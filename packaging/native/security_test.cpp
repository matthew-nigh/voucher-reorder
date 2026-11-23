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
    try {
        if (argc == 3 && std::wstring(argv[1]) == L"--reject") { reject(argv[2]); return 0; }
        vr::check(argc == 1);
        vr::check(vr::account_sid(L"S-1-5-21-1-2-3-1001"));
        for (auto bad : {L"S-1-5-18", L"S-1-5-32-544", L"S-1-5-21-1-2-3-1001\\..", L"../../victim"})
            vr::check(!vr::account_sid(bad));
        auto root = vr::known(FOLDERID_ProgramData) + L"\\VoucherReorderSecurityTest";
        {
            vr::LockedTree tree(root, true);
            // Held directory handle forbids replacement, even to an admin.
            vr::check(!MoveFileExW(root.c_str(), (root + L"-moved").c_str(), 0));
            vr::Descriptor unsafe(L"O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;BU)");
            SECURITY_ATTRIBUTES sa{sizeof(sa), unsafe.value, FALSE};
            auto child = root + L"\\writable";
            vr::check(CreateDirectoryW(child.c_str(), &sa));
            reject(child); // Must refuse, never repair a pre-existing user-writable directory.
            vr::check(RemoveDirectoryW(child.c_str()));
            // A restricted desktop token cannot plant a file, directory or redirect.
            HANDLE token = nullptr, limited = nullptr;
            vr::check(OpenProcessToken(GetCurrentProcess(), TOKEN_DUPLICATE | TOKEN_QUERY, &token));
            vr::Handle tokenGuard(token);
            PSID admins = nullptr; vr::check(ConvertStringSidToSidW(L"S-1-5-32-544", &admins));
            SID_AND_ATTRIBUTES disable{admins, 0};
            BOOL ok = CreateRestrictedToken(token, DISABLE_MAX_PRIVILEGE, 1, &disable, 0, nullptr, 0, nullptr, &limited);
            LocalFree(admins); vr::check(ok); vr::Handle limitedGuard(limited);
            vr::check(ImpersonateLoggedOnUser(limited));
            BOOL made = CreateDirectoryW((root + L"\\planted").c_str(), nullptr);
            HANDLE file = CreateFileW((root + L"\\planted.pdf").c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, 0, nullptr);
            BOOL reverted = RevertToSelf();
            vr::Handle fileGuard(file);
            vr::check(reverted && !made && file == INVALID_HANDLE_VALUE);
        }
        vr::check(RemoveDirectoryW(root.c_str()));
        std::wcout << L"PASS: canonical SID, ACL refusal, held-directory replacement, restricted-token writes\n";
        return 0;
    } catch (...) { std::wcerr << L"Native security regression failed\n"; return 1; }
}
