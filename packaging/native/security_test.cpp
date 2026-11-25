// SPDX-License-Identifier: GPL-3.0-or-later
// Native acceptance harness. Never installed with the privileged helper.
#include "secure.hpp"
#include <winspool.h>
#include <iostream>

static void reject(const std::wstring& path) {
    bool refused = false;
    try { vr::LockedTree tree(path); } catch (...) { refused = true; }
    vr::check(refused);
}
static void check_port(const std::wstring& port, const wchar_t* monitor, bool expected) {
    std::vector<BYTE> buffer(1024 * 1024);
    DWORD bytes = 0, count = 0;
    for (;;) {
        if (EnumPortsW(nullptr, 2, buffer.data(), static_cast<DWORD>(buffer.size()), &bytes, &count)) break;
        DWORD error = GetLastError();
        if (error == ERROR_INSUFFICIENT_BUFFER && bytes > buffer.size() && bytes < 16 * 1024 * 1024) {
            buffer.resize(bytes); continue;
        }
        std::wcerr << L"EnumPortsW failed with Windows error " << error << L", bytes=" << bytes << L"\n";
        vr::check(false);
    }
    vr::check(count <= buffer.size() / sizeof(PORT_INFO_2W));
    auto entries = reinterpret_cast<PORT_INFO_2W*>(buffer.data());
    bool found = false;
    std::wstring owner;
    for (DWORD i = 0; i < count; ++i) {
        if (entries[i].pPortName && !_wcsicmp(entries[i].pPortName, port.c_str())) {
            vr::check(!found);
            found = true;
            if (entries[i].pMonitorName) owner = entries[i].pMonitorName;
        }
    }
    if (found != expected || (found && monitor && _wcsicmp(owner.c_str(), monitor)))
        std::wcerr << L"Port check: found=" << found << L", monitor=" << owner
                   << L", enumerated=" << count << L"\n";
    vr::check(found == expected);
    if (found && monitor) vr::check(!_wcsicmp(owner.c_str(), monitor));
}
// Whole-system EnumPortsW health with whatever monitors are installed. Fails
// on any error, a size/count disagreement, an undersized buffer that is not
// reported as ERROR_INSUFFICIENT_BUFFER, or a string pointing outside the buffer.
static void check_enumeration() {
    for (DWORD level : {1u, 2u}) {
        DWORD need = 0, count = 0;
        vr::check(!EnumPortsW(nullptr, level, nullptr, 0, &need, &count) && GetLastError() == ERROR_INSUFFICIENT_BUFFER && need);
        DWORD bytes = 0;
        // Exact-size buffer, then a generously padded one; both must work.
        for (DWORD size : {need, need + 4096}) {
            std::vector<BYTE> buffer(size + 16);
            vr::check(EnumPortsW(nullptr, level, buffer.data(), size, &bytes, &count), "EnumPortsW failed with a sufficient buffer");
            vr::check(bytes <= size && count);
            DWORD record = level == 1 ? sizeof(PORT_INFO_1W) : sizeof(PORT_INFO_2W);
            vr::check(static_cast<size_t>(count) * record <= bytes);
            auto begin = buffer.data(), end = buffer.data() + size;
            auto inside = [&](const wchar_t* text) {
                if (!text) return true;
                auto p = reinterpret_cast<const BYTE*>(text);
                if (p < begin + static_cast<size_t>(count) * record || p >= end) return false;
                for (auto q = p; q + 1 < end; q += 2) if (!*reinterpret_cast<const wchar_t*>(q)) return true;
                return false;
            };
            for (DWORD i = 0; i < count; ++i) {
                if (level == 1) vr::check(inside(reinterpret_cast<PORT_INFO_1W*>(begin)[i].pName), "bad PORT_INFO_1 string");
                else {
                    auto& e = reinterpret_cast<PORT_INFO_2W*>(begin)[i];
                    vr::check(inside(e.pPortName) && inside(e.pMonitorName) && inside(e.pDescription), "bad PORT_INFO_2 string");
                }
            }
        }
        if (need > 1) {
            std::vector<BYTE> small(need - 1);
            vr::check(!EnumPortsW(nullptr, level, small.data(), need - 1, &bytes, &count) &&
                GetLastError() == ERROR_INSUFFICIENT_BUFFER && bytes >= need, "short buffer not reported");
        }
    }
}
int wmain(int argc, wchar_t** argv) {
    const wchar_t* stage = L"arguments";
    try {
        if (argc == 2 && std::wstring(argv[1]) == L"--enum-all") {
            stage = L"system-wide EnumPortsW levels 1 and 2"; check_enumeration(); return 0;
        }
        if (argc == 3 && std::wstring(argv[1]) == L"--reject") {
            stage = L"reject untrusted path"; reject(argv[2]); return 0;
        }
        if (argc == 4 && std::wstring(argv[1]) == L"--port") {
            stage = L"verify port and monitor with Win32 EnumPorts";
            check_port(argv[2], argv[3], true); return 0;
        }
        if (argc == 3 && std::wstring(argv[1]) == L"--port-absent") {
            stage = L"verify retired port with Win32 EnumPorts";
            check_port(argv[2], nullptr, false); return 0;
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
