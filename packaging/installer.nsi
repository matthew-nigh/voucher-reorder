; SPDX-License-Identifier: GPL-3.0-or-later
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"
!ifndef STAGE
  !error "Pass DSTAGE"
!endif
!ifndef OUTPUT
  !error "Pass DOUTPUT"
!endif
!define MUI_ICON "${STAGE}\packaging\printer.ico"
!define MUI_UNICON "${STAGE}\packaging\printer.ico"
Name "Voucher Reorder"
Icon "${STAGE}\packaging\printer.ico"
UninstallIcon "${STAGE}\packaging\printer.ico"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Voucher Reorder"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Var Candidate
Var Active
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open Voucher Reorder"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenSettings
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!macro LockInstallation
  CreateDirectory "$LOCALAPPDATA\VoucherReorder"
  System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\VoucherReorder\installer.guard", i 0x40000000, i 0, p 0, i 4, i 128, p 0)p.r0'
  ${If} $0 == -1
    SetErrorLevel 1
    Abort "Another install or uninstall is running."
  ${EndIf}
  ; The OS closes this exclusive handle when the installer process exits.
!macroend
Function .onInit
  !insertmacro LockInstallation
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Voucher Reorder requires Windows 10 or 11 x64. ARM64 is not yet qualified."
    Abort
  ${EndIf}
  Call SelectVirtual
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Voucher Reorder"
FunctionEnd
Function OpenSettings
  ReadINIStr $Active "$INSTDIR\current.ini" "app" "directory"
  Exec '"$INSTDIR\$Active\runtime\pythonw.exe" "$INSTDIR\$Active\app.py" settings'
FunctionEnd
Section "Install or upgrade"
  SectionIn RO
  CreateDirectory "$INSTDIR\deployments"
  GetTempFileName $Candidate "$INSTDIR\deployments"
  Delete "$Candidate"
  ; NSIS-generated unique names become managed app-* directories.
  ${GetBaseName} "$Candidate" $0
  StrCpy $Candidate "$INSTDIR\deployments\app-$0"
  SetOutPath "$Candidate"
  ClearErrors
  File /r "${STAGE}\*"
  IfErrors stageFailed
  WriteUninstaller "$Candidate\Uninstall.next.exe"
  IfErrors stageFailed
  nsExec::ExecToStack '"$Candidate\runtime\python.exe" "$Candidate\packaging\manage_install.py" install --root "$INSTDIR" --candidate "$Candidate"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    stageFailed:
    RMDir /r "$Candidate"
    SetErrorLevel 1
    Abort "Update was not activated. The previous installation and settings were retained."
  ${EndIf}
SectionEnd
Section /o "Virtual printer (Recommended) - one administrator prompt" VirtualPrinter
  nsExec::ExecToStack '"$Candidate\runtime\python.exe" "$Candidate\packaging\mode_setup.py" setup'
  Pop $0
  Pop $1
  DetailPrint "$1"
  IfSilent +2
  MessageBox MB_ICONINFORMATION "$1"
SectionEnd
Section "-Start notification watcher"
  Exec '"$Candidate\runtime\pythonw.exe" "$Candidate\app.py" register'
SectionEnd
Function SelectVirtual
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/VIRTUAL=" $1
  ${If} $1 == "1"
    !insertmacro SelectSection ${VirtualPrinter}
  ${EndIf}
FunctionEnd
Function un.onInit
  !insertmacro LockInstallation
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Voucher Reorder"
FunctionEnd
Section "Uninstall"
  ReadINIStr $Active "$INSTDIR\current.ini" "app" "directory"
  IfSilent skipRemoveVirtual
  ExecWait '"$INSTDIR\$Active\runtime\pythonw.exe" "$INSTDIR\$Active\packaging\mode_setup.py" remove' $0
  skipRemoveVirtual:
  nsExec::ExecToStack '"$INSTDIR\$Active\runtime\python.exe" "$INSTDIR\$Active\packaging\manage_install.py" uninstall --root "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    SetErrorLevel 1
    Abort "Wait for printing to finish, then try uninstall again."
  ${EndIf}
  SetOutPath "$TEMP"
  RMDir /r "$INSTDIR\deployments"
  Delete "$INSTDIR\current.json"
  Delete "$INSTDIR\current.ini"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ; Keep user settings, Inbox originals and held jobs for a safe reinstall.
SectionEnd
