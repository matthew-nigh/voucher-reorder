# SPDX-License-Identifier: GPL-3.0-or-later
param([ValidateSet('preflight','install','uninstall')][string]$Action)
$ErrorActionPreference = 'Stop'
$name = 'Voucher Reorder'
$port = 'VoucherReorder_LPR'
$driver = 'MS Publisher Imagesetter'
$root = Split-Path $PSScriptRoot -Parent
$marker = Join-Path $root 'printer-owned.json'
try {
    # A single Windows account owns this workstation installation. Prevent alternate-admin installs.
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $session = (Get-Process -Id $PID).SessionId
    $explorer = Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" | Where-Object { $_.SessionId -eq $session } | Select-Object -First 1
    if ($null -eq $explorer -or (Invoke-CimMethod -InputObject $explorer -MethodName GetOwnerSid).Sid -ne $sid) {
        throw 'Install/uninstall while signed into the same administrator account you use for QuickBooks. Alternate administrator credentials are not supported.'
    }
    if ($Action -eq 'preflight') {
        if (Get-Printer -Name $name -ErrorAction SilentlyContinue) { throw 'Voucher Reorder already exists. Uninstall the previous version first.' }
        if (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue) { throw 'The Voucher Reorder port already exists. Ask your administrator to inspect it.' }
        $probe = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 515)
        try { $probe.Start() } finally { $probe.Stop() }
        # Register Microsoft's signed inbox PostScript driver, never download an unknown driver.
        if (-not (Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue)) { Add-PrinterDriver -Name $driver }
        # Ghostscript requires the shared Microsoft C++ runtime. Do not redistribute
        # its proprietary installer with this GPL package; fetch it from Microsoft
        # only when missing, verify its signature, then install it as a system prerequisite.
        $runtime = Join-Path $env:WINDIR 'System32\msvcp140.dll'
        if (-not (Test-Path $runtime) -or [version](Get-Item $runtime).VersionInfo.FileVersionRaw -lt [version]'14.38.0.0') {
            $redist = Join-Path $env:TEMP ([guid]::NewGuid().ToString('N') + '.exe')
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $redist -UseBasicParsing
                $signature = Get-AuthenticodeSignature -LiteralPath $redist
                if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') {
                    throw 'Microsoft runtime signature validation failed.'
                }
                $process = Start-Process -FilePath $redist -ArgumentList '/install /quiet /norestart' -Wait -PassThru
                if ($process.ExitCode -notin @(0, 1638, 3010)) { throw 'Microsoft C++ runtime installation failed.' }
            } finally { Remove-Item -LiteralPath $redist -Force -ErrorAction SilentlyContinue }
        }
        exit 0
    }
    if ($Action -eq 'install') {
        $createdPort = $false; $createdPrinter = $false
        try {
            Add-PrinterPort -Name $port -LprHostAddress '127.0.0.1' -LprQueueName 'voucher' -LprByteCounting
            $createdPort = $true
            Add-Printer -Name $name -DriverName $driver -PortName $port
            $createdPrinter = $true
            Set-PrintConfiguration -PrinterName $name -PaperSize Letter -DuplexingMode OneSided
            # Owner can print, admins/SYSTEM can administer. No access for other desktop users.
            Set-Printer -Name $name -PermissionSDDL "O:${sid}G:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00020008;;;${sid})"
            @{port=$port; owner=$sid} | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
        } catch {
            if ($createdPrinter) { Remove-Printer -Name $name -ErrorAction SilentlyContinue }
            if ($createdPort) { Remove-PrinterPort -Name $port -ErrorAction SilentlyContinue }
            throw
        }
        exit 0
    }
    if (-not (Test-Path -LiteralPath $marker)) { throw 'Printer ownership marker missing. Ask your administrator to inspect the installation.' }
    $owned = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    if ($owned.owner -ne $sid) { throw 'Uninstall using the Windows account that installed Voucher Reorder.' }
    $printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
    if ($printer -and $printer.PortName -ne $owned.port) { throw 'Printer configuration changed. Refusing to remove a different printer.' }
    if ($printer -and (Get-PrintJob -PrinterName $name -ErrorAction Stop)) { throw 'Cancel all jobs in the Voucher Reorder Windows queue, then uninstall again.' }
    & (Join-Path $root 'runtime\pythonw.exe') (Join-Path $root 'app.py') stop
    if ($LASTEXITCODE -ne 0) { throw 'The background app did not stop. Check the physical printer queue and try again.' }
    if ($printer) { Remove-Printer -Name $name }
    if (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue) { Remove-PrinterPort -Name $port }
    Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name VoucherReorder -ErrorAction SilentlyContinue
    $data = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
    if (Test-Path -LiteralPath $data) { Remove-Item -LiteralPath $data -Recurse -Force }
    Remove-Item -LiteralPath $marker
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    $null = [Windows.Forms.MessageBox]::Show("Voucher Reorder setup could not finish.`n`n$($_.Exception.Message)`n`nNo third-party printer driver will be installed. See TESTING_ON_WINDOWS.md.", 'Voucher Reorder setup', 'OK', 'Error')
    exit 1
}
