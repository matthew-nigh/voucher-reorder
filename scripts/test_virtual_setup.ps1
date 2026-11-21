# Exercise provisioning decisions against isolated printer API doubles.
$ErrorActionPreference = 'Stop'
$temp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
Copy-Item "$PSScriptRoot\..\packaging\printer.ps1" $temp
Set-Content (Join-Path $temp 'raw_spool.ps1') '$global:rawConfigured = $true'
$global:printer = $null
$global:port = $false
$sid = 'S-1-5-21-1-2-3-1001'
function Get-Printer { param($Name,$ErrorAction) $global:printer }
function Get-PrinterPort { param($Name,$ErrorAction) if ($global:port) { @{PortMonitor='Local Port'} } }
function Get-PrinterDriver { param($Name,$ErrorAction) @{Name=$Name} }
function Add-PrinterPort { param($Name) if ($Name -ne 'NUL:') { throw 'Wrong port' }; $global:port=$true }
function Add-Printer { param($Name,$PortName,$DriverName,$Comment,$PermissionSDDL,[switch]$KeepPrintedJobs,$Datatype)
    if ($PermissionSDDL -notlike "*$sid*" -or -not $KeepPrintedJobs -or $Datatype -ne 'RAW') { throw 'Unsafe queue' }
    $global:printer = @{Comment=$Comment; PortName=$PortName; DriverName=$DriverName}
}
function Set-Printer { param($Name,$PermissionSDDL,$KeepPrintedJobs,$Shared,$Datatype) }
function Set-PrintConfiguration { param($PrinterName,$PaperSize,$DuplexingMode) }
function Remove-Printer { param($Name) $global:printer=$null }
function Get-PrintJob { param($PrinterName) }
function Test-Path { param($Path) $true }
function Get-Item { param($Path) @{VersionInfo=@{FileVersionRaw=[version]'99.0.0.0'}} }
try {
    foreach ($operation in 'install','install','remove') {
        & "$temp\printer.ps1" -Action $operation -TargetSid $sid -NoDialogs
        if ($LASTEXITCODE) { throw "Unexpected $operation failure" }
    }
    if ($global:printer -or -not $global:rawConfigured) { throw 'Incorrect provisioning result' }
    $global:printer = @{Comment='foreign'; PortName='NUL:'; DriverName='MS Publisher Imagesetter'}
    & "$temp\printer.ps1" -Action remove -TargetSid $sid -NoDialogs
    if (-not $LASTEXITCODE -or -not $global:printer) { throw 'Foreign queue was removable' }
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
exit 0
