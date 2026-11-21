# Exercise the privileged script without modifying the hosted runner's print system.
$ErrorActionPreference = 'Stop'
function New-Object {
    param([string]$TypeName, [object[]]$ArgumentList)
    if ($TypeName -eq 'Net.Sockets.TcpListener') {
        $listener=[pscustomobject]@{}
        $listener | Add-Member ScriptMethod Start {}
        $listener | Add-Member ScriptMethod Stop {}
        return $listener
    }
    Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
}
$global:VoucherTestState = @{Printer=$null; Port=$false; Fail=$false}
function Get-Printer { param($Name,$ErrorAction) return $global:VoucherTestState.Printer }
function Get-PrinterPort { param($Name,$ErrorAction) if ($global:VoucherTestState.Port) { return @{Name=$Name} } }
function Get-PrinterDriver { param($Name,$ErrorAction) return @{Name=$Name} }
function Add-PrinterPort { param($Name,$LprHostAddress,$LprQueueName,[switch]$LprByteCounting)
    if ($LprHostAddress -ne '127.0.0.1' -or $LprQueueName -ne 'voucher' -or -not $LprByteCounting) { throw 'Wrong capture port' }
    $global:VoucherTestState.Port=$true
}
function Add-Printer { param($Name,$DriverName,$PortName,$Comment)
    if ($global:VoucherTestState.Fail) { throw 'Simulated driver refusal' }
    $global:VoucherTestState.Printer=[pscustomobject]@{Name=$Name; DriverName=$DriverName; PortName=$PortName; Comment=$Comment}
}
function Set-PrintConfiguration { param($PrinterName,$PaperSize,$DuplexingMode) }
function Set-Printer { param($Name,$PermissionSDDL)
    if ($PermissionSDDL -notmatch 'S-1-5-21-1-2-3-1001') { throw 'Original user not granted print permission' }
}
function Remove-Printer { param($Name,$ErrorAction) $global:VoucherTestState.Printer=$null }
function Remove-PrinterPort { param($Name,$ErrorAction) $global:VoucherTestState.Port=$false }
function Get-PrintJob { param($PrinterName) }
function Test-Path { param($Path) return $true }
function Get-Item { param($Path) return @{VersionInfo=@{FileVersionRaw=[version]'99.0.0.0'}} }
# The success/removal paths do not show dialogs. Error UI is covered by Python fallback tests.
& "$PSScriptRoot\..\packaging\printer.ps1" -Action install -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 0 -or -not $global:VoucherTestState.Printer -or -not $global:VoucherTestState.Port) { throw 'Virtual setup failed' }
& "$PSScriptRoot\..\packaging\printer.ps1" -Action install -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 0) { throw 'Existing owned printer was not upgrade-safe' }
& "$PSScriptRoot\..\packaging\printer.ps1" -Action remove -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 0 -or $global:VoucherTestState.Printer -or $global:VoucherTestState.Port) { throw 'Virtual cleanup failed' }
Write-Output 'Virtual printer setup, original-user permission, reuse and cleanup passed with mocked printer APIs.'
$global:VoucherTestState.Fail=$true
& "$PSScriptRoot\..\packaging\printer.ps1" -Action install -TargetSid 'S-1-5-21-1-2-3-1001' -NoDialogs
if ($LASTEXITCODE -ne 1 -or $global:VoucherTestState.Port -or $global:VoucherTestState.Printer) { throw 'Failed provisioning did not roll back its port' }
Write-Output 'Virtual driver failure rolls back without leaving a port.'
# Reset the expected failure's exit status for the workflow shell.
exit 0
