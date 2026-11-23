param([ValidateSet('install','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    # This script is unprivileged. UAC launches the protected executable itself;
    # no per-user script, command text, module, or output path crosses elevation.
    $helper = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPrinter\PrinterSetup.exe'
    if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) { exit 11 }
    $process = Start-Process -FilePath $helper -ArgumentList @($Action,$sid) -WorkingDirectory ([Environment]::SystemDirectory) -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
} catch { exit 10 }
