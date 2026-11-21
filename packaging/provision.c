/* Native entry point installed and run only from the protected machine package. */
#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <shellapi.h>
#include <sddl.h>
#include <strsafe.h>

int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR args,int show) {
    WCHAR base[MAX_PATH], system[MAX_PATH], shell[MAX_PATH], command[2048], modules[1024];
    PWSTR *argv;
    int argc;
    PSID sid;
    DWORD status = 1;
    STARTUPINFOW startup = {sizeof(startup)};
    PROCESS_INFORMATION process = {0};
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32);
    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv || argc != 3 || (wcscmp(argv[1],L"install") && wcscmp(argv[1],L"remove"))) return 1;
    if (wcsncmp(argv[2],L"S-1-",4) || wcsspn(argv[2]+4,L"0123456789-") != wcslen(argv[2]+4)
        || !ConvertStringSidToSidW(argv[2], &sid)) return 1;
    LocalFree(sid);
    if (FAILED(SHGetFolderPathW(NULL,CSIDL_PROGRAM_FILES,NULL,0,base)) ||
        !GetSystemDirectoryW(system,MAX_PATH) ||
        FAILED(StringCchCatW(base,MAX_PATH,L"\\Voucher Reorder Provisioning")) ||
        !SetCurrentDirectoryW(base) ||
        FAILED(StringCchPrintfW(shell,MAX_PATH,L"%s\\WindowsPowerShell\\v1.0\\powershell.exe",system)) ||
        FAILED(StringCchPrintfW(modules,1024,L"%s\\WindowsPowerShell\\v1.0\\Modules",system)) ||
        FAILED(StringCchPrintfW(command,2048,L"\"%s\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%s\\printer.ps1\" -Action %s -TargetSid %s",shell,base,argv[1],argv[2]))) return 1;
    /* Start PowerShell with a fresh environment; never inherit CLR/profiler or module hooks. */
    WCHAR env[4096], windir[MAX_PATH]; size_t offset = 0;
    if (!GetWindowsDirectoryW(windir,MAX_PATH)) return 1;
    const WCHAR *keys[]={L"PATH",L"PSModulePath",L"SystemRoot",L"TEMP",L"TMP",L"windir"};
    const WCHAR *values[]={system,modules,windir,base,base,windir};
    for (int i=0;i<6;i++) {
        if (FAILED(StringCchPrintfW(env+offset,4095-offset,L"%s=%s",keys[i],values[i]))) return 1;
        offset += wcslen(env+offset)+1;
    }
    env[offset]=0;
    if (!CreateProcessW(shell,command,NULL,NULL,FALSE,CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW,
                        env,base,&startup,&process)) return 1;
    WaitForSingleObject(process.hProcess,INFINITE);
    GetExitCodeProcess(process.hProcess,&status);
    CloseHandle(process.hThread); CloseHandle(process.hProcess);
    return status;
}
