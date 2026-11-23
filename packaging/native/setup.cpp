// SPDX-License-Identifier: GPL-3.0-or-later
#include "secure.hpp"
#include <winspool.h>
#include <iostream>

static const wchar_t* name = L"Voucher Reorder";
static const wchar_t* monitor = L"Voucher Reorder Secure Port";
static const wchar_t* driver = L"Microsoft Print To PDF";
static const wchar_t* key = L"SOFTWARE\\VoucherReorderPrinter";
static std::vector<BYTE> printer_info(HANDLE printer) {
    DWORD bytes = 0; GetPrinterW(printer, 2, nullptr, 0, &bytes);
    vr::check(bytes && bytes < 16 * 1024 * 1024);
    std::vector<BYTE> data(bytes); vr::check(GetPrinterW(printer, 2, data.data(), bytes, &bytes)); return data;
}
static bool queue_exists() {
    DWORD bytes = 0, count = 0;
    BOOL queried = EnumPrintersW(PRINTER_ENUM_LOCAL, nullptr, 4, nullptr, 0, &bytes, &count);
    if (!bytes) { vr::check(queried); return false; }
    vr::check(queried || GetLastError() == ERROR_INSUFFICIENT_BUFFER);
    std::vector<BYTE> data(bytes);
    vr::check(EnumPrintersW(PRINTER_ENUM_LOCAL, nullptr, 4, data.data(), bytes, &bytes, &count));
    auto entries = reinterpret_cast<PRINTER_INFO_4W*>(data.data());
    for (DWORD i = 0; i < count; ++i) if (!_wcsicmp(entries[i].pPrinterName, name)) return true;
    return false;
}
static void configure_paper(HANDLE printer) {
    LONG size = DocumentPropertiesW(nullptr, printer, const_cast<LPWSTR>(name), nullptr, nullptr, 0);
    vr::check(size >= static_cast<LONG>(sizeof(DEVMODEW)) && size < 1024 * 1024);
    std::vector<BYTE> buffer(static_cast<size_t>(size));
    auto mode = reinterpret_cast<DEVMODEW*>(buffer.data());
    vr::check(DocumentPropertiesW(nullptr, printer, const_cast<LPWSTR>(name), mode, nullptr, DM_OUT_BUFFER) == IDOK);
    mode->dmFields |= DM_PAPERSIZE | DM_DUPLEX;
    mode->dmPaperSize = DMPAPER_LETTER; mode->dmDuplex = DMDUP_SIMPLEX;
    vr::check(DocumentPropertiesW(nullptr, printer, const_cast<LPWSTR>(name), mode, mode,
        DM_IN_BUFFER | DM_OUT_BUFFER) == IDOK);
    PRINTER_INFO_8W info{mode}; vr::check(SetPrinterW(printer, 8, reinterpret_cast<LPBYTE>(&info), 0));
}
static void enable_driver_privilege() {
    HANDLE raw = nullptr;
    vr::check(OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &raw));
    vr::Handle token(raw); TOKEN_PRIVILEGES privileges{};
    privileges.PrivilegeCount = 1;
    vr::check(LookupPrivilegeValueW(nullptr, SE_LOAD_DRIVER_NAME, &privileges.Privileges[0].Luid));
    privileges.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    vr::check(AdjustTokenPrivileges(raw, FALSE, &privileges, 0, nullptr, nullptr));
    vr::check(GetLastError() == ERROR_SUCCESS);
}
static void remove_queue(HANDLE printer) {
    auto bytes = printer_info(printer);
    vr::check(reinterpret_cast<PRINTER_INFO_2W*>(bytes.data())->cJobs == 0);
    vr::check(DeletePrinter(printer));
}
int wmain(int argc, wchar_t** argv) {
    try {
        // Only fixed install/remove verbs and a canonical account SID cross UAC.
        vr::check(argc == 3);
        std::wstring action(argv[1]), sid(argv[2]);
        vr::check((action == L"install" || action == L"remove") && vr::account_sid(sid));
        vr::LockedTree code(vr::program()); vr::protected_image();
        vr::LockedTree system(vr::system_directory());
        auto dll = vr::system_directory() + L"\\VoucherReorderPort.dll";
        vr::Handle dllLock(CreateFileW(dll.c_str(), READ_CONTROL | FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        vr::check(dllLock.value != INVALID_HANDLE_VALUE); vr::verify(dllLock.value, dll);
        const auto port = L"VoucherReorder:" + sid, owner = L"VoucherReorder owner=" + sid;
        PRINTER_DEFAULTSW defaults{nullptr, nullptr, PRINTER_ALL_ACCESS};
        HANDLE printer = nullptr;
        if (OpenPrinterW(const_cast<LPWSTR>(name), &printer, &defaults)) {
            auto data = printer_info(printer); auto info = reinterpret_cast<PRINTER_INFO_2W*>(data.data());
            bool ours = info->pComment && owner == info->pComment && info->pDriverName &&
                (std::wstring(info->pDriverName) == driver || std::wstring(info->pDriverName) == L"MS Publisher Imagesetter");
            if (!ours) { ClosePrinter(printer); vr::check(false); }
            // Re-create to remove sharing/retention and migrate the old writable port.
            try { remove_queue(printer); } catch (...) { ClosePrinter(printer); throw; }
            ClosePrinter(printer);
            for (int i = 0; i < 30 && queue_exists(); ++i) Sleep(1000);
            vr::check(!queue_exists());
            // Old Local Ports are inert once detached. Leave their registry entry
            // for admin maintenance rather than touching shared/foreign ports.
        } else vr::check(GetLastError() == ERROR_INVALID_PRINTER_NAME);
        wchar_t previous[256]; DWORD size = sizeof(previous);
        LONG status = RegGetValueW(HKEY_LOCAL_MACHINE, key, L"OwnerSid", RRF_RT_REG_SZ, nullptr, previous, &size);
        vr::check(status == ERROR_FILE_NOT_FOUND || (status == ERROR_SUCCESS && sid == previous));
        enable_driver_privilege();
        if (action == L"remove") {
            // No service restart. An in-use monitor stays installed for maintenance.
            if (!DeleteMonitorW(nullptr, nullptr, const_cast<LPWSTR>(monitor)))
                vr::check(GetLastError() == ERROR_UNKNOWN_PRINT_MONITOR);
            return 0;
        }
        vr::LockedTree spool(vr::spool(), true);
        vr::LockedTree incoming(vr::spool() + L"\\" + sid, true, sid);
        HKEY registry = nullptr;
        vr::check(RegCreateKeyExW(HKEY_LOCAL_MACHINE, key, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &registry, nullptr) == ERROR_SUCCESS);
        status = RegSetValueExW(registry, L"OwnerSid", 0, REG_SZ, reinterpret_cast<const BYTE*>(sid.c_str()),
            static_cast<DWORD>((sid.size() + 1) * sizeof(wchar_t)));
        RegCloseKey(registry); vr::check(status == ERROR_SUCCESS);
        MONITOR_INFO_2W monitorInfo{const_cast<LPWSTR>(monitor), const_cast<LPWSTR>(L"Windows x64"), const_cast<LPWSTR>(L"VoucherReorderPort.dll")};
        if (!AddMonitorW(nullptr, 2, reinterpret_cast<LPBYTE>(&monitorInfo)))
            vr::check(GetLastError() == ERROR_PRINT_MONITOR_ALREADY_INSTALLED);
        vr::Descriptor security(L"O:BAG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;SWRC;;;" + sid + L")(A;OIIO;GA;;;" + sid + L")");
        PRINTER_INFO_2W info{};
        info.pPrinterName = const_cast<LPWSTR>(name); info.pPortName = const_cast<LPWSTR>(port.c_str());
        info.pDriverName = const_cast<LPWSTR>(driver); info.pComment = const_cast<LPWSTR>(owner.c_str());
        info.pPrintProcessor = const_cast<LPWSTR>(L"winprint"); info.pDatatype = const_cast<LPWSTR>(L"RAW");
        info.pSecurityDescriptor = security.value; info.Attributes = PRINTER_ATTRIBUTE_LOCAL;
        printer = AddPrinterW(nullptr, 2, reinterpret_cast<LPBYTE>(&info)); vr::check(printer != nullptr);
        try { configure_paper(printer); }
        catch (...) { DeletePrinter(printer); ClosePrinter(printer); throw; }
        ClosePrinter(printer);
        return 0;
    } catch (...) {
        std::wcerr << L"Printer setup refused. Verify the protected package, owner, pending jobs and Microsoft Print To PDF driver. PDF Inbox remains available.\n";
        return 1;
    }
}
