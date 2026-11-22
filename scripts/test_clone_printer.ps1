# Real fixed-port driver acceptance. No PrintToFile flag or output filename in the application.
param([Parameter(Mandatory=$true)][string]$AppRoot)
$ErrorActionPreference='Stop'
$python=Join-Path $AppRoot 'runtime\python.exe'
$app=Join-Path $AppRoot 'app.py'
$data=Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$port=Join-Path $data 'Incoming\job.pdf'
& $python -c "from voucher_reorder.config import *; save(data_dir()/'settings.json',Settings(mode='virtual',output_mode='pdf',output_folder=str(data_dir()/'CI-output')))"
if ($LASTEXITCODE) { throw 'Could not configure output' }
& $python $app register
if ($LASTEXITCODE) { throw 'Watcher registration failed' }
Add-Type -AssemblyName System.Drawing
function Send-Document($count,$title) {
    Write-Output "Printing $title ($count pages)"
    $source=Join-Path $data 'CI-source.txt'
    Set-Content -LiteralPath $source -Value "VOID FAKE $title"
    $document=New-Object Drawing.Printing.PrintDocument
    $document.PrinterSettings.PrinterName='Voucher Reorder'
    $document.PrintController=New-Object Drawing.Printing.StandardPrintController
    $document.DocumentName=$title
    $script:page=0
    $script:pageCount=$count
    $script:sourceText=[IO.File]::ReadAllText($source)
    $document.add_PrintPage({
        param($sender,$event)
        $script:page++
        $font=New-Object Drawing.Font('Arial',12)
        try { $event.Graphics.DrawString("$script:sourceText PAGE $script:page",$font,[Drawing.Brushes]::Black,72,72) }
        finally { $font.Dispose() }
        $event.HasMorePages=$script:page -lt $script:pageCount
    })
    try { $document.Print(); Write-Output "Submitted $title" } finally { $document.Dispose() }
}
function Wait-Sent($count) {
    $deadline=[DateTime]::UtcNow.AddSeconds(90)
    do {
        $jobs=@(Get-ChildItem (Join-Path $data 'jobs\*\state.json') | ForEach-Object {Get-Content $_.FullName -Raw | ConvertFrom-Json})
        if (@($jobs | Where-Object state -in @('review','failed')).Count) { throw ($jobs | ConvertTo-Json -Depth 5) }
        if (@($jobs | Where-Object state -eq 'sent').Count -eq $count) { return }
        if ([DateTime]::UtcNow -gt $deadline) {
            Get-Content (Join-Path $data 'watcher.json') -ErrorAction SilentlyContinue
            Get-PrintJob -PrinterName 'Voucher Reorder' | Format-List
            throw 'No-dialog print did not reach the durable queue'
        }
        Start-Sleep -Milliseconds 100 # test harness only, never application scheduling
    } while ($true)
}
try {
    Send-Document 1 'FAKE no-dialog file'
    Wait-Sent 1
    # Submit two ten-page documents without waiting for pickup between them.
    Send-Document 10 'FAKE burst A'
    Send-Document 10 'FAKE burst B'
    Wait-Sent 3
    & $python -c "from pathlib import Path; from pypdf import PdfReader; from voucher_reorder.config import data_dir; r=data_dir(); assert sorted(len(PdfReader(p).pages) for p in (r/'CI-output').glob('*.pdf'))==[1,10,10]; assert not list((r/'jobs').glob('*/input.pdf')); assert not (r/'Incoming'/'job.pdf').exists()"
    if ($LASTEXITCODE) { throw 'Missing pages, overwritten input, or payload not deleted' }
    if (Test-Path (Join-Path $data 'printer-warning.json')) { throw (Get-Content (Join-Path $data 'printer-warning.json') -Raw) }
    Write-Output 'PASS: Microsoft Print To PDF fixed port, no output filename/dialog, three unique jobs (1/10/10 pages), delete after success'
} finally {
    & $python $app stop
}
