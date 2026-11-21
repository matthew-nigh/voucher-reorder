Unicode True
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
Name "Voucher Reorder Printer Provisioning"
RequestExecutionLevel admin
InstallDir "$PROGRAMFILES64\Voucher Reorder Provisioning"
OutFile "${OUTPUT}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Voucher Reorder Printer Provisioning"
VIAddVersionKey "FileVersion" "${VERSION}"
Var TargetSid
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Section
  SetRegView 64
  SetOutPath "$INSTDIR"
  File "${HELPER}"
  File "printer.ps1"
  File "raw_spool.ps1"
  FileOpen $0 "$INSTDIR\version.txt" w
  FileWrite $0 "${VERSION}"
  FileClose $0
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorderProvisioning" "DisplayName" "Voucher Reorder Printer Provisioning"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorderProvisioning" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorderProvisioning" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  ${GetParameters} $0
  ${GetOptions} $0 "/TARGETSID=" $TargetSid
  ${If} $TargetSid != ""
    ; Only the protected native launcher parses/validates the SID and runs scripts.
    ExecWait '$\"$INSTDIR\Provision.exe$\" install $TargetSid' $0
    ${If} $0 != 0
      SetErrorLevel 1
      Quit
    ${EndIf}
    WriteRegStr HKLM "Software\VoucherReorderProvisioning" "Owner" $TargetSid
  ${EndIf}
SectionEnd
Section "Uninstall"
  SetRegView 64
  ReadRegStr $TargetSid HKLM "Software\VoucherReorderProvisioning" "Owner"
  ${If} $TargetSid != ""
    ExecWait '$\"$INSTDIR\Provision.exe$\" remove $TargetSid' $0
    ${If} $0 != 0
      SetErrorLevel 1
      IfSilent +2
      MessageBox MB_ICONSTOP "Reconcile and cancel pending printer jobs before removing provisioning. The package was retained."
      Quit
    ${EndIf}
  ${EndIf}
  DeleteRegKey HKLM "Software\VoucherReorderProvisioning"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorderProvisioning"
  Delete "$INSTDIR\Provision.exe"
  Delete "$INSTDIR\printer.ps1"
  Delete "$INSTDIR\raw_spool.ps1"
  Delete "$INSTDIR\version.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
