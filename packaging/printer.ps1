param([Parameter(Mandatory)][ValidateSet('install','remove')][string]$Action,
      [Parameter(Mandatory)][ValidatePattern('^S-1-5-21-(?:[0-9]+-){3}[0-9]+$|^S-1-12-1-(?:[0-9]+-){3}[0-9]+$')][string]$TargetSid,
      [switch]$NoDialogs)
$ErrorActionPreference = 'Stop'
$name = 'Voucher Reorder'
$port = 'NUL:'
$driver = 'MS Publisher Imagesetter'
$owner = "VoucherReorder owner=$TargetSid"
try {
    $printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
    if ($printer -and ($printer.Comment -ne $owner -or $printer.DriverName -ne $driver -or
        $printer.PortName -notin @($port,'VoucherReorder_LPR'))) { throw 'Printer ownership mismatch.' }
    if ($printer -and ($Action -eq 'remove' -or $printer.PortName -ne $port)) {
        if (Get-PrintJob -PrinterName $name) { throw 'Reconcile and cancel pending jobs before migration.' }
        Remove-Printer -Name $name
        if ($printer.PortName -eq 'VoucherReorder_LPR') { Remove-PrinterPort -Name $printer.PortName }
        $printer = $null
    }
    if ($Action -eq 'remove') { exit 0 }
    $existing = Get-PrinterPort -Name $port -ErrorAction SilentlyContinue
    if ($existing -and $existing.PortMonitor -ne 'Local Port') { throw 'Unexpected port monitor.' }
    if (-not $existing) { Add-PrinterPort -Name $port }
    if (-not (Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue)) { Add-PrinterDriver -Name $driver }
    $acl = "O:BAG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;SWRC;;;$TargetSid)(A;OIIO;GA;;;$TargetSid)"
    if (-not $printer) {
        Add-Printer -Name $name -PortName $port -DriverName $driver -Comment $owner -PermissionSDDL $acl -KeepPrintedJobs -Datatype RAW
    } else {
        Set-Printer -Name $name -PermissionSDDL $acl -KeepPrintedJobs $true -Shared $false -Datatype RAW
    }
    Set-PrintConfiguration -PrinterName $name -PaperSize Letter -DuplexingMode OneSided
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
