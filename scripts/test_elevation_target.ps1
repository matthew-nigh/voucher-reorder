# Run before any helper is deployed. A forged Setup path in AppData must be refused.
$ErrorActionPreference = 'Stop'
$helper = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPrinter\PrinterSetup.exe'
if (Test-Path $helper) { throw 'Elevation target check must run before printer deployment' }
$fake = Join-Path $env:LOCALAPPDATA 'VoucherReorder\Fake-Setup.exe'
New-Item -ItemType Directory (Split-Path $fake) -Force | Out-Null
[IO.File]::WriteAllBytes($fake, [byte[]]@(77,90))
try {
    $env:VOUCHER_REORDER_SETUP_IMAGE = $fake
    $script = (Resolve-Path (Join-Path $PSScriptRoot '..\packaging\request_printer.ps1')).Path
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $script + '" -Action install -Installer'
    $process = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 11) { throw "AppData elevation target was not refused: $($process.ExitCode)" }
    Write-Output 'PASS: AppData Setup image rejected before elevation (code 11)'
} finally {
    Remove-Item Env:\VOUCHER_REORDER_SETUP_IMAGE -ErrorAction SilentlyContinue
    Remove-Item $fake -ErrorAction SilentlyContinue
}
