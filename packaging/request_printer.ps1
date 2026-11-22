param([ValidateSet('install','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$incoming = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'VoucherReorder\Incoming'
[IO.Directory]::CreateDirectory($incoming) | Out-Null
$port = Join-Path $incoming 'job.pdf'
try {
    # Snapshot the script and literal parameters into one encoded command. Only the
    # signed Windows PowerShell binary is elevated, never a per-user executable.
    $script = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'printer.ps1'))
    $literalPort = $port.Replace("'","''")
    $command = "& {`n$script`n} -Action '$Action' -TargetSid '$sid' -IncomingPath '$literalPort' -NoDialogs"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $powershell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
    $process = Start-Process $powershell -ArgumentList @('-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',$encoded) -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
} catch { exit 10 }
