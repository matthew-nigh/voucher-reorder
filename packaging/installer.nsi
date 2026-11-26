; SPDX-License-Identifier: GPL-3.0-or-later
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!ifndef STAGE
  !error "Pass DSTAGE"
!endif
!ifndef OUTPUT
  !error "Pass DOUTPUT"
!endif
!ifndef VERSION
  !error "Pass DVERSION (major.minor.patch)"
!endif
VIProductVersion "${VERSION}.0"
VIFileVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Voucher Reorder"
VIAddVersionKey "CompanyName" "M. Nigh"
VIAddVersionKey "LegalCopyright" "Copyright (C) M. Nigh"
VIAddVersionKey "FileDescription" "Voucher Reorder per-user installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
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
Var Mode
Var HandoffRadio
Var ImagesetterRadio
Var PdfRadio
Var Description
Var Dialog
Page custom OptionsPage OptionsLeave
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
  Call SelectMode
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Voucher Reorder"
FunctionEnd
Function OptionsPage
  !insertmacro MUI_HEADER_TEXT "Choose printing mode" "The app is always installed for this user."
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $Dialog == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 12u "Select a printing option:"
  Pop $0
  ${NSD_CreateGroupBox} 0 14u 100% 70u "Printing option"
  Pop $0
  ${NSD_CreateRadioButton} 10u 29u 95% 12u "PDF handoff (no administrator needed)"
  Pop $HandoffRadio
  ${NSD_CreateRadioButton} 10u 45u 95% 12u "Virtual printer with Imagesetter (recommended; requires administrator)"
  Pop $ImagesetterRadio
  ${NSD_CreateRadioButton} 10u 61u 95% 12u "Virtual printer with Microsoft Print to PDF (requires administrator)"
  Pop $PdfRadio
  ${If} $Mode == "imagesetter"
    ${NSD_Check} $ImagesetterRadio
  ${ElseIf} $Mode == "pdf"
    ${NSD_Check} $PdfRadio
  ${Else}
    ${NSD_Check} $HandoffRadio
  ${EndIf}
  ${NSD_CreateGroupBox} 0 89u 100% 83u "Description"
  Pop $0
  ${NSD_CreateLabel} 10u 104u 95% 63u ""
  Pop $Description
  ${NSD_OnClick} $HandoffRadio ModeClicked
  ${NSD_OnClick} $ImagesetterRadio ModeClicked
  ${NSD_OnClick} $PdfRadio ModeClicked
  Call SelectedDescription
  ${NSD_CreateTimer} HoverDescription 100
  nsDialogs::Show
  ${NSD_KillTimer} HoverDescription
FunctionEnd
Function ModeClicked
  Pop $0
  Call SelectedDescription
FunctionEnd
Function SelectedDescription
  ${NSD_GetState} $ImagesetterRadio $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $1 "imagesetter"
  ${Else}
    ${NSD_GetState} $PdfRadio $0
    ${If} $0 == ${BST_CHECKED}
      StrCpy $1 "pdf"
    ${Else}
      StrCpy $1 "handoff"
    ${EndIf}
  ${EndIf}
  Call ShowDescription
FunctionEnd
Function HoverDescription
  System::Alloc 8
  Pop $0
  System::Call 'user32::GetCursorPos(p r0)'
  System::Call '*$0(i .r2, i .r3)'
  System::Free $0
  System::Call 'user32::WindowFromPoint(i r2, i r3) p.r0'
  ${If} $0 == $HandoffRadio
    StrCpy $1 "handoff"
  ${ElseIf} $0 == $ImagesetterRadio
    StrCpy $1 "imagesetter"
  ${ElseIf} $0 == $PdfRadio
    StrCpy $1 "pdf"
  ${Else}
    Call SelectedDescription
    Return
  ${EndIf}
  Call ShowDescription
FunctionEnd
Function ShowDescription
  ${If} $1 == "imagesetter"
    ${NSD_SetText} $Description "Recommended virtual-printer approach. Requires administrator approval once. Installs the protected printer helper and a Voucher Reorder printer that gives each job a unique file, so back-to-back checks are not overwritten."
  ${ElseIf} $1 == "pdf"
    ${NSD_SetText} $Description "Requires administrator approval once. Uses the built-in Microsoft Print to PDF driver. Jobs printed back to back may overlap, overwrite, or be lost. Check Job status for warnings and reprint missing checks. Prefer Imagesetter when every check must be kept."
  ${Else}
    ${NSD_SetText} $Description "Installs for this user only; no administrator needed. Print from QuickBooks to Microsoft Print to PDF, save in the Inbox shown in Settings, or use Print a PDF. Enable a virtual printer later by rerunning Setup or, once the helper is installed, from Settings."
  ${EndIf}
FunctionEnd
Function OptionsLeave
  ${NSD_GetState} $ImagesetterRadio $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $Mode "imagesetter"
    Return
  ${EndIf}
  ${NSD_GetState} $PdfRadio $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $Mode "pdf"
  ${Else}
    StrCpy $Mode "handoff"
  ${EndIf}
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
  ${If} $Mode != "handoff"
    ${If} $Mode == "pdf"
      StrCpy $2 "setup-pdf"
    ${Else}
      StrCpy $2 "setup"
    ${EndIf}
    nsExec::ExecToStack '"$Candidate\runtime\python.exe" "$Candidate\packaging\mode_setup.py" $2 --installer'
    Pop $0
    Pop $1
    DetailPrint "$1"
    ${If} $0 != 0
      SetErrorLevel 1
      IfSilent +2
      MessageBox MB_ICONEXCLAMATION "$1"
    ${EndIf}
  ${EndIf}
SectionEnd
Section "-Start notification watcher"
  Exec '"$Candidate\runtime\pythonw.exe" "$Candidate\app.py" register'
SectionEnd
Function SelectMode
  StrCpy $Mode "handoff"
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/VIRTUAL=" $1
  ${If} $1 == "1"
    StrCpy $Mode "imagesetter"
  ${ElseIf} $1 == "pdf"
    StrCpy $Mode "pdf"
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
