# Built-in printer decisions with API doubles: idempotence, migration, foreign queue protection.
$ErrorActionPreference='Stop'
$script=Join-Path $PSScriptRoot '..\packaging\printer.ps1'
$temp=Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$null=[IO.Directory]::CreateDirectory($temp)
$target=Join-Path $temp 'job.pdf'
$sid='S-1-5-21-1-2-3-1001'
$global:printer=$null
$global:port=$false
function Get-Printer { param($Name,$ErrorAction) $global:printer }
function Get-PrinterPort { param($Name,$ErrorAction) if ($global:port) { @{PortMonitor='Local Monitor'} } }
function Get-PrinterDriver { param($Name,$ErrorAction) @{Name=$Name} }
function Add-PrinterPort { param($Name) if ($Name -ne $target) { throw 'Wrong fixed port' }; $global:port=$true }
function Add-Printer { param($Name,$PortName,$DriverName,$Comment,$PermissionSDDL)
    if ($DriverName -ne 'Microsoft Print To PDF' -or $PermissionSDDL -notlike "*$sid*") { throw 'Unsafe clone' }
    $global:printer=@{Comment=$Comment; PortName=$PortName; DriverName=$DriverName}
}
function Set-Printer { param($Name,$PermissionSDDL,$KeepPrintedJobs,$Shared) if ($KeepPrintedJobs) { throw 'Retained jobs forbidden' } }
function Set-PrintConfiguration { param($PrinterName,$PaperSize,$DuplexingMode) }
function Remove-Printer { param($Name) $global:printer=$null }
function Remove-PrinterPort { param($Name,$ErrorAction) $global:port=$false }
function Get-PrintJob { param($PrinterName) }
try {
    foreach ($operation in 'install','install','remove') {
        & $script -Action $operation -TargetSid $sid -IncomingPath $target -NoDialogs
        if ($LASTEXITCODE) { throw "Unexpected $operation failure" }
    }
    if ($global:printer -or $global:port) { throw 'Incomplete removal' }
    $global:printer=@{Comment="VoucherReorder owner=$sid";PortName='NUL:';DriverName='MS Publisher Imagesetter'}
    & $script -Action install -TargetSid $sid -IncomingPath $target
    if ($LASTEXITCODE -or $global:printer.DriverName -ne 'Microsoft Print To PDF') { throw 'Migration failed' }
    $global:printer=@{Comment='foreign';PortName='NUL:';DriverName='MS Publisher Imagesetter'}
    & $script -Action remove -TargetSid $sid -IncomingPath $target
    if (-not $LASTEXITCODE -or -not $global:printer) { throw 'Foreign queue was removable' }
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
exit 0
