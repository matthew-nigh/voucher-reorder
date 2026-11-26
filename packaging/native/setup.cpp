// SPDX-License-Identifier: GPL-3.0-or-later
#include "secure.hpp"
#include <winspool.h>
#include <iostream>

static const wchar_t* name = L"Voucher Reorder";
static const wchar_t* monitor = L"Voucher Reorder Secure Port";
// This inbox v3 driver can bind to our protected port monitor. The v4
// Microsoft Print To PDF driver rejects third-party monitors.
static const wchar_t* driver = L"MS Publisher Imagesetter";
static const wchar_t* key = L"SOFTWARE\\VoucherReorderPrinter";
struct SetupFailure { DWORD error; };
[[noreturn]] static void fail(DWORD error) { throw SetupFailure{error}; }
static void set_port_active(bool active) {
    HKEY registry = nullptr;
    auto status = RegOpenKeyExW(HKEY_LOCAL_MACHINE, key, 0, KEY_SET_VALUE, &registry);
    if (!active && status == ERROR_FILE_NOT_FOUND) return;
    if (status != ERROR_SUCCESS) { SetLastError(status); vr::check(false); }
    DWORD value = active ? 1 : 0;
    status = RegSetValueExW(registry, L"PortActive", 0, REG_DWORD,
        reinterpret_cast<const BYTE*>(&value), sizeof(value));
    RegCloseKey(registry);
    if (status != ERROR_SUCCESS) { SetLastError(status); vr::check(false); }
}
static std::wstring pdf_path(const std::wstring& sid) {
    const auto profileKey = L"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList\\" + sid;
    wchar_t profile[32768]; DWORD bytes = sizeof(profile);
    DWORD type = 0;
    auto result = RegGetValueW(HKEY_LOCAL_MACHINE, profileKey.c_str(), L"ProfileImagePath",
        RRF_RT_REG_SZ | RRF_RT_REG_EXPAND_SZ, &type, profile, &bytes);
    if (result != ERROR_SUCCESS) { SetLastError(result); vr::check(false); }
    wchar_t expanded[32768];
    DWORD length = ExpandEnvironmentStringsW(profile, expanded, 32768);
    vr::check(length && length < 32768);
    std::wstring incoming = std::wstring(expanded) + L"\\AppData\\Local\\VoucherReorder\\Incoming";
    DWORD attributes = GetFileAttributesW(incoming.c_str());
    vr::check(attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY));
    return incoming + L"\\virtual.pdf";
}
// Registry is only a hint that the Local Port already exists. It must never be
// required, and it must never depend on EnumPorts: a third-party monitor with a
// bad EnumPorts breaks system-wide enumeration (error 13) for everyone.
static bool local_port_hint(const std::wstring& path) {
    HKEY registry = nullptr;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Ports",
        0, KEY_QUERY_VALUE | KEY_WOW64_64KEY, &registry) != ERROR_SUCCESS) return false;
    DWORD bytes = 0;
    auto status = RegQueryValueExW(registry, path.c_str(), nullptr, nullptr, nullptr, &bytes);
    RegCloseKey(registry);
    return status == ERROR_SUCCESS;
}
static void add_local_port(const std::wstring& path, int& stage) {
    // AddPort directly; already-exists is success. No EnumPortsW anywhere.
    stage = 162;
    if (local_port_hint(path)) return;
    stage = 163;
    PRINTER_DEFAULTSW defaults{nullptr, nullptr, SERVER_ACCESS_ADMINISTER};
    HANDLE raw = nullptr;
    if (!OpenPrinterW(const_cast<LPWSTR>(L",XcvMonitor Local Port"), &raw, &defaults)) fail(GetLastError());
    std::unique_ptr<void, decltype(&ClosePrinter)> xcv(raw, ClosePrinter);
    DWORD needed = 0, status = ERROR_SUCCESS;
    // LOCALMON AddPort has no output buffer, but the Winspool XcvDataW client
    // still requires a non-null pcbOutputNeeded pointer (error 87 otherwise).
    stage = 164;
    if (!XcvDataW(raw, L"AddPort", reinterpret_cast<PBYTE>(const_cast<wchar_t*>(path.c_str())),
        static_cast<DWORD>((path.size() + 1) * sizeof(wchar_t)), nullptr, 0, &needed, &status)) {
        DWORD error = GetLastError();
        if (error == ERROR_ALREADY_EXISTS || error == ERROR_FILE_EXISTS) return;
        fail(error);
    }
    stage = 165;
    if (status != ERROR_SUCCESS && status != ERROR_ALREADY_EXISTS && status != ERROR_FILE_EXISTS) fail(status);
}
// Print to PDF does not use the secure port. Unregister it so a stale or faulty
// copy cannot sit in the spooler's EnumPorts path. Best effort: PortActive is
// already false, and the monitor itself never fails enumeration.
static void retire_secure_monitor() {
    for (int i = 0; i < 10; ++i) {
        if (DeleteMonitorW(nullptr, nullptr, const_cast<LPWSTR>(monitor))) return;
        DWORD error = GetLastError();
        if (error == ERROR_UNKNOWN_PRINT_MONITOR) return;
        if (error != ERROR_PRINT_MONITOR_IN_USE) return;
        Sleep(1000);
    }
}
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
    int stage = 100;
    try {
        // Only fixed install/remove verbs and a canonical account SID cross UAC.
        vr::check(argc == 3);
        std::wstring action(argv[1]), sid(argv[2]);
        vr::check((action == L"install" || action == L"install-pdf" || action == L"remove") && vr::account_sid(sid));
        stage = 110;
        vr::LockedTree code(vr::program()); vr::protected_image();
        vr::LockedTree system(vr::system_directory());
        auto dll = vr::system_directory() + L"\\VoucherReorderPort.dll";
        vr::Handle dllLock(CreateFileW(dll.c_str(), READ_CONTROL | FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        vr::check(dllLock.value != INVALID_HANDLE_VALUE); vr::verify(dllLock.value, dll);
        const auto port = L"VoucherReorder:" + sid, owner = L"VoucherReorder owner=" + sid;
        PRINTER_DEFAULTSW defaults{nullptr, nullptr, PRINTER_ALL_ACCESS};
        HANDLE printer = nullptr;
        stage = 120;
        if (OpenPrinterW(const_cast<LPWSTR>(name), &printer, &defaults)) {
            auto data = printer_info(printer); auto info = reinterpret_cast<PRINTER_INFO_2W*>(data.data());
            bool ours = info->pComment && owner == info->pComment && info->pDriverName &&
                (!_wcsicmp(info->pDriverName, driver) || !_wcsicmp(info->pDriverName, L"Microsoft Print To PDF"));
            if (!ours) { ClosePrinter(printer); vr::check(false); }
            // Re-create to remove sharing/retention and migrate the old writable port.
            try { remove_queue(printer); } catch (...) { ClosePrinter(printer); throw; }
            ClosePrinter(printer);
            for (int i = 0; i < 30 && queue_exists(); ++i) Sleep(1000);
            vr::check(!queue_exists());
            // Old Local Ports are inert once detached. Leave their registry entry
            // for admin maintenance rather than touching shared/foreign ports.
        } else vr::check(GetLastError() == ERROR_INVALID_PRINTER_NAME);
        stage = 130;
        wchar_t previous[256]; DWORD size = sizeof(previous);
        LONG status = RegGetValueW(HKEY_LOCAL_MACHINE, key, L"OwnerSid", RRF_RT_REG_SZ, nullptr, previous, &size);
        vr::check(status == ERROR_FILE_NOT_FOUND || (status == ERROR_SUCCESS && sid == previous));
        stage = 140;
        enable_driver_privilege();
        if (action == L"remove") {
            // The queue is gone; stop advertising its port before removal.
            set_port_active(false);
            // No service restart. An in-use monitor stays installed for maintenance.
            if (!DeleteMonitorW(nullptr, nullptr, const_cast<LPWSTR>(monitor)))
                vr::check(GetLastError() == ERROR_UNKNOWN_PRINT_MONITOR ||
                    GetLastError() == ERROR_PRINT_MONITOR_IN_USE);
            return 0;
        }
        stage = 150;
        if (action == L"install") {
            vr::LockedTree spool(vr::spool(), true, L"BU");
            vr::LockedTree incoming(vr::spool() + L"\\" + sid, true, sid);
        }
        HKEY registry = nullptr;
        vr::check(RegCreateKeyExW(HKEY_LOCAL_MACHINE, key, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &registry, nullptr) == ERROR_SUCCESS);
        status = RegSetValueExW(registry, L"OwnerSid", 0, REG_SZ, reinterpret_cast<const BYTE*>(sid.c_str()),
            static_cast<DWORD>((sid.size() + 1) * sizeof(wchar_t)));
        RegCloseKey(registry); vr::check(status == ERROR_SUCCESS);
        set_port_active(action == L"install");
        stage = 160;
        std::wstring selectedPort = port;
        const wchar_t* selectedDriver = driver;
        if (action == L"install") {
            MONITOR_INFO_2W monitorInfo{const_cast<LPWSTR>(monitor), const_cast<LPWSTR>(L"Windows x64"), const_cast<LPWSTR>(L"VoucherReorderPort.dll")};
            if (!AddMonitorW(nullptr, 2, reinterpret_cast<LPBYTE>(&monitorInfo)))
                vr::check(GetLastError() == ERROR_PRINT_MONITOR_ALREADY_INSTALLED);
        } else {
            stage = 161;
            selectedPort = pdf_path(sid);
            retire_secure_monitor();
            selectedDriver = L"Microsoft Print To PDF";
            add_local_port(selectedPort, stage);
        }
        vr::Descriptor security(L"O:BAG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;SWRC;;;" + sid + L")(A;OIIO;GA;;;" + sid + L")");
        PRINTER_INFO_2W info{};
        info.pPrinterName = const_cast<LPWSTR>(name); info.pPortName = const_cast<LPWSTR>(selectedPort.c_str());
        info.pDriverName = const_cast<LPWSTR>(selectedDriver); info.pComment = const_cast<LPWSTR>(owner.c_str());
        // Let the v4 PDF driver choose its supported datatype. Imagesetter uses RAW.
        info.pPrintProcessor = const_cast<LPWSTR>(L"winprint");
        if (action == L"install") info.pDatatype = const_cast<LPWSTR>(L"RAW");
        info.pSecurityDescriptor = security.value; info.Attributes = PRINTER_ATTRIBUTE_LOCAL;
        stage = 170;
        printer = AddPrinterW(nullptr, 2, reinterpret_cast<LPBYTE>(&info));
        if (!printer) {
            DWORD error = GetLastError();
            if (action == L"install") {
                set_port_active(false);
            }
            fail(error);
        }
        stage = 180;
        try { if (action == L"install") configure_paper(printer); }
        catch (...) {
            DeletePrinter(printer); ClosePrinter(printer);
            if (action == L"install") {
                set_port_active(false);
            }
            throw;
        }
        ClosePrinter(printer);
        return 0;
    } catch (const SetupFailure& failure) {
        DWORD error = failure.error;
        std::wcerr << L"Printer setup refused at stage " << stage << L" (Windows error " << error
                   << L"). PDF Inbox remains available.\n";
        return stage * 10000 + static_cast<int>(error % 10000);
    } catch (...) {
        DWORD error = GetLastError();
        std::wcerr << L"Printer setup refused at stage " << stage << L" (Windows error " << error
                   << L"). PDF Inbox remains available.\n";
        // The caller records only a numeric code; no path or job data crosses UAC.
        return stage * 10000 + static_cast<int>(error % 10000);
    }
}
