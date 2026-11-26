# Real unique-job driver acceptance. No PrintToFile flag or output filename in the application.
param([Parameter(Mandatory=$true)][string]$AppRoot)
$ErrorActionPreference='Stop'
$python=Join-Path $AppRoot 'runtime\python.exe'
$app=Join-Path $AppRoot 'app.py'
$data=Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$incoming=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) ('VoucherReorderPrinter\Spool\'+$sid)
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
    # Stop pickup entirely: both jobs must survive as separate files offline.
    & $python $app stop
    if ($LASTEXITCODE) { throw 'Could not stop watcher' }
    Send-Document 10 'FAKE burst A'
    Send-Document 10 'FAKE burst B'
    $deadline=[DateTime]::UtcNow.AddSeconds(60)
    while (@(Get-ChildItem -LiteralPath $incoming -Filter '*.ps').Count -ne 2) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Offline burst did not preserve two independent PostScript jobs' }
        Start-Sleep -Milliseconds 100
    }
    $spoolJobs=@(Get-ChildItem -LiteralPath $incoming -Filter '*.ps')
    if (@($spoolJobs | Select-Object -ExpandProperty Name -Unique).Count -ne 2) {
        throw 'Offline burst reused a spool filename'
    }
    & $python $app register
    if ($LASTEXITCODE) { throw 'Could not restart watcher' }
    Wait-Sent 3
    $verifyPython=(Get-Command python).Source
    & $verifyPython (Join-Path $PSScriptRoot 'verify_clone_output.py') (Join-Path $data 'CI-output')
    if ($LASTEXITCODE) { throw 'Burst PDFs have missing, blank, or duplicate rendered pages' }
    & $python -c "from voucher_reorder.config import data_dir; from voucher_reorder.spool import incoming_folder; r=data_dir(); assert not list((r/'jobs').glob('*/input.ps')); assert not list((r/'jobs').glob('*/input.pdf')); assert not list(incoming_folder().glob('*.ps')); assert not list(incoming_folder().glob('*.pdf'))"
    if ($LASTEXITCODE) { throw 'Missing pages, overwritten input, or payload not deleted' }
    if (Test-Path (Join-Path $data 'printer-warning.json')) { throw (Get-Content (Join-Path $data 'printer-warning.json') -Raw) }
    Write-Output 'PASS: MS Publisher Imagesetter protected port, no output filename/dialog, distinct complete offline burst jobs (1/10/10 pages), delete after success'
} finally {
    & $python $app stop
}
