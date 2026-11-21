param([ValidateSet('install','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$base = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)) 'Voucher Reorder Provisioning'
$helper = Join-Path $base 'Provision.exe'
$root = Split-Path $PSScriptRoot -Parent
try {
    $app = Get-Content (Join-Path $root 'PACKAGE.json') -Raw | ConvertFrom-Json
    $installed = if (Test-Path (Join-Path $base 'version.txt')) { [IO.File]::ReadAllText((Join-Path $base 'version.txt')) } else { '' }
    if ($Action -eq 'install') {
        # Run the matching embedded package, which installs AND configures in one elevation.
        # Never execute an elevated PowerShell/Python script from the per-user tree.
        $package = Join-Path $root 'provisioning\Setup.exe'
        $manifest = Get-Content (Join-Path $root 'provisioning\package.json') -Raw | ConvertFrom-Json
        if ($manifest.version -ne $app.version -or (Get-FileHash $package -Algorithm SHA256).Hash -ne $manifest.sha256) { exit 11 }
        $process = Start-Process $package -ArgumentList @('/S',"/TARGETSID=$sid") -Verb RunAs -Wait -PassThru
        if ($process.ExitCode -ne 0) { exit $process.ExitCode }
        if ([IO.File]::ReadAllText((Join-Path $base 'version.txt')) -ne $app.version) { exit 11 }
    } else {
        if (-not [IO.File]::Exists($helper)) { exit 0 }
        if ($installed -ne $app.version) { exit 11 }
        $process = Start-Process $helper -ArgumentList @($Action,$sid) -WorkingDirectory $base -Verb RunAs -Wait -PassThru
    }
    exit $process.ExitCode
} catch { exit 10 }
