# Exercise real spooler state across both virtual variants and repeated Local Ports.
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot '..\dist\VoucherReorder-0.2.6-Setup.exe'
$appRoot = Join-Path $env:LOCALAPPDATA 'Programs\Voucher Reorder'
$data = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$portProbe = Join-Path $PSScriptRoot '..\build\printer\PrinterSecurityTest.exe'
function Assert-Enumeration($label) {
    # No installed monitor may break system-wide port enumeration.
    & $portProbe --enum-all
    if ($LASTEXITCODE) { throw "EnumPortsW is broken ($label)" }
    try { $ports = @(Get-PrinterPort -ErrorAction Stop) }
    catch { throw "Get-PrinterPort is broken ($label): $($_.Exception.Message)" }
    if (-not $ports.Count) { throw "Get-PrinterPort returned no ports ($label)" }
}
function Assert-Mode($variant, $driver, $port) {
    $settings = Get-Content (Join-Path $data 'settings.json') -Raw | ConvertFrom-Json
    if ($settings.mode -ne $(if ($variant) { 'virtual' } else { 'pdf' }) -or
        ($variant -and $settings.virtual_variant -ne $variant)) { throw "Wrong mode: $($settings | ConvertTo-Json -Compress)" }
    $printer = Get-Printer -Name 'Voucher Reorder' -ErrorAction SilentlyContinue
    if ($variant -and (-not $printer -or $printer.DriverName -ne $driver -or $printer.PortName -ne $port)) {
        $detail = Get-Content (Join-Path $data 'printer-setup-error.txt') -ErrorAction SilentlyContinue
        throw "Wrong printer state: expected $driver on $port; detail=$detail"
    }
    if ($variant) {
        # Win32 EnumPorts labels Windows' Local Port monitor "Local Monitor".
        $monitor = if ($variant -eq 'imagesetter') { 'Voucher Reorder Secure Port' } else { 'Local Monitor' }
        & $portProbe --port $port $monitor
        if ($LASTEXITCODE) { throw "Port was not published by ${monitor}: $port" }
    }
    if (-not $variant -and $printer) { throw 'Handoff retained the optional printer' }
    if (-not $variant) {
        & $portProbe --port-absent "VoucherReorder:$sid"
        if ($LASTEXITCODE) { throw 'Handoff retained the Imagesetter port' }
    }
    Assert-Enumeration "variant=$variant"
}
function Change-Mode($action) {
    $active = Get-Content (Join-Path $appRoot 'current.json') -Raw | ConvertFrom-Json
    $python = Join-Path $appRoot "deployments\$($active.directory)\runtime\python.exe"
    $mode = Join-Path $appRoot "deployments\$($active.directory)\packaging\mode_setup.py"
    & $python $mode $action --ui
    if ($LASTEXITCODE) {
        $detail = Get-Content (Join-Path $data 'printer-setup-error.txt') -ErrorAction SilentlyContinue
        throw "Mode switch $action failed: $detail"
    }
}
$process = Start-Process (Resolve-Path $installer) -ArgumentList '/S /VIRTUAL=1' -PassThru
if (-not $process.WaitForExit(120000) -or $process.ExitCode) { throw "Imagesetter installer failed: $($process.ExitCode)" }
Assert-Mode 'imagesetter' 'MS Publisher Imagesetter' "VoucherReorder:$sid"
$profile = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid").ProfileImagePath
$pdfPort = Join-Path ([Environment]::ExpandEnvironmentVariables($profile)) 'AppData\Local\VoucherReorder\Incoming\virtual.pdf'
Change-Mode 'pdf-printer'
Assert-Mode 'print_to_pdf' 'Microsoft Print To PDF' $pdfPort
Change-Mode 'remove'
Assert-Mode $null $null $null
Change-Mode 'pdf-printer'
Assert-Mode 'print_to_pdf' 'Microsoft Print To PDF' $pdfPort
Change-Mode 'pdf-printer'
Assert-Mode 'print_to_pdf' 'Microsoft Print To PDF' $pdfPort
Change-Mode 'remove'
Assert-Mode $null $null $null
# This unit runs on Windows too and checks that native stage and Win32 error
# are visible in Settings status and the user's diagnostic log.
python -m pytest tests/test_user_workflow.py -k pdf_virtual_setup_failure_is_visible_to_acceptance_runner -q
if ($LASTEXITCODE) { throw 'Stage/error presentation test failed' }
