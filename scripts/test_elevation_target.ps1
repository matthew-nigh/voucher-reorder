# Run before any helper is deployed. A forged Setup path in AppData must be refused.
$ErrorActionPreference = 'Stop'
$helper = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPrinter\PrinterSetup.exe'
if (Test-Path $helper) { throw 'Elevation target check must run before printer deployment' }
$fake = Join-Path $env:LOCALAPPDATA 'VoucherReorder\Fake-Setup.exe'
New-Item -ItemType Directory (Split-Path $fake) -Force | Out-Null
[IO.File]::WriteAllBytes($fake, [byte[]]@(77,90))
try {
    $env:VOUCHER_REORDER_SETUP_IMAGE = $fake
    & (Join-Path $PSHOME 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot '..\packaging\request_printer.ps1') -Action install -Installer
    if ($LASTEXITCODE -ne 11) { throw "AppData elevation target was not refused: $LASTEXITCODE" }
} finally {
    Remove-Item Env:\VOUCHER_REORDER_SETUP_IMAGE -ErrorAction SilentlyContinue
    Remove-Item $fake -ErrorAction SilentlyContinue
}
