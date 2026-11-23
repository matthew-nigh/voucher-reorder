// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <sddl.h>
#include <aclapi.h>
#include <shlobj.h>
#include <string>
#include <vector>
#include <stdexcept>
#include <memory>
#include <cstring>

namespace vr {
inline void check(bool ok) { if (!ok) throw std::runtime_error("Protected printer operation failed"); }
struct Handle {
    HANDLE value = INVALID_HANDLE_VALUE;
    explicit Handle(HANDLE h = INVALID_HANDLE_VALUE) : value(h) {}
    ~Handle() { if (value != INVALID_HANDLE_VALUE && value) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};
struct Descriptor {
    PSECURITY_DESCRIPTOR value = nullptr;
    explicit Descriptor(const std::wstring& sddl) {
        check(ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &value, nullptr));
    }
    ~Descriptor() { LocalFree(value); }
};
inline std::wstring known(REFKNOWNFOLDERID id) {
    PWSTR p = nullptr;
    check(SUCCEEDED(SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, nullptr, &p)));
    std::wstring result(p); CoTaskMemFree(p); return result;
}
inline std::wstring program() { return known(FOLDERID_ProgramFilesX64) + L"\\VoucherReorderPrinter"; }
inline std::wstring system_directory() {
    wchar_t path[32768]; UINT n = GetSystemDirectoryW(path, 32768);
    check(n && n < 32768); return path;
}
inline std::wstring spool() { return known(FOLDERID_ProgramData) + L"\\VoucherReorderSpool"; }
inline bool account_sid(const std::wstring& text) {
    PSID sid = nullptr;
    if (!ConvertStringSidToSidW(text.c_str(), &sid)) return false;
    SID_IDENTIFIER_AUTHORITY nt = SECURITY_NT_AUTHORITY;
    bool ok = IsValidSid(sid) && *GetSidSubAuthorityCount(sid) == 5 &&
        !memcmp(GetSidIdentifierAuthority(sid), &nt, sizeof(nt)) && *GetSidSubAuthority(sid, 0) == 21;
    LPWSTR canonical = nullptr;
    if (ok && ConvertSidToStringSidW(sid, &canonical)) { ok = text == canonical; LocalFree(canonical); }
    else ok = false;
    LocalFree(sid); return ok;
}
inline bool trusted(PSID sid) {
    LPWSTR text = nullptr;
    check(ConvertSidToStringSidW(sid, &text));
    std::wstring s(text); LocalFree(text);
    return s == L"S-1-5-18" || s == L"S-1-5-32-544" ||
        s == L"S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"; // TrustedInstaller
}
inline std::wstring directory_acl(const std::wstring& reader = L"") {
    return L"O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)" +
        (reader.empty() ? L"" : L"(A;;GRGX;;;" + reader + L")");
}
inline void verify(HANDLE h, const std::wstring& path, bool ancestor = false) {
    BY_HANDLE_FILE_INFORMATION info{};
    check(GetFileInformationByHandle(h, &info));
    check(!(info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT));
    check((info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || info.nNumberOfLinks == 1);
    wchar_t finalPath[32768];
    DWORD n = GetFinalPathNameByHandleW(h, finalPath, 32768, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
    check(n && n < 32768);
    auto expected = L"\\\\?\\" + path;
    check(_wcsicmp(expected.c_str(), finalPath) == 0);
    PSID owner = nullptr; PACL acl = nullptr; PSECURITY_DESCRIPTOR sd = nullptr;
    check(GetSecurityInfo(h, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        &owner, nullptr, &acl, nullptr, &sd) == ERROR_SUCCESS);
    std::unique_ptr<void, decltype(&LocalFree)> freeSD(sd, LocalFree);
    check(owner && trusted(owner) && acl);
    for (DWORD i = 0; i < acl->AceCount; ++i) {
        void* raw = nullptr; check(GetAce(acl, i, &raw));
        auto header = static_cast<ACE_HEADER*>(raw);
        if (header->AceFlags & INHERIT_ONLY_ACE) continue;
        if (header->AceType == ACCESS_DENIED_ACE_TYPE) continue;
        check(header->AceType == ACCESS_ALLOWED_ACE_TYPE);
        auto ace = static_cast<ACCESS_ALLOWED_ACE*>(raw);
        if (trusted(&ace->SidStart)) continue;
        DWORD forbidden = DELETE | WRITE_DAC | WRITE_OWNER | FILE_DELETE_CHILD | GENERIC_ALL | GENERIC_WRITE |
            FILE_WRITE_EA | FILE_WRITE_ATTRIBUTES;
        if (!ancestor) forbidden |= FILE_WRITE_DATA | FILE_APPEND_DATA;
        check(!(ace->Mask & forbidden));
    }
}
// Each component is opened without following reparses and held without delete
// sharing until the operation ends. Never "repair" an untrusted existing ACL.
struct LockedTree {
    std::vector<std::unique_ptr<Handle>> handles;
    explicit LockedTree(const std::wstring& path, bool create = false, const std::wstring& reader = L"") {
        check(path.size() > 3 && path[1] == L':' && path[2] == L'\\');
        for (size_t end = 3; ; ) {
            auto part = path.substr(0, end);
            bool leaf = end == path.size();
            if (leaf && create) {
                Descriptor sd(directory_acl(reader));
                SECURITY_ATTRIBUTES sa{sizeof(sa), sd.value, FALSE};
                check(CreateDirectoryW(part.c_str(), &sa) || GetLastError() == ERROR_ALREADY_EXISTS);
            }
            auto h = std::make_unique<Handle>(CreateFileW(part.c_str(), READ_CONTROL | FILE_READ_ATTRIBUTES,
                FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
            check(h->value != INVALID_HANDLE_VALUE);
            verify(h->value, part, !leaf);
            handles.push_back(std::move(h));
            if (leaf) break;
            auto next = path.find(L'\\', end + (end == 3 ? 0 : 1));
            end = next == std::wstring::npos ? path.size() : next;
        }
    }
};
inline void set_dacl(HANDLE file, const std::wstring& sddl) {
    Descriptor sd(sddl); PACL acl = nullptr; BOOL present, defaults;
    check(GetSecurityDescriptorDacl(sd.value, &present, &acl, &defaults));
    check(SetSecurityInfo(file, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
        nullptr, nullptr, acl, nullptr) == ERROR_SUCCESS);
}
inline void protected_image() {
    wchar_t path[32768]; auto n = GetModuleFileNameW(nullptr, path, 32768);
    check(n && n < 32768);
    auto expected = program() + L"\\PrinterSetup.exe";
    check(_wcsicmp(expected.c_str(), path) == 0);
    Handle file(CreateFileW(path, READ_CONTROL | FILE_READ_ATTRIBUTES, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    check(file.value != INVALID_HANDLE_VALUE); verify(file.value, expected);
}
inline std::wstring port_sid(const std::wstring& port) {
    const std::wstring prefix = L"VoucherReorder:";
    check(port.compare(0, prefix.size(), prefix) == 0);
    auto sid = port.substr(prefix.size()); check(account_sid(sid)); return sid;
}
}
