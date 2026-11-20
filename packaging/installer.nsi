; SPDX-License-Identifier: GPL-3.0-or-later
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!ifndef STAGE
  !error "Pass DSTAGE"
!endif
!ifndef OUTPUT
  !error "Pass DOUTPUT"
!endif
Name "Voucher Reorder"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Voucher Reorder"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Var Candidate
Var Active
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open Voucher Reorder"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenSettings
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Voucher Reorder requires Windows 10 or 11 x64. ARM64 is not yet qualified."
    Abort
  ${EndIf}
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Voucher Reorder"
FunctionEnd
Function OpenSettings
  ReadINIStr $Active "$INSTDIR\current.ini" "app" "directory"
  Exec '"$INSTDIR\$Active\runtime\pythonw.exe" "$INSTDIR\$Active\app.py" settings'
FunctionEnd
Section "Install or upgrade"
  CreateDirectory "$INSTDIR\deployments"
  GetTempFileName $Candidate "$INSTDIR\deployments"
  Delete "$Candidate"
  ; NSIS-generated unique names become managed app-* directories.
  ${GetBaseName} "$Candidate" $0
  StrCpy $Candidate "$INSTDIR\deployments\app-$0"
  SetOutPath "$Candidate"
  File /r "${STAGE}\*"
  nsExec::ExecToStack '"$Candidate\runtime\python.exe" "$Candidate\packaging\manage_install.py" install --root "$INSTDIR" --candidate "$Candidate"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    RMDir /r "$Candidate"
    SetErrorLevel 1
    Abort "Update was not activated. The previous installation and settings were retained."
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ; Request admin ONLY for the optional printer. Cancellation leaves a working PDF app.
  IfSilent skipVirtual
  ExecWait '"$Candidate\runtime\pythonw.exe" "$Candidate\packaging\mode_setup.py" auto' $0
  skipVirtual:
SectionEnd
Function un.onInit
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
