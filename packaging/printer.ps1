param([Parameter(Mandatory)][ValidateSet('install','remove')][string]$Action,
      [Parameter(Mandatory)][ValidatePattern('^S-1-5-21-(?:[0-9]+-){3}[0-9]+$|^S-1-12-1-(?:[0-9]+-){3}[0-9]+$')][string]$TargetSid,
      [switch]$NoDialogs)
$ErrorActionPreference = 'Stop'
$name = 'Voucher Reorder'
$port = 'NUL:'
$driver = 'MS Publisher Imagesetter'
$owner = "VoucherReorder owner=$TargetSid"
try {
    $printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
    if ($printer -and ($printer.Comment -ne $owner -or $printer.DriverName -ne $driver -or
        $printer.PortName -notin @($port,'VoucherReorder_LPR'))) { throw 'Printer ownership mismatch.' }
    if ($printer -and ($Action -eq 'remove' -or $printer.PortName -ne $port)) {
        if (Get-PrintJob -PrinterName $name) { throw 'Reconcile and cancel pending jobs before migration.' }
        Remove-Printer -Name $name
        if ($printer.PortName -eq 'VoucherReorder_LPR') { Remove-PrinterPort -Name $printer.PortName }
        $printer = $null
    }
    if ($Action -eq 'remove') { exit 0 }
    $runtime = Join-Path ([Environment]::SystemDirectory) 'msvcp140.dll'
    if (-not (Test-Path $runtime) -or (Get-Item $runtime).VersionInfo.FileVersionRaw -lt [version]'14.38.0.0') {
        # PSScriptRoot is the administrator-installed directory. Keep download, verification
        # and execution there even when UAC uses the desktop user's administrator token.
        $redist = Join-Path $PSScriptRoot ([Guid]::NewGuid().ToString('N') + '.exe')
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $redist -UseBasicParsing
            $signature = Get-AuthenticodeSignature -LiteralPath $redist
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') { throw 'Invalid Microsoft runtime signature.' }
            $process = Start-Process $redist -WorkingDirectory $PSScriptRoot -ArgumentList '/install /quiet /norestart' -Wait -PassThru
            if ($process.ExitCode -notin @(0,1638,3010)) { throw 'Microsoft runtime installation failed.' }
        } finally { Remove-Item -LiteralPath $redist -Force -ErrorAction SilentlyContinue }
    }
    $existing = Get-PrinterPort -Name $port -ErrorAction SilentlyContinue
    if ($existing -and $existing.PortMonitor -ne 'Local Port') { throw 'Unexpected port monitor.' }
    if (-not $existing) { Add-PrinterPort -Name $port }
    if (-not (Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue)) { Add-PrinterDriver -Name $driver }
    $acl = "O:BAG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;SWRC;;;$TargetSid)(A;OIIO;GA;;;$TargetSid)"
    if (-not $printer) {
        Add-Printer -Name $name -PortName $port -DriverName $driver -Comment $owner -PermissionSDDL $acl -KeepPrintedJobs -Datatype RAW
        $madePrinter = $true
    } else {
        Set-Printer -Name $name -PermissionSDDL $acl -KeepPrintedJobs $true -Shared $false -Datatype RAW
    }
    & (Join-Path $PSScriptRoot "raw_spool.ps1")
    Set-PrintConfiguration -PrinterName $name -PaperSize Letter -DuplexingMode OneSided
} catch {
    if ($madePrinter) { Remove-Printer -Name $name -ErrorAction SilentlyContinue }
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
