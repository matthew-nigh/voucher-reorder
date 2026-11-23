# Diagnostic only: measure the token used by Microsoft's v4 PDF Local Port.
# This fixture is never used by the installed virtual printer.
param(
    [switch]$Child,
    [string]$PrinterName,
    [string]$Title
)
$ErrorActionPreference = 'Stop'
if ($Child) {
    Add-Type -AssemblyName System.Drawing
    $document = [Drawing.Printing.PrintDocument]::new()
    $document.PrinterSettings.PrinterName = $PrinterName
    $document.PrintController = [Drawing.Printing.StandardPrintController]::new()
    $document.DocumentName = $Title
    $document.add_PrintPage({
        param($sender, $event)
        $font = [Drawing.Font]::new('Arial', 12)
        try { $event.Graphics.DrawString('VOID FAKE TOKEN PROBE', $font, [Drawing.Brushes]::Black, 72, 72) }
        finally { $font.Dispose() }
    })
    try { $document.Print() } finally { $document.Dispose() }
    exit 0
}

$name = 'VrPdf' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$password = ConvertTo-SecureString ('Vr!' + [guid]::NewGuid().ToString('N') + '9a') -AsPlainText -Force
$credential = [Management.Automation.PSCredential]::new("$env:COMPUTERNAME\$name", $password)
$root = Join-Path $env:PUBLIC ('VoucherPdfProbe-' + [guid]::NewGuid().ToString('N'))
$redirect = Join-Path $root 'redirect'
$protected = Join-Path $env:ProgramFiles ('VoucherPdfProbe-' + [guid]::NewGuid().ToString('N'))
$filename = Join-Path $redirect 'job.pdf'
$printer = 'Voucher PDF probe ' + [guid]::NewGuid().ToString('N')
$userCreated = $false
$portCreated = $false
$printerCreated = $false
try {
    $driver = Get-PrinterDriver -Name 'Microsoft Print To PDF' -ErrorAction Stop
    $user = New-LocalUser -Name $name -Password $password
    $userCreated = $true
    Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $name
    New-Item -ItemType Directory -Path $root, $redirect, $protected | Out-Null
    & icacls.exe $root /grant "${name}:(OI)(CI)M" /T | Out-Null
    if ($LASTEXITCODE) { throw 'Could not grant probe user access' }
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $admins = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $acl.SetOwner($admins)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
        $identity = [Security.Principal.SecurityIdentifier]::new($sid)
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $protected -AclObject $acl
    Add-PrinterPort -Name $filename
    $portCreated = $true
    Add-Printer -Name $printer -PortName $filename -DriverName $driver.Name
    $printerCreated = $true

    function Send-Probe($title) {
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Child -PrinterName "' + $printer + '" -Title "' + $title + '"'
        $process = Start-Process (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -Credential $credential -LoadUserProfile -ArgumentList $arguments -PassThru
        if (-not $process.WaitForExit(30000)) { Stop-Process -Id $process.Id; throw 'Probe submission timed out' }
        if ($process.ExitCode) { throw "Probe submission failed: $($process.ExitCode)" }
    }

    Send-Probe 'VOID FAKE owner probe'
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $filename)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'PDF file was not produced' }
        Start-Sleep -Milliseconds 200
    }
    while (Get-PrintJob -PrinterName $printer) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'PDF job did not complete' }
        Start-Sleep -Milliseconds 200
    }
    $owner = (Get-Acl -LiteralPath $filename).GetOwner([Security.Principal.SecurityIdentifier]).Value
    $expected = $user.SID.Value
    Write-Output "LOCAL PORT OWNER: $owner; submitting user: $expected; user-owned: $($owner -eq $expected)"

    Remove-Printer -Name $printer
    $printerCreated = $false
    Remove-Item -LiteralPath $filename -Force
    Remove-Item -LiteralPath $redirect
    New-Item -ItemType Junction -Path $redirect -Target $protected | Out-Null
    # Same port path, now redirected to a directory only SYSTEM/admin can write.
    Add-Printer -Name $printer -PortName $filename -DriverName $driver.Name
    $printerCreated = $true
    Send-Probe 'VOID FAKE junction probe'
    Start-Sleep -Seconds 5
    Write-Output "LOCAL PORT JUNCTION: protected target created: $(Test-Path -LiteralPath (Join-Path $protected 'job.pdf'))"
} catch {
    Write-Warning "LOCAL PORT PROBE INCONCLUSIVE: $($_.Exception.Message)"
} finally {
    if ($printerCreated) { Remove-Printer -Name $printer -ErrorAction SilentlyContinue }
    if ($portCreated) { Remove-PrinterPort -Name $filename -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $redirect) {
        if ((Get-Item -LiteralPath $redirect -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            [IO.Directory]::Delete($redirect)
        } else {
            Remove-Item -LiteralPath $redirect -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $protected) { Remove-Item -LiteralPath $protected -Recurse -Force -ErrorAction SilentlyContinue }
    if ($userCreated) { Remove-LocalUser -Name $name -ErrorAction SilentlyContinue }
}
