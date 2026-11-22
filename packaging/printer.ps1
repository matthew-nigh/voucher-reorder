param([ValidateSet('install','remove')][string]$Action,
      [Parameter(Mandatory=$true)][string]$TargetSid,
      [Parameter(Mandatory=$true)][string]$IncomingPath,
      [switch]$NoDialogs)
$ErrorActionPreference = 'Stop'
$name = 'Voucher Reorder'
$driver = 'Microsoft Print To PDF'
$owner = "VoucherReorder owner=$TargetSid"
$port = [IO.Path]::GetFullPath($IncomingPath)
try {
    if ($TargetSid -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$' -or [IO.Path]::GetFileName($port) -ne 'job.pdf' -or $port.StartsWith('\\')) { throw 'Invalid per-user printer target.' }
    $printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
    if ($printer -and ($printer.Comment -ne $owner -or $printer.DriverName -notin @($driver,'MS Publisher Imagesetter'))) { throw 'Printer ownership mismatch.' }
    if ($printer -and ($Action -eq 'remove' -or $printer.DriverName -ne $driver -or $printer.PortName -ne $port)) {
        if (Get-PrintJob -PrinterName $name) { throw 'Reconcile and cancel pending jobs before migration.' }
        $oldPort = $printer.PortName
        Remove-Printer -Name $name
        # NUL: is a shared system port; never remove it. Remove only dedicated unused ports.
        if ($oldPort -ne 'NUL:' -and -not (Get-Printer | Where-Object PortName -eq $oldPort)) {
            Remove-PrinterPort -Name $oldPort -ErrorAction SilentlyContinue
        }
        $printer = $null
    }
    if ($Action -eq 'remove') { exit 0 }
    $folder = [IO.Path]::GetDirectoryName($port)
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { throw 'Incoming folder must be created by the desktop user first.' }
    # Spooler writes as SYSTEM; the desktop user owns the per-user folder.
    $acl = Get-Acl -LiteralPath $folder
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule('SYSTEM','FullControl','ContainerInherit,ObjectInherit','None','Allow')))
    Set-Acl -LiteralPath $folder -AclObject $acl
    if (-not (Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue)) { Add-PrinterDriver -Name $driver }
    $existing = Get-PrinterPort -Name $port -ErrorAction SilentlyContinue
    if ($existing -and $existing.PortMonitor -notin @('Local Monitor','Local Port')) { throw 'Unexpected port monitor.' }
    if (-not $existing) { Add-PrinterPort -Name $port }
    $permission = "O:BAG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;SWRC;;;$TargetSid)(A;OIIO;GA;;;$TargetSid)"
    if (-not $printer) {
        Add-Printer -Name $name -PortName $port -DriverName $driver -Comment $owner -PermissionSDDL $permission
        $madePrinter = $true
    } else {
        Set-Printer -Name $name -PermissionSDDL $permission -KeepPrintedJobs $false -Shared $false
    }
    Set-PrintConfiguration -PrinterName $name -PaperSize Letter -DuplexingMode OneSided
} catch {
    if ($madePrinter) { Remove-Printer -Name $name -ErrorAction SilentlyContinue }
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
