// SPDX-License-Identifier: GPL-3.0-or-later
// No PDF parsing, user paths, executable launches, or network endpoints.
#include "secure.hpp"
#include <winspool.h>
#include <winsplp.h>
#include <rpc.h>
#include <cstring>

static const wchar_t* monitorName = L"Voucher Reorder Secure Port";
static const wchar_t* registryPath = L"SOFTWARE\\VoucherReorderPrinter";
static std::wstring configured_sid() {
    wchar_t sid[256]; DWORD size = sizeof(sid);
    vr::check(RegGetValueW(HKEY_LOCAL_MACHINE, registryPath, L"OwnerSid", RRF_RT_REG_SZ,
        nullptr, sid, &size) == ERROR_SUCCESS);
    vr::check(vr::account_sid(sid)); return sid;
}
struct SystemIdentity {
    HANDLE old = nullptr;
    SystemIdentity() {
        if (!OpenThreadToken(GetCurrentThread(), TOKEN_IMPERSONATE | TOKEN_QUERY, TRUE, &old))
            vr::check(GetLastError() == ERROR_NO_TOKEN);
        if (!RevertToSelf()) { if (old) CloseHandle(old); vr::check(false); }
    }
    ~SystemIdentity() {
        if (old) {
            // Never return a borrowed spooler thread with changed authority.
            if (!SetThreadToken(nullptr, old)) std::terminate();
            CloseHandle(old);
        }
    }
};
struct Port {
    std::wstring sid, partial, ready;
    std::unique_ptr<vr::LockedTree> root, folder;
    std::unique_ptr<vr::Handle> file;
    HANDLE printer = nullptr;
    DWORD job = 0, bytes = 0;
    bool failed = false;
    explicit Port(std::wstring s) : sid(std::move(s)) {}
    void reset() {
        file.reset(); // An incomplete .partial is never admitted as a PDF.
        folder.reset(); root.reset();
        if (printer) { ClosePrinter(printer); printer = nullptr; }
        bytes = 0; job = 0; failed = false;
    }
    ~Port() { reset(); }
};
static BOOL WINAPI enum_ports(HANDLE, LPWSTR, DWORD level, LPBYTE data, DWORD size, LPDWORD needed, LPDWORD count) {
    *count = 0; *needed = 0;
    try {
        auto name = L"VoucherReorder:" + configured_sid();
        std::wstring monitor(monitorName), description(L"Protected unique PDF jobs");
        DWORD structure = level == 1 ? sizeof(PORT_INFO_1W) : sizeof(PORT_INFO_2W);
        if (level != 1 && level != 2) { SetLastError(ERROR_INVALID_LEVEL); return FALSE; }
        *needed = structure + static_cast<DWORD>((name.size() + 1) * sizeof(wchar_t));
        if (level == 2) *needed += static_cast<DWORD>((monitor.size() + description.size() + 2) * sizeof(wchar_t));
        if (size < *needed) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return FALSE; }
        ZeroMemory(data, *needed);
        auto cursor = reinterpret_cast<wchar_t*>(data + structure);
        auto put = [&](const std::wstring& value) {
            auto dest = cursor; memcpy(dest, value.c_str(), (value.size() + 1) * sizeof(wchar_t));
            cursor += value.size() + 1; return dest;
        };
        if (level == 1) reinterpret_cast<PORT_INFO_1W*>(data)->pName = put(name);
        else {
            auto info = reinterpret_cast<PORT_INFO_2W*>(data);
            info->pPortName = put(name); info->pMonitorName = put(monitor);
            info->pDescription = put(description); info->fPortType = PORT_TYPE_WRITE;
        }
        *count = 1; return TRUE;
    } catch (...) { SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
}
static BOOL WINAPI open_port(HANDLE, LPWSTR name, PHANDLE output) {
    try {
        auto sid = vr::port_sid(name); vr::check(sid == configured_sid());
        *output = new Port(sid); return TRUE;
    } catch (...) { SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
}
static BOOL WINAPI start_doc(HANDLE handle, LPWSTR printer, DWORD job, DWORD level, LPBYTE) {
    auto p = static_cast<Port*>(handle);
    try {
        SystemIdentity system;
        vr::check(!p->file && level == 1 && p->sid == configured_sid());
        p->root = std::make_unique<vr::LockedTree>(vr::spool());
        auto folder = vr::spool() + L"\\" + p->sid;
        p->folder = std::make_unique<vr::LockedTree>(folder);
        UUID uuid; vr::check(UuidCreate(&uuid) == RPC_S_OK);
        RPC_WSTR text = nullptr; vr::check(UuidToStringW(&uuid, &text) == RPC_S_OK);
        std::wstring token(reinterpret_cast<wchar_t*>(text)); RpcStringFreeW(&text);
        p->partial = folder + L"\\" + token + L".partial";
        p->ready = folder + L"\\" + token + L".pdf";
        vr::Descriptor sd(vr::directory_acl());
        SECURITY_ATTRIBUTES sa{sizeof(sa), sd.value, FALSE};
        p->file = std::make_unique<vr::Handle>(CreateFileW(p->partial.c_str(), GENERIC_WRITE | DELETE | WRITE_DAC,
            0, &sa, CREATE_NEW, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        vr::check(p->file->value != INVALID_HANDLE_VALUE);
        vr::check(OpenPrinterW(printer, &p->printer, nullptr)); p->job = job;
        return TRUE;
    } catch (...) { p->reset(); SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
}
static BOOL WINAPI write_port(HANDLE handle, LPBYTE data, DWORD size, LPDWORD written) {
    auto p = static_cast<Port*>(handle); *written = 0;
    if (!p->file || p->failed || size > 100 * 1024 * 1024 - p->bytes) {
        p->failed = true; SetLastError(ERROR_DISK_FULL); return FALSE;
    }
    if (!WriteFile(p->file->value, data, size, written, nullptr) || *written != size) {
        p->failed = true; return FALSE;
    }
    p->bytes += *written; return TRUE;
}
static BOOL WINAPI end_doc(HANDLE handle) {
    auto p = static_cast<Port*>(handle);
    try {
        SystemIdentity system;
        vr::check(p->file && !p->failed && p->bytes);
        vr::check(FlushFileBuffers(p->file->value));
        // Grant read/delete on this completed file only. No directory creation,
        // write, ACL, owner or delete-child rights are granted to the desktop SID.
        vr::set_dacl(p->file->value, L"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRSD;;;" + p->sid + L")");
        DWORD length = static_cast<DWORD>(p->ready.size() * sizeof(wchar_t));
        std::vector<BYTE> buffer(sizeof(FILE_RENAME_INFO) + length);
        auto rename = reinterpret_cast<FILE_RENAME_INFO*>(buffer.data());
        rename->ReplaceIfExists = FALSE; rename->RootDirectory = nullptr; rename->FileNameLength = length;
        memcpy(rename->FileName, p->ready.data(), length);
        vr::check(SetFileInformationByHandle(p->file->value, FileRenameInfo, rename, static_cast<DWORD>(buffer.size())));
        p->file.reset(); // Publish complete, flushed bytes before spooler completion notification.
        // Publication already committed. A notification failure must not tell
        // the spooler to retransmit an already durable PDF as a second job.
        SetJobW(p->printer, p->job, 0, nullptr, JOB_CONTROL_SENT_TO_PRINTER);
        p->reset(); return TRUE;
    } catch (...) { p->reset(); SetLastError(ERROR_WRITE_FAULT); return FALSE; }
}
static BOOL WINAPI read_port(HANDLE, LPBYTE, DWORD, LPDWORD read) {
    *read = 0; SetLastError(ERROR_NOT_SUPPORTED); return FALSE;
}
// Required configuration callbacks expose no mutation protocol. Only the
// administrator-protected setup executable configures this single fixed port.
static BOOL WINAPI xcv_open(HANDLE, LPCWSTR, ACCESS_MASK, PHANDLE handle) {
    *handle = nullptr; SetLastError(ERROR_NOT_SUPPORTED); return FALSE;
}
static DWORD WINAPI xcv_data(HANDLE, LPCWSTR, PBYTE, DWORD, PBYTE, DWORD, PDWORD needed) {
    *needed = 0; return ERROR_NOT_SUPPORTED;
}
static BOOL WINAPI xcv_close(HANDLE) { return TRUE; }
static BOOL WINAPI close_port(HANDLE handle) { delete static_cast<Port*>(handle); return TRUE; }
static void WINAPI shutdown(HANDLE) {}
extern "C" __declspec(dllexport) LPMONITOR2 WINAPI InitializePrintMonitor2(PMONITORINIT, PHANDLE handle) {
    static MONITOR2 table{};
    table.cbSize = sizeof(table); table.pfnEnumPorts = enum_ports; table.pfnOpenPort = open_port;
    table.pfnStartDocPort = start_doc; table.pfnWritePort = write_port;
    table.pfnReadPort = read_port; table.pfnXcvOpenPort = xcv_open;
    table.pfnXcvDataPort = xcv_data; table.pfnXcvClosePort = xcv_close;
    table.pfnEndDocPort = end_doc; table.pfnClosePort = close_port; table.pfnShutdown = shutdown;
    *handle = &table; return &table;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) { return TRUE; }
