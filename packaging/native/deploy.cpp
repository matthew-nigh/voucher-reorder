// SPDX-License-Identifier: GPL-3.0-or-later
// Administrator runs this separately from independently verified release media.
// Its embedded resources, never files from the per-user installation, are deployed.
#include "secure.hpp"
#include <cstring>
#include <iostream>

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
int wmain(int argc, wchar_t**) {
    try {
        vr::check(argc == 1);
        // Bootstrap is never auto-launched by the per-user app. Require the
        // administrator's verified package to be staged under protected parents.
        wchar_t image[32768]; DWORD length = GetModuleFileNameW(nullptr, image, 32768);
        vr::check(length && length < 32768);
        std::wstring imagePath(image);
        vr::LockedTree staging(imagePath.substr(0, imagePath.find_last_of(L'\\')));
        vr::Handle package(CreateFileW(image, GENERIC_READ | READ_CONTROL, FILE_SHARE_READ, nullptr,
            OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
        vr::check(package.value != INVALID_HANDLE_VALUE); vr::verify(package.value, imagePath);
        vr::LockedTree directory(vr::program(), true, L"BU");
        deploy(101, vr::program() + L"\\PrinterSetup.exe");
        // AddMonitor requires the DLL in System32. Deploy only our fixed name,
        // with the same no-reparse/ACL checks and embedded-byte verification.
        vr::LockedTree system(vr::system_directory());
        deploy(102, vr::system_directory() + L"\\VoucherReorderPort.dll");
        std::wcout << L"Protected printer helper deployed and verified. Enable virtual printing from the desktop user's Settings.\n";
        return 0;
    } catch (...) {
        std::wcerr << L"Deployment refused: untrusted/reparse path, changed installed bytes, or insufficient privileges. No ACLs were repaired.\n";
        return 1;
    }
}
