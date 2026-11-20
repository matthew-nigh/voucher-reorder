param([ValidateSet('install','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$script = Join-Path $PSScriptRoot 'printer.ps1'
# Pass the original user's SID even if UAC uses a different administrator account.
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $script + '" -Action ' + $Action + ' -TargetSid ' + $sid
try {
    $process = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
} catch {
    exit 10 # UAC declined, credentials unavailable, or policy blocked elevation
}
