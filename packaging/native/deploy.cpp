// SPDX-License-Identifier: GPL-3.0-or-later
// The distributed Setup image: run the per-user NSIS UI or perform its elevated action.
#include "secure.hpp"
#include <shellapi.h>
#include <winsvc.h>
#include <winspool.h>
#include <cstring>
#include <cstddef>
#include <iostream>
#include <vector>

// Deploy sub-steps. A failure is reported as stage * 10000 + (Win32 error % 10000),
// the same pattern as the printer stages (100-180); deploy stages are 200-249.
enum Stage {
    kDestination = 200,   // protected destination directories (Program Files, System32)
    kInspect = 201,       // inspecting the already-installed helper/monitor
    kSpoolerStop = 210,   // stopping the print spooler and dependents
    kSpoolerStart = 211,  // restarting the spooler and waiting for it to answer
    kCopyHelper = 220,    // writing PrinterSetup.exe (retry / rename-aside)
    kCopyMonitor = 221,   // writing VoucherReorderPort.dll (retry / rename-aside)
    kHashHelper = 230,    // byte/hash and ACL verification of PrinterSetup.exe
    kHashMonitor = 231,   // byte/hash and ACL verification of VoucherReorderPort.dll
    kLaunch = 240,        // starting the Program Files PrinterSetup.exe
    kHelperWait = 241,    // waiting for PrinterSetup.exe to finish
};
static const wchar_t* stage_name(int stage) {
    switch (stage) {
    case kDestination: return L"protected destination check";
    case kInspect: return L"inspecting installed helper or monitor";
    case kSpoolerStop: return L"stopping the print spooler";
    case kSpoolerStart: return L"restarting the print spooler";
    case kCopyHelper: return L"copying PrinterSetup.exe";
    case kCopyMonitor: return L"copying VoucherReorderPort.dll";
    case kHashHelper: return L"verifying PrinterSetup.exe bytes and ACL";
    case kHashMonitor: return L"verifying VoucherReorderPort.dll bytes and ACL";
    case kLaunch: return L"starting PrinterSetup.exe";
    case kHelperWait: return L"waiting for PrinterSetup.exe";
    }
    return L"deployment";
}
struct DeployError { int stage; DWORD error; };
static int g_stage = kDestination;
// Capture the Win32 error before any destructor can disturb it.
static void must(bool ok) { if (!ok) { DWORD e = GetLastError(); throw DeployError{g_stage, e}; } }
static void fail(DWORD error) { throw DeployError{g_stage, error}; }

