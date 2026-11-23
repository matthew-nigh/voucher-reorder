param([ValidateSet('install','install-pdf','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    # This script is unprivileged. UAC launches the protected executable itself;
    # no per-user script, command text, module, or output path crosses elevation.
    $helper = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPrinter\PrinterSetup.exe'
    if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) { exit 11 }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    # Start-Process preserves the helper's numeric stage/error code. Direct
    # invocation can turn its stderr into a terminating PowerShell error and
    # replace the useful code with this script's generic catch result.
    $start = @{ FilePath=$helper; ArgumentList=@($Action,$sid); WorkingDirectory=[Environment]::SystemDirectory; Wait=$true; PassThru=$true }
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $start.Verb = 'RunAs'
    }
    $process = Start-Process @start
    exit $process.ExitCode
} catch { exit 10 }
