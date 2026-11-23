// SPDX-License-Identifier: GPL-3.0-or-later
// Native acceptance harness. Never installed with the privileged helper.
#include "secure.hpp"
#include <iostream>

static void reject(const std::wstring& path) {
    bool refused = false;
    try { vr::LockedTree tree(path); } catch (...) { refused = true; }
    vr::check(refused);
}
int wmain(int argc, wchar_t** argv) {
    const wchar_t* stage = L"arguments";
    try {
        if (argc == 3 && std::wstring(argv[1]) == L"--reject") {
            stage = L"reject untrusted path"; reject(argv[2]); return 0;
        }
        vr::check(argc == 1);
        stage = L"canonical SID validation";
        vr::check(vr::account_sid(L"S-1-5-21-1-2-3-1001"));
        for (auto bad : {L"S-1-5-18", L"S-1-5-32-544", L"S-1-5-21-1-2-3-1001\\..", L"../../victim"})
            vr::check(!vr::account_sid(bad));
        auto root = vr::known(FOLDERID_ProgramFilesX64) + L"\\VoucherReorderSecurityTest";
        {
            stage = L"create and verify protected fixture";
            vr::LockedTree tree(root, true);
            // Held directory handle forbids replacement, even to an admin.
            stage = L"held directory replacement";
            vr::check(!MoveFileExW(root.c_str(), (root + L"-moved").c_str(), 0));
            vr::Descriptor unsafe(L"O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;BU)");
            SECURITY_ATTRIBUTES sa{sizeof(sa), unsafe.value, FALSE};
            auto child = root + L"\\writable";
            stage = L"create unsafe child";
            vr::check(CreateDirectoryW(child.c_str(), &sa));
            stage = L"reject unsafe child";
            reject(child); // Must refuse, never repair a pre-existing user-writable directory.
            stage = L"remove unsafe child";
            vr::check(RemoveDirectoryW(child.c_str()));
            // A restricted desktop token cannot plant a file, directory or redirect.
            HANDLE token = nullptr, limited = nullptr;
            stage = L"open process token";
            vr::check(OpenProcessToken(GetCurrentProcess(), TOKEN_DUPLICATE | TOKEN_QUERY, &token));
            vr::Handle tokenGuard(token);
            PSID admins = nullptr; vr::check(ConvertStringSidToSidW(L"S-1-5-32-544", &admins));
            SID_AND_ATTRIBUTES disable{admins, 0};
            stage = L"create restricted token";
            BOOL ok = CreateRestrictedToken(token, DISABLE_MAX_PRIVILEGE, 1, &disable, 0, nullptr, 0, nullptr, &limited);
            LocalFree(admins); vr::check(ok); vr::Handle limitedGuard(limited);
            stage = L"impersonate restricted token";
            vr::check(ImpersonateLoggedOnUser(limited));
            stage = L"reject restricted writes";
            BOOL made = CreateDirectoryW((root + L"\\planted").c_str(), nullptr);
            HANDLE file = CreateFileW((root + L"\\planted.pdf").c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, 0, nullptr);
            BOOL reverted = RevertToSelf();
            vr::Handle fileGuard(file);
            vr::check(reverted && !made && file == INVALID_HANDLE_VALUE);
        }
        stage = L"remove protected fixture";
        vr::check(RemoveDirectoryW(root.c_str()));
        std::wcout << L"PASS: canonical SID, ACL refusal, held-directory replacement, restricted-token writes\n";
        return 0;
    } catch (const std::exception& error) {
        std::wcerr << L"Native security regression failed at " << stage << L": " << error.what() << L"\n";
        return 1;
    } catch (...) {
        std::wcerr << L"Native security regression failed at " << stage << L"\n";
        return 1;
    }
}
