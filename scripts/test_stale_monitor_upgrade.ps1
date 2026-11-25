# Upgrade over a STALE, in-use Imagesetter install: the spooler holds an older
# VoucherReorderPort.dll mapped, and an older PrinterSetup.exe is held open.
# The new Setup (elevated /elevated-printer path) must stop the spooler, retry,
# rename the locked helper aside, write the new bytes, restart the spooler and
# finish with Imagesetter active.
param([string]$OldBuild = (Join-Path $PSScriptRoot '..\build\old-printer'))
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot '..\dist\VoucherReorder-0.2.6-Setup.exe'
$newBuild = Join-Path $PSScriptRoot '..\build\printer'
$data = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$helper = Join-Path $env:ProgramFiles 'VoucherReorderPrinter\PrinterSetup.exe'
$monitor = Join-Path $env:SystemRoot 'System32\VoucherReorderPort.dll'
function Hash($path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
function Run-Setup($label) {
    $p = Start-Process (Resolve-Path $installer) -ArgumentList '/S /VIRTUAL=1' -PassThru
    if (-not $p.WaitForExit(240000)) { try { $p.Kill() } catch {}; throw "$label Setup timed out" }
    $detail = Get-Content (Join-Path $data 'printer-setup-error.txt') -ErrorAction SilentlyContinue
    $code = Get-Content (Join-Path $data 'printer-setup-code.txt') -ErrorAction SilentlyContinue
    if ($p.ExitCode) { throw "$label Setup failed: exit=$($p.ExitCode) code=$code detail=$detail" }
}
foreach ($name in 'PrinterSetup.exe','VoucherReorderPort.dll') {
    if (-not (Test-Path (Join-Path $OldBuild $name))) { throw "Older build missing: $name" }
}
# 1. Imagesetter active with the current build.
Run-Setup 'Initial'
$printer = Get-Printer -Name 'Voucher Reorder'
if ($printer.DriverName -ne 'MS Publisher Imagesetter') { throw 'Imagesetter not active before stale simulation' }
# 2. Make both installed files stale (older build) while the spooler is stopped,
#    then let the spooler load the old monitor DLL.
Stop-Service Spooler -Force
Copy-Item (Join-Path $OldBuild 'VoucherReorderPort.dll') $monitor -Force
Copy-Item (Join-Path $OldBuild 'PrinterSetup.exe') $helper -Force
Start-Service Spooler
$spooler = Get-Process spoolsv
$loaded = $spooler.Modules | Where-Object { $_.ModuleName -eq 'VoucherReorderPort.dll' }
if (-not $loaded) { throw 'Spooler did not load the stale monitor DLL' }
if ((Hash $monitor) -ne (Hash (Join-Path $OldBuild 'VoucherReorderPort.dll'))) { throw 'Stale monitor fixture not in place' }
$new = @{ 'PrinterSetup.exe' = Hash (Join-Path $newBuild 'PrinterSetup.exe'); 'VoucherReorderPort.dll' = Hash (Join-Path $newBuild 'VoucherReorderPort.dll') }
if ((Hash $helper) -eq $new['PrinterSetup.exe'] -or (Hash $monitor) -eq $new['VoucherReorderPort.dll']) {
    throw 'Older build is not distinguishable from this build; stale fixture is meaningless'
}
# 3. Hold the stale helper open without write sharing (but allowing rename), so
#    in-place overwrite keeps failing and forces retry then rename-aside.
$hold = [IO.File]::Open($helper, 'Open', 'Read', ([IO.FileShare]::Read -bor [IO.FileShare]::Delete))
try {
    Run-Setup 'Stale upgrade'
} finally { $hold.Dispose() }
# 4. New bytes in place, spooler running, Imagesetter still active.
if ((Hash $helper) -ne $new['PrinterSetup.exe']) { throw 'PrinterSetup.exe was not replaced with this build' }
if ((Hash $monitor) -ne $new['VoucherReorderPort.dll']) { throw 'VoucherReorderPort.dll was not replaced with this build' }
if ((Get-Service Spooler).Status -ne 'Running') { throw 'Spooler was not restarted' }
$printer = Get-Printer -Name 'Voucher Reorder'
if ($printer.DriverName -ne 'MS Publisher Imagesetter' -or $printer.PortName -ne "VoucherReorder:$sid") {
    throw "Imagesetter not active after stale upgrade: $($printer.DriverName) on $($printer.PortName)"
}
$old = @(Get-ChildItem (Split-Path $helper) -Filter 'PrinterSetup.exe.old*' -ErrorAction SilentlyContinue)
Write-Output "Rename-aside leftovers (deleted at reboot): $($old.Count)"
# Metadata checks on the freshly deployed binaries.
foreach ($file in $helper, $monitor) {
    $company = (Get-Item $file).VersionInfo.CompanyName
    if ($company -ne 'M. Nigh') { throw "CompanyName on $file is '$company'" }
}
# Clean up so later steps start from the usual baseline.
$active = Get-Content (Join-Path $env:LOCALAPPDATA 'Programs\Voucher Reorder\current.json') -Raw | ConvertFrom-Json
$app = Join-Path $env:LOCALAPPDATA ('Programs\Voucher Reorder\deployments\' + $active.directory)
& (Join-Path $app 'runtime\python.exe') (Join-Path $app 'packaging\mode_setup.py') remove --ui
if ($LASTEXITCODE) { throw 'Cleanup removal failed' }
Write-Output 'PASS: stale in-use monitor DLL and helper replaced by elevated Setup; spooler restarted; Imagesetter active'
