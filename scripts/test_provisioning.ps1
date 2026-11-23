# Real migration to the protected unique-job port and native helper lifecycle.
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
# Test-only trusted build staging. Production admins independently verify release
# provenance and checksums AFTER staging in an admin-protected directory.
$staging=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPackageTest'
New-Item -ItemType Directory -Path $staging -ErrorAction Stop | Out-Null
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
$acl.SetAccessRuleProtection($true,$false)
foreach ($sid in @('S-1-5-18','S-1-5-32-544')) {
    $identity=New-Object Security.Principal.SecurityIdentifier($sid)
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
}
Set-Acl -LiteralPath $staging -AclObject $acl
try {
    $deploy=Join-Path $staging 'PrinterDeploy.exe'
    Copy-Item (Join-Path $PSScriptRoot '..\build\printer\PrinterDeploy.exe') $deploy
    $fileAcl=Get-Acl -LiteralPath $deploy
    $fileAcl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    Set-Acl -LiteralPath $deploy -AclObject $fileAcl
    & $deploy
    if ($LASTEXITCODE) { throw 'Protected package deployment failed' }
} finally { Remove-Item -LiteralPath $staging -Recurse -Force }
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$securePort="VoucherReorder:$sid"
Setup $Installer $true # historical v0.2.0 fixture, not shipped by the new installer
if ((Get-Printer -Name 'Voucher Reorder').DriverName -ne 'MS Publisher Imagesetter') { throw 'Legacy fixture missing' }
Setup $UpgradeInstaller $false
$config=Get-Content (Join-Path $data 'settings.json') -Raw | ConvertFrom-Json
if ($config.mode -ne 'pdf') { throw 'Legacy upgrade must fall back without elevation' }
Setup $UpgradeInstaller $true
$current=Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
if ($current.version -ne '0.2.6') { throw 'Wrong upgraded version' }
$app=Join-Path $root ('deployments\'+$current.directory)
$python=Join-Path $app 'runtime\python.exe'
$printer=Get-Printer -Name 'Voucher Reorder'
if ($printer.DriverName -ne 'Microsoft Print To PDF' -or $printer.PortName -ne $securePort) {
    Get-Content (Join-Path $data 'mode-status.txt') -ErrorAction SilentlyContinue
    throw 'Protected-port clone setup failed'
}
if (-not (Test-Path (Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPrinter\PrinterSetup.exe'))) { throw 'Protected helper missing' }
Write-Output 'Clone configured; beginning real document prints'
& (Join-Path $PSScriptRoot 'test_clone_printer.ps1') -AppRoot $app
if ($LASTEXITCODE) { throw 'Clone acceptance failed' }
# Removal elevates the protected native helper directly.
& $python (Join-Path $app 'packaging\mode_setup.py') remove --ui
$removeExit = $LASTEXITCODE
$remainingPrinter = @(Get-Printer -ErrorAction Stop | Where-Object Name -eq 'Voucher Reorder')
$remainingPort = @(Get-PrinterPort -ErrorAction Stop | Where-Object Name -eq $securePort)
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
