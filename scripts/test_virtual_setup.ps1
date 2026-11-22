# Built-in printer decisions with API doubles: idempotence, migration, foreign queue protection.
$ErrorActionPreference='Stop'
$script=Join-Path $PSScriptRoot '..\packaging\printer.ps1'
$temp=Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$null=[IO.Directory]::CreateDirectory($temp)
$target=Join-Path $temp 'job.pdf'
$sid='S-1-5-21-1-2-3-1001'
$global:printer=$null
$global:port=$false
$global:pendingPrinter=$null
$global:printerReads=0
$global:latePrinterReads=0
$global:printerGoneOnce=$false
$global:busyRemovals=0
$global:removeCalls=0
$global:leavePort=$false
$global:restartCount=0
$global:restartClearsBusy=$false
function Start-Sleep { param($Milliseconds) } # Exercise bounded backoff without wall-clock delays.
function Restart-Service { param($Name,$ErrorAction)
    if ($Name -ne 'Spooler') { throw 'Wrong service restarted' }
    $global:restartCount++
    if ($global:restartClearsBusy) { $global:busyRemovals=0 }
}
function Get-Printer { param($Name,$ErrorAction)
    if ($global:printerReads -gt 0) {
        $global:printerReads--
        return $global:pendingPrinter
    }
    if (-not $global:printerGoneOnce -and $global:pendingPrinter) {
        $global:printerGoneOnce=$true
        return $null
    }
    if ($global:latePrinterReads -gt 0) {
        $global:latePrinterReads--
        return $global:pendingPrinter
    }
    $global:printer
}
function Get-PrinterPort { param($Name,$ErrorAction) if ($global:port) { @{Name=$target;PortMonitor='Local Monitor'} } }
function Get-PrinterDriver { param($Name,$ErrorAction) @{Name=$Name} }
function Add-PrinterPort { param($Name) if ($Name -ne $target) { throw 'Wrong fixed port' }; $global:port=$true }
function Add-Printer { param($Name,$PortName,$DriverName,$Comment,$PermissionSDDL)
    if ($DriverName -ne 'Microsoft Print To PDF' -or $PermissionSDDL -notlike "*$sid*") { throw 'Unsafe clone' }
    $global:printer=@{Name=$Name;Comment=$Comment; PortName=$PortName; DriverName=$DriverName}
}
function Set-Printer { param($Name,$PermissionSDDL,$KeepPrintedJobs,$Shared) if ($KeepPrintedJobs) { throw 'Retained jobs forbidden' } }
function Set-PrintConfiguration { param($PrinterName,$PaperSize,$DuplexingMode) }
function Remove-Printer { param($Name)
    $global:pendingPrinter=$global:printer
    $global:printerReads=3 # Simulate asynchronous queue disappearance.
    $global:latePrinterReads=if ($global:printer.PortName -eq $target) { 2 } else { 0 }
    $global:printerGoneOnce=$false
    $global:printer=$null
}
function Remove-PrinterPort { param($Name,$ComputerName,$ErrorAction)
    if ($Name -eq 'NUL:') { throw 'Shared system port removal attempted' }
    if (-not $ComputerName -or $ComputerName -ne $env:COMPUTERNAME) { throw 'Local print server was not specified' }
    $global:removeCalls++
    if ($global:busyRemovals -gt 0) { $global:busyRemovals--; throw 'Port handle is still busy' }
    if (-not $global:leavePort) { $global:port=$false }
}
function Get-PrintJob { param($PrinterName) }
try {
    $global:busyRemovals=3
    foreach ($operation in 'install','install','remove') {
        & $script -Action $operation -TargetSid $sid -IncomingPath $target -NoDialogs
        if ($LASTEXITCODE) { throw "Unexpected $operation failure" }
    }
    if ($global:printer -or $global:port -or $global:removeCalls -ne 4 -or $global:restartCount) { throw 'Incomplete bounded removal' }
    # An orphaned port from a prior partial removal must be retried too.
    $global:port=$true
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if ($LASTEXITCODE -or $global:port) { throw 'Orphan port remains' }
    # A successful cmdlet return is insufficient if the port is still listed.
    $global:port=$true; $global:leavePort=$true; $global:removeCalls=0; $global:restartCount=0
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if (-not $LASTEXITCODE -or -not $global:port -or $global:removeCalls -ne 60 -or $global:restartCount -ne 1) { throw 'Persistent port was reported removed' }
    $global:leavePort=$false
    # A spooler restart releases a port that remained busy through the first bound.
    $global:busyRemovals=40; $global:removeCalls=0; $global:restartCount=0; $global:restartClearsBusy=$true
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if ($LASTEXITCODE -or $global:port -or $global:removeCalls -ne 31 -or $global:restartCount -ne 1) { throw 'Spooler restart did not clear busy port' }
    $global:restartClearsBusy=$false; $global:port=$true
    # Persistent spooler errors must also fail after the bounded retry budget.
    $global:busyRemovals=70; $global:removeCalls=0; $global:restartCount=0
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if (-not $LASTEXITCODE -or $global:removeCalls -ne 60 -or $global:restartCount -ne 1) { throw 'Busy port did not fail within the bound' }
    $global:busyRemovals=0
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if ($LASTEXITCODE -or $global:port) { throw 'Retry after partial removal failed' }
    $global:printer=@{Name='Voucher Reorder';Comment="VoucherReorder owner=$sid";PortName='NUL:';DriverName='MS Publisher Imagesetter'}
    & $script -Action install -TargetSid $sid -IncomingPath $target
    if ($LASTEXITCODE -or $global:printer.DriverName -ne 'Microsoft Print To PDF') { throw 'Migration failed' }
    $global:printer=@{Name='Voucher Reorder';Comment='foreign';PortName='NUL:';DriverName='MS Publisher Imagesetter'}
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if (-not $LASTEXITCODE -or -not $global:printer) { throw 'Foreign queue was removable' }
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
exit 0
