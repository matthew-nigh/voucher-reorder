param([ValidateSet('install','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$base = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)
$helper = Join-Path $base 'Voucher Reorder Provisioning\Provision.exe'
if (-not [IO.File]::Exists($helper)) { exit 1 }
try {
    $process = Start-Process $helper -ArgumentList @($Action,$sid) -WorkingDirectory (Split-Path $helper) -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
} catch { exit 10 }
