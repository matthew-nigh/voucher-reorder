# Exercise the privileged script without modifying the hosted runner's print system.
$ErrorActionPreference = 'Stop'
$script:printer = $null; $script:port = $false; $script:fail = $false
function Get-Printer { param($Name,$ErrorAction) return $script:printer }
function Get-PrinterPort { param($Name,$ErrorAction) if ($script:port) { return @{Name=$Name} } }
function Get-PrinterDriver { param($Name,$ErrorAction) return @{Name=$Name} }
function Add-PrinterPort { param($Name,$LprHostAddress,$LprQueueName,[switch]$LprByteCounting)
    if ($LprHostAddress -ne '127.0.0.1' -or $LprQueueName -ne 'voucher' -or -not $LprByteCounting) { throw 'Wrong capture port' }
    $script:port=$true
}
function Add-Printer { param($Name,$DriverName,$PortName,$Comment)
    if ($script:fail) { throw 'Simulated driver refusal' }
    $script:printer=[pscustomobject]@{Name=$Name; DriverName=$DriverName; PortName=$PortName; Comment=$Comment}
}
function Set-PrintConfiguration { param($PrinterName,$PaperSize,$DuplexingMode) }
function Set-Printer { param($Name,$PermissionSDDL)
    if ($PermissionSDDL -notmatch 'S-1-5-21-1-2-3-1001') { throw 'Original user not granted print permission' }
}
function Remove-Printer { param($Name,$ErrorAction) $script:printer=$null }
function Remove-PrinterPort { param($Name,$ErrorAction) $script:port=$false }
function Get-PrintJob { param($PrinterName) }
function Test-Path { param($Path) return $true }
function Get-Item { param($Path) return @{VersionInfo=@{FileVersionRaw=[version]'99.0.0.0'}} }
# The success/removal paths do not show dialogs. Error UI is covered by Python fallback tests.
& "$PSScriptRoot\..\packaging\printer.ps1" -Action install -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 0 -or -not $script:printer -or -not $script:port) { throw 'Virtual setup failed' }
& "$PSScriptRoot\..\packaging\printer.ps1" -Action install -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 0) { throw 'Existing owned printer was not upgrade-safe' }
& "$PSScriptRoot\..\packaging\printer.ps1" -Action remove -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 0 -or $script:printer -or $script:port) { throw 'Virtual cleanup failed' }
Write-Output 'Virtual printer setup, original-user permission, reuse and cleanup passed with mocked printer APIs.'
