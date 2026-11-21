# Synthetic UI checks, isolated from any installed user's settings and printer setup.
param([string]$AppRoot=(Join-Path $PSScriptRoot '..\build\windows'))
$ErrorActionPreference='Stop'
$AppRoot=(Resolve-Path $AppRoot).Path
$previousData=$env:LOCALAPPDATA
$testData=Join-Path ([IO.Path]::GetTempPath()) ('VoucherSettings-'+[guid]::NewGuid().ToString('N'))
try {
    $env:LOCALAPPDATA=$testData
    $python=Join-Path $AppRoot 'runtime\python.exe'
    & $python -c "from voucher_reorder.config import *; save(data_dir()/'settings.json', Settings())"
    if ($LASTEXITCODE) { throw 'Could not initialize UI test settings' }
    foreach ($scale in @(1,1.5,2)) {
        foreach ($small in @($false,$true)) {
            $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $AppRoot 'packaging\settings.ps1'),'-SmokeTest','-SmokeScale',$scale)
            if ($small) { $arguments+='-SmokeSmall' }
            & (Join-Path $PSHOME 'powershell.exe') @arguments
            if ($LASTEXITCODE) { throw "Settings UI failed: scale=$scale small=$small" }
        }
    }
} finally {
    $env:LOCALAPPDATA=$previousData
    Remove-Item -LiteralPath $testData -Recurse -Force -ErrorAction SilentlyContinue
}
