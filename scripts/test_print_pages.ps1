# Render 52 synthetic vector pages into the Windows PDF printer's local file port.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\build\windows").Path
$python = Join-Path $root 'runtime\python.exe'
$temp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($temp)
$result = Join-Path $temp 'device.pdf'
$source = Join-Path $temp 'input.pdf'
$name = "Voucher CI $([Guid]::NewGuid().ToString('N'))"
$driver = Get-PrinterDriver -Name 'Microsoft Print To PDF' -ErrorAction SilentlyContinue
if (-not $driver) { throw 'Native PDF printer required for vector print acceptance' }
try {
    Add-PrinterPort -Name $result
    Add-Printer -Name $name -PortName $result -DriverName $driver.Name
    & $python -c "from voucher_reorder.alignment import create; from voucher_reorder.config import Settings; from pypdf import PdfWriter; import sys; create(sys.argv[1], Settings()); w=PdfWriter(); [w.append(sys.argv[1]) for _ in range(52)]; w.write(sys.argv[2])" (Join-Path $temp 'sample.pdf') $source
    if ($LASTEXITCODE) { throw 'Unable to generate synthetic batch' }
    & $python -c "from pathlib import Path; from voucher_reorder.config import Settings; from voucher_reorder.bounded import execute; import sys; execute('print',Path(sys.argv[1]),Settings(printer=sys.argv[2]))" $source $name
    if ($LASTEXITCODE) { Get-Content (Join-Path $env:LOCALAPPDATA 'VoucherReorder\print-error.log'); throw 'Bounded Windows print failed' }
    $metrics = Get-Content (Join-Path $temp 'print-metrics.json') -Raw | ConvertFrom-Json
    Write-Output "52-page print child peak job memory: $($metrics.peak_job_bytes) bytes"
    if ($metrics.peak_job_bytes -le 0 -or $metrics.peak_job_bytes -ge 600MB) { throw 'Peak print memory exceeded 600 MiB acceptance budget' }
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        if (Test-Path $result) {
            & $python (Join-Path $PSScriptRoot 'verify_print_output.py') $result 52 2>$null
            if ($LASTEXITCODE -eq 0) {
                $gs = Join-Path $root 'vendor\ghostscript\bin\gswin64c.exe'
                $ink = & $gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=inkcov -sOutputFile=- $result
                if ($LASTEXITCODE) { throw 'Cannot check printed ink coverage' }
                $coverage = @($ink | Where-Object { $_ -match 'CMYK OK' })
                if ($coverage.Count -ne 52) { throw 'Ink coverage page count mismatch' }
                foreach ($line in $coverage) {
                    $values = $line.Trim() -split '\s+'
                    if (([double]::Parse($values[0],[cultureinfo]::InvariantCulture) + [double]::Parse($values[1],[cultureinfo]::InvariantCulture) + [double]::Parse($values[2],[cultureinfo]::InvariantCulture) + [double]::Parse($values[3],[cultureinfo]::InvariantCulture)) -le 0) { throw 'Blank printed page' }
                }
                & $python (Join-Path $PSScriptRoot 'test_vector_rejection.py') $temp $name
                if ($LASTEXITCODE) { throw 'Vector preflight rejection checks failed' }
                Write-Output 'PASS: 52 nonblank vector pages, no image XObjects, bounded peak memory'
                exit 0
            }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'The Windows printer did not produce all 52 pages'
} finally {
    Remove-Printer -Name $name -ErrorAction SilentlyContinue
    Remove-PrinterPort -Name $result -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force
}
