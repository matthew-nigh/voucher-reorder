# Exercise short jobs back to back through the real worker and a Windows file port.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\build\windows").Path
$python = Join-Path $root 'runtime\python.exe'
$verifyPython = (Get-Command python).Source
$temp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($temp)
$result = Join-Path $temp 'device.pdf'
$name = "Voucher CI $([Guid]::NewGuid().ToString('N'))"
$driver = Get-PrinterDriver -Name 'Microsoft Print To PDF' -ErrorAction SilentlyContinue
if (-not $driver) { throw 'Native PDF printer required for vector print acceptance' }
try {
    Add-PrinterPort -Name $result
    Add-Printer -Name $name -PortName $result -DriverName $driver.Name
    & $python (Join-Path $PSScriptRoot 'test_print_jobs.py') $temp $name $verifyPython
    if ($LASTEXITCODE) { throw 'Consecutive Windows print jobs failed' }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (Get-PrintJob -PrinterName $name) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Windows spool backlog remains after output verification' }
        Start-Sleep -Milliseconds 100
    }
    & $python (Join-Path $PSScriptRoot 'test_feedback_windows.py') (Join-Path $temp 'feedback') $name
    if ($LASTEXITCODE) { throw 'Saved Microsoft PDF reprint feedback regressions failed' }
    & $python (Join-Path $PSScriptRoot 'test_vector_rejection.py') $temp $name
    if ($LASTEXITCODE) { throw 'Vector preflight rejection checks failed' }
} finally {
    Remove-Printer -Name $name -ErrorAction SilentlyContinue
    Remove-PrinterPort -Name $result -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
