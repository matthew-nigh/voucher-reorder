# Windows acceptance diagnostic for the selectable Microsoft Print to PDF queue.
$ErrorActionPreference = 'Stop'
$appRoot = Join-Path $PSScriptRoot '..\build\windows'
$python = Join-Path $appRoot 'runtime\python.exe'
$app = Join-Path $appRoot 'app.py'
$data = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$mode = Join-Path $appRoot 'packaging\mode_setup.py'
$child = Join-Path $PSScriptRoot 'probe_pdf_overlap.ps1'
$run = [guid]::NewGuid().ToString('N')
$outputFolder = Join-Path $data ('CI-PDF-burst-' + $run)
$processes = [Collections.Generic.List[object]]::new()
try {
    & $python $mode pdf-printer --ui
    $configured = Get-Content (Join-Path $data 'settings.json') -Raw | ConvertFrom-Json
    if ($LASTEXITCODE -or $configured.mode -ne 'virtual' -or $configured.virtual_variant -ne 'print_to_pdf') {
        $code = Get-Content (Join-Path $data 'printer-setup-code.txt') -ErrorAction SilentlyContinue
        throw "PDF virtual printer setup failed; helper code=$code"
    }
    & $python -c "from voucher_reorder.config import *; from dataclasses import replace; p=data_dir()/'settings.json'; save(p,replace(load(p),output_mode='pdf',output_folder=str(data_dir()/'CI-PDF-burst-$run')))"
    if ($LASTEXITCODE) { throw 'PDF burst settings failed' }
    & $python $app register
    if ($LASTEXITCODE) { throw 'PDF burst watcher registration failed' }
    $before = @(Get-ChildItem (Join-Path $data 'jobs\*\state.json') -ErrorAction SilentlyContinue).Count
    $cases = @(1,3,10,1,3,10,1,3,10,1)
    for ($i=0; $i -lt $cases.Count; $i++) {
        $title = "BURST-$run-$i"
        $marker = Join-Path $data "$title.tick"
        $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $child + '" -ChildPrint -PrinterName "Voucher Reorder" -Pages ' + $cases[$i] + ' -Title "' + $title + '" -Marker "' + $marker + '"'
        $processes.Add((Start-Process (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $args -PassThru -WindowStyle Hidden))
    }
    foreach ($process in $processes) { if (-not $process.WaitForExit(60000) -or $process.ExitCode) { throw 'A concurrent PDF print child failed' } }
    for ($i=0; $i -lt 5; $i++) {
        $title = "RAPID-$run-$i"
        $marker = Join-Path $data "$title.tick"
        $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $child + '" -ChildPrint -PrinterName "Voucher Reorder" -Pages ' + @(1,3,10,1,3)[$i] + ' -Title "' + $title + '" -Marker "' + $marker + '"'
        $process = Start-Process (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $args -PassThru -WindowStyle Hidden
        $processes.Add($process)
        Start-Sleep -Milliseconds 350
    }
    foreach ($process in $processes) { if (-not $process.WaitForExit(60000) -or $process.ExitCode) { throw 'A rapid PDF print child failed' } }
    $deadline = (Get-Date).AddSeconds(90)
    do {
        $states = @(Get-ChildItem (Join-Path $data 'jobs\*\state.json') -ErrorAction SilentlyContinue)
        $added = $states.Count - $before
        $queued = @(Get-PrintJob -PrinterName 'Voucher Reorder' -ErrorAction SilentlyContinue).Count
        if ($queued -eq 0 -and $added -ge 15 -and @(Get-ChildItem $outputFolder -Filter '*.pdf' -ErrorAction SilentlyContinue).Count -ge 15) { break }
        if ((Get-Date) -ge $deadline) { break }
        Start-Sleep -Milliseconds 100
    } while ($true)
    $results = @(& python (Join-Path $PSScriptRoot 'verify_pdf_overlap.py') $outputFolder | ConvertFrom-Json)
    if ($LASTEXITCODE) { throw 'PDF burst output verification failed' }
    $files = $results.Count
    $pages = @($results | Where-Object valid | Group-Object pages | Sort-Object { [int]$_.Name } | ForEach-Object { "$($_.Name):$($_.Count)" }) -join ','
    $distinct = @($results | Where-Object valid | Select-Object -ExpandProperty fingerprint -Unique).Count
    $warning = Join-Path $data 'printer-warning.json'
    $warnText = if (Test-Path $warning) { (Get-Content $warning -Raw | ConvertFrom-Json).error } else { 'none' }
    $preserved = ($added -eq 15 -and $files -eq 15 -and $distinct -eq 15 -and $pages -eq '1:6,3:5,10:4')
    Write-Output "PDF BURST: submitted=15 concurrent=10 rapid=5 collected=$added output-files=$files distinct=$distinct pages=$pages all-preserved=$preserved warning=$warnText"
} finally {
    foreach ($process in $processes) { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } }
    & $python $app stop
    & $python $mode remove --ui
}
