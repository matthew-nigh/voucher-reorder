# Real administrator lifecycle; interactive alternate-credential UAC remains a manual check.
param([string]$Installer,[string]$UpgradeInstaller)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'Programs\Voucher Reorder'
$data = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$protected = Join-Path $env:ProgramFiles 'Voucher Reorder Provisioning'
function Setup($path,$virtual) {
    $arguments = if ($virtual) { '/S /VIRTUAL=1' } else { '/S' }
    Write-Output "Running setup: $([IO.Path]::GetFileName($path)); virtual=$virtual"
    $p = Start-Process (Resolve-Path $path) -ArgumentList $arguments -Wait -PassThru
    if ($p.ExitCode) { throw "Integrated setup failed: $($p.ExitCode)" }
}
function Check($version,$mode) {
    $current = Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
    $config = Get-Content (Join-Path $data 'settings.json') -Raw | ConvertFrom-Json
    Write-Output "Expected $version/$mode; got $($current.version)/$($config.mode)"
    if ($current.version -ne $version -or $config.mode -ne $mode) {
        Get-Content (Join-Path $data 'mode-status.txt') -ErrorAction SilentlyContinue
        Get-Content (Join-Path $protected 'version.txt') -ErrorAction SilentlyContinue
        # CI contains only synthetic state. Run the installed script directly to
        # expose the underlying machine setup error, then fail the original check.
        if (Test-Path (Join-Path $protected 'printer.ps1')) {
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            & (Join-Path $PSHOME 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File (Join-Path $protected 'printer.ps1') -Action install -TargetSid $sid -NoDialogs
        }
        throw 'Unexpected app version or operating mode'
    }
    if ($mode -eq 'virtual') {
        if ([IO.File]::ReadAllText((Join-Path $protected 'version.txt')) -ne $version) { throw 'Provisioning version mismatch' }
        $printer = Get-Printer -Name 'Voucher Reorder'
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        if ($printer.PortName -ne 'NUL:' -or $printer.Comment -ne "VoucherReorder owner=$sid") { throw 'Incorrect queue ownership or port' }
    }
}
try {
    Setup $Installer $true
    Check '0.2.0' 'virtual'
    Setup $UpgradeInstaller $false
    Check '0.2.2' 'pdf' # No UAC/app upgrade dependency on the machine package.
    Setup $UpgradeInstaller $true
    Check '0.2.2' 'virtual'
    $active = Get-Content (Join-Path $root 'current.json') -Raw | ConvertFrom-Json
    $app = Join-Path $root ('deployments\'+$active.directory)
    $python = Join-Path $app 'runtime\python.exe'
    & $python (Join-Path $app 'app.py') stop
    if ($LASTEXITCODE) { throw 'Could not stop worker for retained printer test' }
    $feedback = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
    & $python (Join-Path $PSScriptRoot 'test_feedback_windows.py') $feedback 'Voucher Reorder'
    if ($LASTEXITCODE) { throw 'Retained printer feedback regressions failed' }
    Remove-Item -LiteralPath $feedback -Recurse -Force
    $manifest = Join-Path $app 'provisioning\package.json'
    $original = [IO.File]::ReadAllText($manifest)
    try {
        [IO.File]::WriteAllText($manifest,'{"version":"0.0.0","sha256":"bad"}')
        & (Join-Path $PSHOME 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'packaging\request_printer.ps1') -Action install
        if ($LASTEXITCODE -ne 11) { throw 'Mismatched package was not rejected before elevation' }
    } finally { [IO.File]::WriteAllText($manifest,$original) }
    $p = Start-Process (Join-Path $root 'Uninstall.exe') -ArgumentList '/S' -Wait -PassThru
    if ($p.ExitCode) { throw 'App uninstall failed' }
    $p = Start-Process (Join-Path $protected 'Uninstall.exe') -ArgumentList '/S' -Wait -PassThru
    if ($p.ExitCode) { throw 'Provisioning uninstall failed' }
    Start-Sleep -Seconds 2
    if (Get-Printer -Name 'Voucher Reorder' -ErrorAction SilentlyContinue) { throw 'Provisioned queue remains' }
    if (Test-Path (Join-Path $protected 'Provision.exe')) { throw 'Provisioning files remain' }
    if (Test-Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorderProvisioning') { throw 'Machine uninstall entry remains' }
    Write-Output 'PASS: integrated optional provisioning, version mismatch fallback/rejection, package upgrade and uninstall'
} finally {
    # Only CI account data is used; leave failures intact for runner diagnostics.
}
# The intentional version-mismatch probe leaves LASTEXITCODE=11; do not let
# the Actions PowerShell wrapper mistake that expected rejection for a failure.
exit 0