struct Embedded { const void* bytes; DWORD size; };
static Embedded embedded(WORD id) {
    auto resource = FindResourceW(nullptr, MAKEINTRESOURCEW(id), RT_RCDATA); vr::check(resource != nullptr);
    auto size = SizeofResource(nullptr, resource); vr::check(size != 0);
    auto bytes = LockResource(LoadResource(nullptr, resource)); vr::check(bytes != nullptr);
    return {bytes, size};
}
static bool same_bytes(HANDLE file, const Embedded& want) {
    LARGE_INTEGER actual{}, zero{};
    vr::check(GetFileSizeEx(file, &actual) && actual.QuadPart < 256 * 1024 * 1024);
    if (actual.QuadPart != want.size) return false;
    vr::check(SetFilePointerEx(file, zero, nullptr, FILE_BEGIN));
    std::vector<BYTE> copy(want.size); DWORD read = 0;
    vr::check(ReadFile(file, copy.data(), want.size, &read, nullptr) && read == want.size);
    return !memcmp(want.bytes, copy.data(), want.size);
}
// True when the file exists and differs from the embedded bytes. The existing
// file must pass the same owner/ACL/reparse checks before it is even compared.
static bool installed_is_stale(WORD id, const std::wstring& path) {
    g_stage = kInspect;
    auto want = embedded(id);
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | READ_CONTROL, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    if (file.value == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();
        if (error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND) return false;
        // A sharing violation on a read-only open still means a file exists that we cannot compare.
        if (error == ERROR_SHARING_VIOLATION || error == ERROR_LOCK_VIOLATION) return true;
        fail(error);
    }
    vr::verify(file.value, path);
    return !same_bytes(file.value, want);
}
static bool sharing_violation(DWORD error) {
    return error == ERROR_SHARING_VIOLATION || error == ERROR_LOCK_VIOLATION || error == ERROR_ACCESS_DENIED;
}
// One attempt to create or overwrite the file. Returns false only when the file
// exists but is locked (mapped by a running process or open without write
// sharing); every other failure is reported with its Win32 error. An existing
// file must pass verification (trusted owner, no untrusted writers, no reparse
// point or extra links) before it is rewritten.
static bool try_deploy(const Embedded& want, const std::wstring& path) {
    vr::Descriptor sd(L"O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;BU)");
    SECURITY_ATTRIBUTES sa{sizeof(sa), sd.value, FALSE};
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE | READ_CONTROL, 0, &sa,
        CREATE_NEW, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    bool write = true;
    if (file.value == INVALID_HANDLE_VALUE && GetLastError() == ERROR_FILE_EXISTS) {
        // Exclusive access fails (sharing violation) while the file is mapped
        // by a running process or held open by another one.
        file.value = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE | READ_CONTROL, 0, nullptr,
            OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        if (file.value == INVALID_HANDLE_VALUE) {
            DWORD error = GetLastError();
            if (sharing_violation(error)) { SetLastError(error); return false; }
            fail(error);
        }
        vr::verify(file.value, path);
        write = !same_bytes(file.value, want);
    } else must(file.value != INVALID_HANDLE_VALUE);
    if (write) {
        LARGE_INTEGER zero{}; DWORD written = 0;
        must(SetFilePointerEx(file.value, zero, nullptr, FILE_BEGIN));
        must(WriteFile(file.value, want.bytes, want.size, &written, nullptr) && written == want.size);
        must(SetEndOfFile(file.value));
        must(FlushFileBuffers(file.value));
    }
    return true;
}
// Last resort for a file that stays locked: verify it, rename it (the same
// verified handle) to a .old name, and queue that file for deletion at reboot.
// A mapped image can be renamed but not overwritten or deleted.
static void rename_aside(const std::wstring& path) {
    std::wstring target;
    {
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | DELETE | READ_CONTROL,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
        FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    must(file.value != INVALID_HANDLE_VALUE);
    vr::verify(file.value, path);
    for (int i = 0; i < 100; ++i) {
        target = path + L".old" + (i ? L"." + std::to_wstring(i) : L"");
        // A previous .old that is no longer mapped is simply removed.
        if (DeleteFileW(target.c_str()) || GetLastError() == ERROR_FILE_NOT_FOUND) break;
        target.clear();
    }
    if (target.empty()) fail(ERROR_ALREADY_EXISTS);
    const size_t bytes = offsetof(FILE_RENAME_INFO, FileName) + (target.size() + 1) * sizeof(wchar_t);
    std::vector<BYTE> buffer(bytes);
    auto info = reinterpret_cast<FILE_RENAME_INFO*>(buffer.data());
    info->FileNameLength = static_cast<DWORD>(target.size() * sizeof(wchar_t));
    memcpy(info->FileName, target.c_str(), (target.size() + 1) * sizeof(wchar_t));
    must(SetFileInformationByHandle(file.value, FileRenameInfo, info, static_cast<DWORD>(bytes)));
    }
    // The renamed old file is removed at the next reboot (best effort: an
    // unscheduled .old file is harmless and is replaced by the next upgrade).
    MoveFileExW(target.c_str(), nullptr, MOVEFILE_DELAY_UNTIL_REBOOT);
}
// Installs or replaces a fixed-name file: retry with backoff for about 30
// seconds while it is locked, then move the verified old file aside.
static void deploy(WORD id, const std::wstring& path, int copyStage, int hashStage) {
    auto want = embedded(id);
    g_stage = copyStage;
    bool done = false;
    ULONGLONG deadline = GetTickCount64() + 30000;
    DWORD delay = 100;
    while (!(done = try_deploy(want, path)) && GetTickCount64() < deadline) {
        Sleep(delay);
        if (delay < 2000) delay *= 2;
    }
    if (!done) {
        rename_aside(path);
        if (!try_deploy(want, path)) fail(ERROR_SHARING_VIOLATION);
    }
    g_stage = hashStage;
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | READ_CONTROL, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    must(file.value != INVALID_HANDLE_VALUE);
    vr::verify(file.value, path);
    if (!same_bytes(file.value, want)) fail(ERROR_CRC);
}
// Replacing a monitor DLL the spooler already loaded needs the spooler stopped
// (a mapped image cannot be overwritten, and the old code would stay resident).
// The registered monitor entry is untouched; the restarted spooler loads the new
// bytes. The spooler is always restarted, even if replacement fails.
struct SpoolerRestart {
    SC_HANDLE manager = nullptr, service = nullptr; bool stopped = false;
    static void wait(SC_HANDLE service, DWORD want) {
        for (int i = 0; i < 300; ++i) {
            SERVICE_STATUS_PROCESS status{}; DWORD bytes = 0;
            must(QueryServiceStatusEx(service, SC_STATUS_PROCESS_INFO, reinterpret_cast<BYTE*>(&status), sizeof(status), &bytes));
            if (status.dwCurrentState == want) return;
            Sleep(100);
        }
        fail(ERROR_SERVICE_REQUEST_TIMEOUT);
    }
    static void stop(SC_HANDLE manager, SC_HANDLE service) {
        DWORD bytes = 0, count = 0;
        EnumDependentServicesW(service, SERVICE_ACTIVE, nullptr, 0, &bytes, &count);
        if (bytes) {
            std::vector<BYTE> data(bytes);
            must(EnumDependentServicesW(service, SERVICE_ACTIVE, reinterpret_cast<LPENUM_SERVICE_STATUSW>(data.data()), bytes, &bytes, &count));
            auto list = reinterpret_cast<LPENUM_SERVICE_STATUSW>(data.data());
            for (DWORD i = 0; i < count; ++i) {
                std::unique_ptr<SC_HANDLE__, decltype(&CloseServiceHandle)> dependent(
                    OpenServiceW(manager, list[i].lpServiceName, SERVICE_STOP | SERVICE_QUERY_STATUS), CloseServiceHandle);
                SERVICE_STATUS status{};
                if (dependent && ControlService(dependent.get(), SERVICE_CONTROL_STOP, &status)) wait(dependent.get(), SERVICE_STOPPED);
            }
        }
        SERVICE_STATUS status{};
        if (!ControlService(service, SERVICE_CONTROL_STOP, &status)) {
            DWORD error = GetLastError();
            // Already stopped, or a stop is already in progress: just wait below.
            if (error != ERROR_SERVICE_NOT_ACTIVE && error != ERROR_SERVICE_CANNOT_ACCEPT_CTRL) fail(error);
        }
        wait(service, SERVICE_STOPPED);
    }
    SpoolerRestart() {
        g_stage = kSpoolerStop;
        manager = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT); must(manager != nullptr);
        service = OpenServiceW(manager, L"Spooler", SERVICE_STOP | SERVICE_START | SERVICE_QUERY_STATUS | SERVICE_ENUMERATE_DEPENDENTS);
        if (!service) { DWORD error = GetLastError(); CloseServiceHandle(manager); fail(error); }
        stopped = true;
        try { stop(manager, service); } catch (...) { restart(); throw; }
    }
    // Starts the spooler again and waits until it answers. Returns 0 or a Win32 error.
    DWORD start() noexcept {
        if (!stopped) return 0;
        stopped = false;
        // StartService fails harmlessly if it is already running.
        if (!StartServiceW(service, 0, nullptr) && GetLastError() != ERROR_SERVICE_ALREADY_RUNNING)
            return GetLastError();
        try { wait(service, SERVICE_RUNNING); } catch (const DeployError& e) { return e.error; } catch (...) { return ERROR_GEN_FAILURE; }
        // SERVICE_RUNNING precedes the spooler's RPC endpoint and monitor
        // loading. Wait until it answers, or the printer helper started
        // next races it (RPC unavailable / invalid printer name).
        for (int i = 0; i < 600; ++i) {
            DWORD bytes = 0, count = 0;
            if (EnumPrintersW(PRINTER_ENUM_LOCAL, nullptr, 4, nullptr, 0, &bytes, &count) ||
                GetLastError() == ERROR_INSUFFICIENT_BUFFER) return 0;
            Sleep(100);
        }
        return ERROR_TIMEOUT;
    }
    // Normal path: a failed restart is a reported deployment failure.
    void finish() { g_stage = kSpoolerStart; DWORD error = start(); if (error) fail(error); }
    void restart() noexcept { start(); }
    ~SpoolerRestart() { restart(); CloseServiceHandle(service); CloseServiceHandle(manager); }
};
static int installer(int argc, wchar_t** argv) {
    wchar_t self[32768];
    vr::check(GetModuleFileNameW(nullptr, self, 32768) > 0);
    vr::check(SetEnvironmentVariableW(L"VOUCHER_REORDER_SETUP_IMAGE", self));
    wchar_t temporary[MAX_PATH], filename[MAX_PATH];
    vr::check(GetTempPathW(MAX_PATH, temporary) && GetTempFileNameW(temporary, L"VRI", 0, filename));
    auto resource = FindResourceW(nullptr, MAKEINTRESOURCEW(103), RT_RCDATA);
    vr::check(resource != nullptr);
    auto size = SizeofResource(nullptr, resource);
    auto bytes = LockResource(LoadResource(nullptr, resource));
    vr::check(size && bytes);
    {
        vr::Handle file(CreateFileW(filename, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr));
        vr::check(file.value != INVALID_HANDLE_VALUE);
        DWORD written = 0;
        vr::check(WriteFile(file.value, bytes, size, &written, nullptr) && written == size);
    }
    std::wstring command = L"\"" + std::wstring(filename) + L"\"";
    for (int i = 1; i < argc; ++i) command += L" " + std::wstring(argv[i]);
    std::vector<wchar_t> args(command.begin(), command.end()); args.push_back(0);
    STARTUPINFOW start{}; start.cb = sizeof(start); PROCESS_INFORMATION process{};
    vr::check(CreateProcessW(filename, args.data(), nullptr, nullptr, FALSE, 0,
        nullptr, nullptr, &start, &process));
    vr::Handle thread(process.hThread), child(process.hProcess);
    vr::check(WaitForSingleObject(child.value, INFINITE) == WAIT_OBJECT_0);
    DWORD code = 0; vr::check(GetExitCodeProcess(child.value, &code));
    DeleteFileW(filename);
    return static_cast<int>(code);
}
static int report(int stage, DWORD error, const char* refusal) {
    std::wcerr << L"Deployment failed at stage " << stage << L" (" << stage_name(stage) << L"): Windows error " << error;
    if (refusal) std::wcerr << L"; refused: " << refusal;
    std::wcerr << L". No ACLs were repaired.\n";
    return stage * 10000 + static_cast<int>(error % 10000);
}
static int run(int argc, wchar_t** argv) {
    try {
        if (argc < 2 || std::wstring(argv[1]) != L"/elevated-printer") return installer(argc, argv);
        g_stage = kDestination;
        vr::check(argc == 4);
        std::wstring action(argv[2]), sid(argv[3]);
        vr::check((action == L"install" || action == L"install-pdf") && vr::account_sid(sid));
        vr::LockedTree directory(vr::program(), true, L"BU");
        // AddMonitor requires the DLL in System32. Deploy only our fixed names,
        // with the same no-reparse/ACL checks and embedded-byte verification.
        // Stale files from an earlier build are replaced here, in the elevated
        // Setup image; the installed helper never updates itself.
        vr::LockedTree system(vr::system_directory());
        const auto helper = vr::program() + L"\\PrinterSetup.exe";
        const auto monitor = vr::system_directory() + L"\\VoucherReorderPort.dll";
        const bool stale = installed_is_stale(101, helper) | installed_is_stale(102, monitor);
        {
            // Stop the spooler whenever a stale file must be replaced: it holds the
            // monitor DLL mapped. It is restarted on every path, including failure.
            std::unique_ptr<SpoolerRestart> spooler;
            if (stale) spooler = std::make_unique<SpoolerRestart>();
            deploy(101, helper, kCopyHelper, kHashHelper);
            deploy(102, monitor, kCopyMonitor, kHashMonitor);
            if (spooler) spooler->finish();
        }
        // Setup may be launched from Downloads. Only the fixed, verified
        // Program Files executable is used for the privileged printer operation.
        g_stage = kLaunch;
        std::wstring command = L"\"" + vr::program() + L"\\PrinterSetup.exe\" " + action + L" " + sid;
        std::vector<wchar_t> mutableCommand(command.begin(), command.end());
        mutableCommand.push_back(0);
        STARTUPINFOW start{}; start.cb = sizeof(start); PROCESS_INFORMATION process{};
        must(CreateProcessW((vr::program() + L"\\PrinterSetup.exe").c_str(), mutableCommand.data(),
            nullptr, nullptr, FALSE, 0, nullptr, vr::system_directory().c_str(), &start, &process));
        vr::Handle thread(process.hThread), child(process.hProcess);
        g_stage = kHelperWait;
        must(WaitForSingleObject(child.value, 300000) == WAIT_OBJECT_0);
        DWORD code = 0; must(GetExitCodeProcess(child.value, &code));
        return static_cast<int>(code);
    } catch (const DeployError& e) {
        return report(e.stage, e.error, nullptr);
    } catch (const std::exception& e) {
        // A refusal from the shared verification helpers (reparse point, extra links,
        // untrusted owner/writer, final path mismatch) rather than a Win32 failure.
        DWORD error = GetLastError();
        return report(g_stage, error ? error : ERROR_INVALID_DATA, e.what());
    } catch (...) {
        return report(g_stage, GetLastError(), nullptr);
    }
}
int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    int argc = 0;
    auto argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) return 1;
    int result = run(argc, argv);
    LocalFree(argv);
    return result;
}
