// SPDX-License-Identifier: GPL-3.0-or-later
// The distributed Setup image: run the per-user NSIS UI or perform its elevated action.
#include "secure.hpp"
#include <shellapi.h>
#include <winsvc.h>
#include <winspool.h>
#include <cstring>
#include <iostream>
#include <vector>

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
    auto want = embedded(id);
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | READ_CONTROL, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    if (file.value == INVALID_HANDLE_VALUE) {
        vr::check(GetLastError() == ERROR_FILE_NOT_FOUND || GetLastError() == ERROR_PATH_NOT_FOUND);
        return false;
    }
    vr::verify(file.value, path);
    return !same_bytes(file.value, want);
}
// Installs or replaces a fixed-name file. A stale file is replaced in place
// only after it passes verification (trusted owner, no untrusted writers, no
// reparse point or extra links); an unsafe existing file is still refused.
static void deploy(WORD id, const std::wstring& path) {
    auto want = embedded(id);
    vr::Descriptor sd(L"O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;BU)");
    SECURITY_ATTRIBUTES sa{sizeof(sa), sd.value, FALSE};
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE | READ_CONTROL, 0, &sa,
        CREATE_NEW, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    bool write = true;
    if (file.value == INVALID_HANDLE_VALUE && GetLastError() == ERROR_FILE_EXISTS) {
        // Exclusive access fails (sharing violation) while the file is mapped
        // by a running process; the caller stops the spooler first for the DLL.
        file.value = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE | READ_CONTROL, 0, nullptr,
            OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        vr::check(file.value != INVALID_HANDLE_VALUE); vr::verify(file.value, path);
        write = !same_bytes(file.value, want);
    } else vr::check(file.value != INVALID_HANDLE_VALUE);
    if (write) {
        LARGE_INTEGER zero{}; DWORD written = 0;
        vr::check(SetFilePointerEx(file.value, zero, nullptr, FILE_BEGIN));
        vr::check(WriteFile(file.value, want.bytes, want.size, &written, nullptr) && written == want.size);
        vr::check(SetEndOfFile(file.value));
        vr::check(FlushFileBuffers(file.value));
    }
    vr::verify(file.value, path);
    vr::check(same_bytes(file.value, want));
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
            vr::check(QueryServiceStatusEx(service, SC_STATUS_PROCESS_INFO, reinterpret_cast<BYTE*>(&status), sizeof(status), &bytes));
            if (status.dwCurrentState == want) return;
            Sleep(100);
        }
        vr::check(false, "spooler state change timed out");
    }
    static void stop(SC_HANDLE manager, SC_HANDLE service) {
        DWORD bytes = 0, count = 0;
        EnumDependentServicesW(service, SERVICE_ACTIVE, nullptr, 0, &bytes, &count);
        if (bytes) {
            std::vector<BYTE> data(bytes);
            vr::check(EnumDependentServicesW(service, SERVICE_ACTIVE, reinterpret_cast<LPENUM_SERVICE_STATUSW>(data.data()), bytes, &bytes, &count));
            auto list = reinterpret_cast<LPENUM_SERVICE_STATUSW>(data.data());
            for (DWORD i = 0; i < count; ++i) {
                std::unique_ptr<SC_HANDLE__, decltype(&CloseServiceHandle)> dependent(
                    OpenServiceW(manager, list[i].lpServiceName, SERVICE_STOP | SERVICE_QUERY_STATUS), CloseServiceHandle);
                SERVICE_STATUS status{};
                if (dependent && ControlService(dependent.get(), SERVICE_CONTROL_STOP, &status)) wait(dependent.get(), SERVICE_STOPPED);
            }
        }
        SERVICE_STATUS status{};
        if (!ControlService(service, SERVICE_CONTROL_STOP, &status))
            vr::check(GetLastError() == ERROR_SERVICE_NOT_ACTIVE);
        wait(service, SERVICE_STOPPED);
    }
    SpoolerRestart() {
        manager = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT); vr::check(manager != nullptr);
        service = OpenServiceW(manager, L"Spooler", SERVICE_STOP | SERVICE_START | SERVICE_QUERY_STATUS | SERVICE_ENUMERATE_DEPENDENTS);
        if (!service) { CloseServiceHandle(manager); vr::check(false); }
        stopped = true;
        try { stop(manager, service); } catch (...) { restart(); throw; }
    }
    void restart() noexcept {
        if (!stopped) return;
        stopped = false;
        // Best effort: StartService fails harmlessly if it is already running.
        if (StartServiceW(service, 0, nullptr) || GetLastError() == ERROR_SERVICE_ALREADY_RUNNING) {
            try { wait(service, SERVICE_RUNNING); } catch (...) {}
            // SERVICE_RUNNING precedes the spooler's RPC endpoint and monitor
            // loading. Wait until it answers, or the printer helper started
            // next races it (RPC unavailable / invalid printer name).
            for (int i = 0; i < 600; ++i) {
                DWORD bytes = 0, count = 0;
                if (EnumPrintersW(PRINTER_ENUM_LOCAL, nullptr, 4, nullptr, 0, &bytes, &count) ||
                    GetLastError() == ERROR_INSUFFICIENT_BUFFER) break;
                Sleep(100);
            }
        }
    }
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
static int run(int argc, wchar_t** argv) {
    try {
        if (argc < 2 || std::wstring(argv[1]) != L"/elevated-printer") return installer(argc, argv);
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
        const bool staleMonitor = installed_is_stale(102, monitor);
        {
            std::unique_ptr<SpoolerRestart> spooler;
            if (staleMonitor) spooler = std::make_unique<SpoolerRestart>();
            deploy(101, helper);
            deploy(102, monitor);
            if (spooler) spooler->restart();
        }
        // Setup may be launched from Downloads. Only the fixed, verified
        // Program Files executable is used for the privileged printer operation.
        std::wstring command = L"\"" + vr::program() + L"\\PrinterSetup.exe\" " + action + L" " + sid;
        std::vector<wchar_t> mutableCommand(command.begin(), command.end());
        mutableCommand.push_back(0);
        STARTUPINFOW start{}; start.cb = sizeof(start); PROCESS_INFORMATION process{};
        vr::check(CreateProcessW((vr::program() + L"\\PrinterSetup.exe").c_str(), mutableCommand.data(),
            nullptr, nullptr, FALSE, 0, nullptr, vr::system_directory().c_str(), &start, &process));
        vr::Handle thread(process.hThread), child(process.hProcess);
        vr::check(WaitForSingleObject(child.value, 300000) == WAIT_OBJECT_0);
        DWORD code = 0; vr::check(GetExitCodeProcess(child.value, &code));
        return static_cast<int>(code);
    } catch (...) {
        std::wcerr << L"Deployment refused: unsafe destination, changed installed bytes, or insufficient privileges. No ACLs were repaired.\n";
        return 1;
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
