param([ValidateSet('install','install-pdf','remove')][string]$Action,[switch]$Installer)
$ErrorActionPreference = 'Stop'
try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    # This script stays unprivileged. Setup relaunches its own image; Settings
    # elevates the installed protected helper. Neither elevates this script.
    $helper = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderPrinter\PrinterSetup.exe'
    if (-not $Installer -and -not (Test-Path -LiteralPath $helper -PathType Leaf)) { exit 11 }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    # Start-Process preserves the helper's numeric stage/error code. Direct
    # invocation can turn its stderr into a terminating PowerShell error and
    # replace the useful code with this script's generic catch result.
    $target = $helper
    $arguments = @($Action,$sid)
    if ($Installer -and -not (Test-Path -LiteralPath $helper -PathType Leaf)) {
        $target = [Environment]::GetEnvironmentVariable('VOUCHER_REORDER_SETUP_IMAGE')
        if (-not $target -or -not $target.EndsWith('-Setup.exe', [StringComparison]::OrdinalIgnoreCase)) { exit 11 }
        $target = [IO.Path]::GetFullPath($target)
        $appData = [IO.Path]::GetFullPath([Environment]::GetFolderPath('LocalApplicationData')).TrimEnd('\') + '\'
        $roaming = [IO.Path]::GetFullPath([Environment]::GetFolderPath('ApplicationData')).TrimEnd('\') + '\'
        if ($target.StartsWith($appData, [StringComparison]::OrdinalIgnoreCase) -or
            $target.StartsWith($roaming, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $target -PathType Leaf)) { exit 11 }
        $arguments = @('/elevated-printer',$Action,$sid)
    }
    $start = @{ FilePath=$target; ArgumentList=$arguments; WorkingDirectory=[Environment]::SystemDirectory; Wait=$true; PassThru=$true }
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $start.Verb = 'RunAs'
    }
    $process = Start-Process @start
    exit $process.ExitCode
} catch { exit 10 }
