Unicode True
Name "Voucher Reorder Printer Provisioning"
RequestExecutionLevel admin
OutFile "${OUTPUT}"
Section
  SetOutPath "$PROGRAMFILES64\Voucher Reorder Provisioning"
  File "${HELPER}"
  File "printer.ps1"
  File "raw_spool.ps1"
SectionEnd
