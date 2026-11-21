# Render two synthetic pages into the Windows PDF printer's local file port.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\build\windows").Path
$python = Join-Path $root 'runtime\python.exe'
$temp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($temp)
$result = Join-Path $temp 'device.pdf'
$source = Join-Path $temp 'input.pdf'
$name = "Voucher CI $([Guid]::NewGuid().ToString('N'))"
$driver = Get-PrinterDriver -Name 'Microsoft Print To PDF' -ErrorAction SilentlyContinue
if (-not $driver) { Write-Warning 'Native PDF printer unavailable; file-port GDI smoke test skipped.'; exit 0 }
try {
    Add-PrinterPort -Name $result
    Add-Printer -Name $name -PortName $result -DriverName $driver.Name
    & $python -c "from voucher_reorder.alignment import create; from voucher_reorder.config import Settings; from pypdf import PdfWriter; import sys; create(sys.argv[1], Settings()); w=PdfWriter(); w.append(sys.argv[1]); w.append(sys.argv[1]); w.write(sys.argv[2])" (Join-Path $temp 'sample.pdf') $source
    if ($LASTEXITCODE) { throw 'Unable to generate synthetic batch' }
    & $python -c "from pathlib import Path; from voucher_reorder.config import Settings; from voucher_reorder.bounded import execute; import sys; execute('print',Path(sys.argv[1]),Settings(printer=sys.argv[2]))" $source $name
    if ($LASTEXITCODE) { throw 'Bounded Windows print failed' }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if (Test-Path $result) {
            & $python -c "from pypdf import PdfReader; import sys; r=PdfReader(sys.argv[1],strict=True); assert len(r.pages)==2 and all(p.get_contents().get_data() for p in r.pages)" $result 2>$null
            if ($LASTEXITCODE -eq 0) { exit 0 }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'The Windows printer did not produce both pages'
} finally {
    Remove-Printer -Name $name -ErrorAction SilentlyContinue
    Remove-PrinterPort -Name $result -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force
}
