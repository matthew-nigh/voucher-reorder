param([ValidateSet('install','remove')][string]$Action,
      [Parameter(Mandatory=$true)][string]$TargetSid,
      [Parameter(Mandatory=$true)][string]$IncomingPath,
      [switch]$NoDialogs)
$ErrorActionPreference = 'Stop'
$name = 'Voucher Reorder'
$driver = 'Microsoft Print To PDF'
$owner = "VoucherReorder owner=$TargetSid"
$port = [IO.Path]::GetFullPath($IncomingPath)
# Bounded retries belong to this explicit setup action, never to the watcher.
function Wait-PrinterRemoved {
    $delay = 100
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $remaining = @(Get-Printer -ErrorAction Stop | Where-Object Name -eq $name)
        if (-not $remaining) { return }
        Start-Sleep -Milliseconds $delay
        $delay = [Math]::Min(1000, $delay * 2)
    }
    throw "Printer removal did not finish: $($remaining | ConvertTo-Json -Compress)"
}
function Remove-DedicatedPort([string]$PortName) {
    if ($PortName -eq 'NUL:') { return } # Shared system port, never ours to remove.
    $lastError = 'Port still listed after removal'
    $delay = 100
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
            # Enumerate with Stop: a query failure must not masquerade as absence.
            $remaining = @(Get-PrinterPort -ErrorAction Stop | Where-Object Name -eq $PortName)
            if (-not $remaining) { return }
            $users = @(Get-Printer -ErrorAction Stop | Where-Object PortName -eq $PortName)
            if ($users) {
                # Queue enumeration can lag behind Remove-Printer even after the
                # name lookup reports it gone. Never remove a port still in use.
                $lastError = "Port is still used by: $($users.Name -join ', ')"
                Start-Sleep -Milliseconds $delay
                $delay = [Math]::Min(1000, $delay * 2)
                continue
            }
            if ($remaining.PortMonitor | Where-Object { $_ -notin @('Local Monitor','Local Port') }) {
                throw "Unexpected monitor for dedicated port '$PortName'."
            }
            try {
                Remove-PrinterPort -Name $PortName -ComputerName $env:COMPUTERNAME -ErrorAction Stop
            } catch {
                # Remove-Printer returns before the spooler releases its port handle.
                $lastError = $_.Exception.Message
            }
            if (-not (Get-PrinterPort -ErrorAction Stop | Where-Object Name -eq $PortName)) { return }
            Start-Sleep -Milliseconds $delay
            $delay = [Math]::Min(1000, $delay * 2)
    }
    throw "Dedicated port '$PortName' remains after 30 removal attempts. The machine Spooler was not restarted. An administrator may restart it during planned maintenance, then retry removal. Last error: $lastError"
}
try {
    if ($TargetSid -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$' -or [IO.Path]::GetFileName($port) -ne 'job.pdf' -or $port.StartsWith('\\')) { throw 'Invalid per-user printer target.' }
    $printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
    if ($printer -and ($printer.Comment -ne $owner -or $printer.DriverName -notin @($driver,'MS Publisher Imagesetter'))) { throw 'Printer ownership mismatch.' }
    if ($printer -and ($Action -eq 'remove' -or $printer.DriverName -ne $driver -or $printer.PortName -ne $port)) {
        if (Get-PrintJob -PrinterName $name) { throw 'Reconcile and cancel pending jobs before migration.' }
        $oldPort = $printer.PortName
        Remove-Printer -Name $name
        Wait-PrinterRemoved
        Remove-DedicatedPort $oldPort
        $printer = $null
    }
    if ($Action -eq 'remove') {
        # Also finish a prior removal that deleted the queue but left its port.
        Remove-DedicatedPort $port
        exit 0
    }
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
