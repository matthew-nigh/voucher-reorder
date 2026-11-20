# This is the ONLY elevated component. The application/installer remain per-user.
param([ValidateSet('install','remove')][string]$Action,
      [ValidatePattern('^S-1-[0-9]+(?:-[0-9]+){1,14}$')][string]$TargetSid)
$ErrorActionPreference = 'Stop'
$name = 'Voucher Reorder'
$port = 'VoucherReorder_LPR'
$driver = 'MS Publisher Imagesetter'
$owner = "VoucherReorder owner=$TargetSid"
try {
    $printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
    if ($printer -and ($printer.Comment -ne $owner -or $printer.PortName -ne $port -or $printer.DriverName -ne $driver)) {
        throw 'A different or older Voucher Reorder printer already exists. Ask its administrator to remove it; PDF mode remains available.'
    }
    if ($Action -eq 'remove') {
        if ($printer) {
            if (Get-PrintJob -PrinterName $name) { throw 'Cancel pending jobs in the virtual printer queue before removing it.' }
            Remove-Printer -Name $name
            Remove-PrinterPort -Name $port
        }
        exit 0
    }
    $probe = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 515)
    try { $probe.Start() } finally { $probe.Stop() }
    if (-not (Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue)) { Add-PrinterDriver -Name $driver }
    $runtime = Join-Path $env:WINDIR 'System32\msvcp140.dll'
    if (-not (Test-Path $runtime) -or [version](Get-Item $runtime).VersionInfo.FileVersionRaw -lt [version]'14.38.0.0') {
        $redist = Join-Path $env:TEMP ([guid]::NewGuid().ToString('N') + '.exe')
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $redist -UseBasicParsing
            $signature = Get-AuthenticodeSignature -LiteralPath $redist
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') { throw 'Microsoft runtime signature validation failed.' }
            $process = Start-Process $redist -ArgumentList '/install /quiet /norestart' -Wait -PassThru
            if ($process.ExitCode -notin @(0,1638,3010)) { throw 'Microsoft runtime installation failed.' }
        } finally { Remove-Item -LiteralPath $redist -Force -ErrorAction SilentlyContinue }
    }
    if ($printer) { exit 0 }
    if (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue) { throw 'The port already exists; it was not changed. Use PDF mode.' }
    $madePort = $false; $madePrinter = $false
    try {
        Add-PrinterPort -Name $port -LprHostAddress '127.0.0.1' -LprQueueName 'voucher' -LprByteCounting
        $madePort = $true
        Add-Printer -Name $name -DriverName $driver -PortName $port -Comment $owner
        $madePrinter = $true
        Set-PrintConfiguration -PrinterName $name -PaperSize Letter -DuplexingMode OneSided
        Set-Printer -Name $name -PermissionSDDL "O:${TargetSid}G:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00020008;;;${TargetSid})"
    } catch {
        if ($madePrinter) { Remove-Printer -Name $name -ErrorAction SilentlyContinue }
        if ($madePort) { Remove-PrinterPort -Name $port -ErrorAction SilentlyContinue }
        throw
    }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    $null = [Windows.Forms.MessageBox]::Show("Optional virtual printer setup was not completed. PDF handoff remains available.`n`n$($_.Exception.Message)", 'Voucher Reorder', 'OK', 'Warning')
    exit 1
}
