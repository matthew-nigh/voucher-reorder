// SPDX-License-Identifier: GPL-3.0-or-later
// Installer-embedded bootstrap: deploy verified resources, then configure the printer.
#include "secure.hpp"
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
int wmain(int argc, wchar_t** argv) {
    try {
        vr::check(argc == 3);
        std::wstring action(argv[1]), sid(argv[2]);
        vr::check((action == L"install" || action == L"install-pdf") && vr::account_sid(sid));
        vr::LockedTree directory(vr::program(), true, L"BU");
        deploy(101, vr::program() + L"\\PrinterSetup.exe");
        // AddMonitor requires the DLL in System32. Deploy only our fixed name,
        // with the same no-reparse/ACL checks and embedded-byte verification.
        vr::LockedTree system(vr::system_directory());
        deploy(102, vr::system_directory() + L"\\VoucherReorderPort.dll");
        // The bootstrap may be launched from Downloads. Only the fixed, verified
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
