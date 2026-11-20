; SPDX-License-Identifier: GPL-3.0-or-later
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!ifndef STAGE
  !error "Pass /DSTAGE=absolute staging directory (Linux: -DSTAGE=...)"
!endif
!ifndef OUTPUT
  !error "Pass /DOUTPUT=installer path"
!endif
Name "Voucher Reorder"
OutFile "${OUTPUT}"
InstallDir "$PROGRAMFILES64\Voucher Reorder"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open Voucher Reorder Settings"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenSettings
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Voucher Reorder requires 64-bit Windows 10 or 11."
    Abort
  ${EndIf}
  SetRegView 64
  IfFileExists "$INSTDIR\*.*" 0 +3
    MessageBox MB_ICONSTOP "Uninstall the existing Voucher Reorder installation first."
    Abort
FunctionEnd

Function OpenSettings
  ; Explicitly launch using Explorer's unelevated token.
  Exec '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\app.py" desktop-settings'
FunctionEnd

Section "Install"
  SetRegView 64
  SetShellVarContext current
  SetOutPath "$PLUGINSDIR"
  File /oname=printer.ps1 "${STAGE}\packaging\printer.ps1"
  nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\printer.ps1" preflight'
  Pop $0
  Pop $1
  ${If} $0 != 0
    Abort "Printer preflight failed. See the setup message."
  ${EndIf}
  SetOutPath "$INSTDIR"
  File /r "${STAGE}\*"
  nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\packaging\printer.ps1" install'
  Pop $0
  Pop $1
  ${If} $0 != 0
    RMDir /r "$INSTDIR"
    Abort "Printer installation failed and app files were removed."
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Voucher Reorder"
  CreateShortCut "$SMPROGRAMS\Voucher Reorder\Settings.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\app.py" settings'
  CreateShortCut "$SMPROGRAMS\Voucher Reorder\User Guide.lnk" "$INSTDIR\USER_GUIDE.txt"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder" "DisplayName" "Voucher Reorder"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder" "DisplayVersion" "0.1.0"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder" "Publisher" "Voucher Reorder contributors"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetRegView 64
  SetShellVarContext current
  nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\packaging\printer.ps1" uninstall'
  Pop $0
  Pop $1
  ${If} $0 != 0
    Abort "Uninstall could not finish safely. See the setup message."
  ${EndIf}
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder"
  RMDir /r "$SMPROGRAMS\Voucher Reorder"
  RMDir /r "$INSTDIR"
SectionEnd
