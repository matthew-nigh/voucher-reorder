// SPDX-License-Identifier: GPL-3.0-or-later
// The distributed Setup image: run the per-user NSIS UI or perform its elevated action.
#include "secure.hpp"
#include <shellapi.h>
#include <cstring>
#include <iostream>
#include <vector>

static void deploy(WORD id, const std::wstring& path) {
    auto resource = FindResourceW(nullptr, MAKEINTRESOURCEW(id), RT_RCDATA); vr::check(resource != nullptr);
    auto size = SizeofResource(nullptr, resource); vr::check(size != 0);
    auto bytes = LockResource(LoadResource(nullptr, resource)); vr::check(bytes != nullptr);
    vr::Descriptor sd(L"O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;BU)");
    SECURITY_ATTRIBUTES sa{sizeof(sa), sd.value, FALSE};
    vr::Handle file(CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE | READ_CONTROL, 0, &sa,
        CREATE_NEW, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    if (file.value == INVALID_HANDLE_VALUE && GetLastError() == ERROR_FILE_EXISTS) {
        file.value = CreateFileW(path.c_str(), GENERIC_READ | READ_CONTROL, FILE_SHARE_READ, nullptr,
            OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        vr::check(file.value != INVALID_HANDLE_VALUE); vr::verify(file.value, path);
        // An existing installation is accepted only if the deployed bytes match.
        // Updating loaded spooler code requires separate admin maintenance.
    } else {
        vr::check(file.value != INVALID_HANDLE_VALUE); DWORD written;
        vr::check(WriteFile(file.value, bytes, size, &written, nullptr) && written == size);
        vr::check(FlushFileBuffers(file.value));
    }
    vr::verify(file.value, path);
    LARGE_INTEGER actual{}, zero{}; vr::check(GetFileSizeEx(file.value, &actual) && actual.QuadPart == size);
    vr::check(SetFilePointerEx(file.value, zero, nullptr, FILE_BEGIN));
    std::vector<BYTE> copy(size); DWORD read;
    vr::check(ReadFile(file.value, copy.data(), size, &read, nullptr) && read == size && !memcmp(bytes, copy.data(), size));
}
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
        deploy(101, vr::program() + L"\\PrinterSetup.exe");
        // AddMonitor requires the DLL in System32. Deploy only our fixed name,
        // with the same no-reparse/ACL checks and embedded-byte verification.
        vr::LockedTree system(vr::system_directory());
        deploy(102, vr::system_directory() + L"\\VoucherReorderPort.dll");
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
