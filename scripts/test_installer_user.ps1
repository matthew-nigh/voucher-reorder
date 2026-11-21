# Run inside a real, non-administrator Windows account by test_standard_user.ps1.
param([string]$Installer, [string]$UpgradeInstaller, [string]$Result)
$ErrorActionPreference='Stop'
try {
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Test must run as standard user' }
    function Run-Setup($path,$expected=0) {
        $p=Start-Process -FilePath $path -ArgumentList '/S' -Wait -PassThru
        if (($expected -eq 0 -and $p.ExitCode -ne 0) -or ($expected -ne 0 -and $p.ExitCode -eq 0)) { throw "Unexpected setup exit $($p.ExitCode)" }
    }
    # CreateProcessWithLogon may inherit the runner's environment; use this token's known folders.
    $env:LOCALAPPDATA=[Environment]::GetFolderPath('LocalApplicationData')
    $env:APPDATA=[Environment]::GetFolderPath('ApplicationData')
    $env:USERPROFILE=[Environment]::GetFolderPath('UserProfile')
    $env:TEMP=Join-Path $env:LOCALAPPDATA 'Temp'
    $null=New-Item -ItemType Directory -Path $env:TEMP -Force
    $root=Join-Path $env:LOCALAPPDATA 'Programs\Voucher Reorder'
    $data=Join-Path $env:LOCALAPPDATA 'VoucherReorder'
    Run-Setup $Installer
    $old=Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
    $oldDir=Join-Path $root ('deployments\'+$old.directory)
    $py=Join-Path $oldDir 'runtime\python.exe'
    & $py -c "from voucher_reorder.config import *; save(data_dir()/'settings.json', Settings(printer='FAKE CI PRINTER', order=(2,0,1), offsets=((.02,0),(0,.03),(0,0))))"
    if ($LASTEXITCODE -ne 0) { throw 'Installed runtime failed' }
    $before=[IO.File]::ReadAllBytes((Join-Path $data 'settings.json'))
    & $py -c "from voucher_reorder.alignment import create; from voucher_reorder.config import *; from voucher_reorder.queue import Queue; p=data_dir()/'FAKE.pdf'; create(p,Settings()); Queue(data_dir()/'jobs').accept_bytes(p.read_bytes(),load(data_dir()/'settings.json'))"
    if ($LASTEXITCODE -ne 0) { throw 'Could not queue fake pending job' }
    & (Join-Path $PSHOME 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File (Join-Path $oldDir 'packaging\settings.ps1') -SmokeTest
    if ($LASTEXITCODE -ne 0) { throw 'Native settings construction failed' }
    & $py -c "from voucher_reorder.config import data_dir; from voucher_reorder.queue import Queue; q=Queue(data_dir()/'jobs'); q.update(q.jobs()[0],'held','FAKE test: held before upgrade')"
    $worker=Start-Process (Join-Path $oldDir 'runtime\pythonw.exe') -ArgumentList ('"'+(Join-Path $oldDir 'app.py')+'" worker') -PassThru
    $deadline=(Get-Date).AddSeconds(10)
    while (-not (Test-Path (Join-Path $data 'worker.json'))) {
        if ((Get-Date) -gt $deadline) { throw 'Worker did not start' }
        Start-Sleep -Milliseconds 100
    }
    Run-Setup $UpgradeInstaller
    if (-not $worker.WaitForExit(10000)) { throw 'Old worker did not stop during upgrade' }
    $current=Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
    if ([version]$current.version -le [version]$old.version) { throw 'Version did not advance' }
    if (Test-Path $oldDir) { throw 'Old deployment not cleaned up' }
    $after=[IO.File]::ReadAllBytes((Join-Path $data 'settings.json'))
    if ([Convert]::ToBase64String($before) -ne [Convert]::ToBase64String($after)) { throw 'Settings changed during upgrade' }
    $state=Get-ChildItem (Join-Path $data 'jobs') -Filter state.json -Recurse | Select-Object -First 1 | Get-Content -Raw | ConvertFrom-Json
    if ($state.state -ne 'held') { throw 'Pending job was not held' }
    # Load actual v0.2.0 settings and a queued snapshot using the upgraded runtime.
    $newDir=Join-Path $root ('deployments\'+$current.directory)
    $newPy=Join-Path $newDir 'runtime\python.exe'
    & $newPy -c "from voucher_reorder.config import *; from dataclasses import asdict; s=load(data_dir()/'settings.json'); assert tuple(s.source_order)==(0,1,2); assert tuple(s.order)==(2,0,1); save(data_dir()/'settings.json',s); assert 'quickbooks_version' not in asdict(s) and 'printer_model' not in asdict(s)"
    if ($LASTEXITCODE -ne 0) { throw 'v0.2.0 settings did not migrate' }
    & $newPy -c "from voucher_reorder.config import *; from voucher_reorder.queue import Queue; from voucher_reorder.worker import process_one; q=Queue(data_dir()/'jobs'); job=q.jobs()[0]; q.update(job,'queued'); calls=[]; process_one(q,load(data_dir()/'settings.json'),sender=lambda p,s,a:calls.append(tuple(s.source_order))); assert calls==[(0,1,2)]; assert q.read(job)['state']=='sent'"
    if ($LASTEXITCODE -ne 0) { throw 'v0.2.0 queued settings did not migrate' }
    Run-Setup $Installer 1 # real downgrade attempt must fail without changing active version
    $check=Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
    if ($check.version -ne $current.version) { throw 'Downgrade changed active install' }
    Run-Setup $UpgradeInstaller # same-version repair
    $p=Start-Process (Join-Path $root 'Uninstall.exe') -ArgumentList '/S' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw 'Uninstall failed' }
    # NSIS self-deletion completes after the uninstaller process exits.
    Start-Sleep -Seconds 2
    if (Test-Path (Join-Path $root 'deployments')) { throw 'Deployment files remain after uninstall' }
    if (Test-Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder') { throw 'Uninstall entry remains' }
    if (-not (Test-Path (Join-Path $data 'settings.json'))) { throw 'Reinstall settings were not preserved' }
    'PASS: standard-user install, UI construction, upgrade, settings/job preservation, downgrade refusal, repair and uninstall' | Set-Content $Result
} catch {
    ('FAIL: '+$_.Exception.Message) | Set-Content $Result
    exit 1
}
