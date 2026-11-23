# Real legacy-to-fixed-port migration and built-in Windows printer lifecycle.
param([string]$Installer,[string]$UpgradeInstaller)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'Programs\Voucher Reorder'
$data = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
function Setup($path,$virtual) {
    Write-Output "Starting setup $([IO.Path]::GetFileName($path)); virtual=$virtual"
    $arguments = if ($virtual) { '/S /VIRTUAL=1' } else { '/S' }
    $p = Start-Process (Resolve-Path $path) -ArgumentList $arguments -PassThru
    # -Wait waits for descendants too, including the intentionally persistent watcher.
    if (-not $p.WaitForExit(120000)) { throw 'Installer process timed out' }
    if ($p.ExitCode) { throw "Setup failed: $($p.ExitCode)" }
    Write-Output 'Setup process exited'
    Get-Content (Join-Path $data 'mode-status.txt') -ErrorAction SilentlyContinue
}
Setup $Installer $true # historical v0.2.0 fixture, not shipped by the new installer
if ((Get-Printer -Name 'Voucher Reorder').DriverName -ne 'MS Publisher Imagesetter') { throw 'Legacy fixture missing' }
Setup $UpgradeInstaller $false
$config=Get-Content (Join-Path $data 'settings.json') -Raw | ConvertFrom-Json
if ($config.mode -ne 'pdf') { throw 'Legacy upgrade must fall back without elevation' }
Setup $UpgradeInstaller $true
$current=Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
if ($current.version -ne '0.2.4') { throw 'Wrong upgraded version' }
$app=Join-Path $root ('deployments\'+$current.directory)
$python=Join-Path $app 'runtime\python.exe'
$printer=Get-Printer -Name 'Voucher Reorder'
if ($printer.DriverName -ne 'Microsoft Print To PDF' -or $printer.PortName -ne (Join-Path $data 'Incoming\job.pdf')) {
    Get-Content (Join-Path $data 'mode-status.txt') -ErrorAction SilentlyContinue
    throw 'Fixed-port clone setup failed'
}
if (Test-Path (Join-Path $app 'provisioning\Setup.exe')) { throw 'Unsigned elevated package must not ship' }
Write-Output 'Clone configured; beginning real document prints'
& (Join-Path $PSScriptRoot 'test_clone_printer.ps1') -AppRoot $app
if ($LASTEXITCODE) { throw 'Clone acceptance failed' }
# Removal also elevates only the built-in PowerShell binary.
& $python (Join-Path $app 'packaging\mode_setup.py') remove --ui
$removeExit = $LASTEXITCODE
$remainingPrinter = @(Get-Printer -ErrorAction Stop | Where-Object Name -eq 'Voucher Reorder')
$remainingPort = @(Get-PrinterPort -ErrorAction Stop | Where-Object Name -eq (Join-Path $data 'Incoming\job.pdf'))
if ($removeExit -or $remainingPrinter -or $remainingPort) {
    Get-Content (Join-Path $data 'mode-status.txt') -ErrorAction SilentlyContinue
    $remainingPrinter | Format-List * | Out-String | Write-Output
    $remainingPort | Format-List * | Out-String | Write-Output
    Get-Service Spooler | Format-List * | Out-String | Write-Output
    throw "Removal failed: exit=$removeExit; remaining printers=$($remainingPrinter.Count); dedicated ports=$($remainingPort.Count)"
}
$p=Start-Process (Join-Path $root 'Uninstall.exe') -ArgumentList '/S' -Wait -PassThru
if ($p.ExitCode) { throw 'App uninstall failed' }
Write-Output 'PASS: old queue migration, no-admin fallback, clone create/print/remove, app uninstall'
exit 0
