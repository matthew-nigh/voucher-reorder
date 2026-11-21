param([string]$Printer,[int]$PaperKind,[int]$Tray,[string]$Pdf,[int]$Pages)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -Path (Join-Path $PSScriptRoot 'CheckedPrint.cs')
$p = New-Object Drawing.Printing.PrinterSettings
$p.PrinterName = $Printer
$p.Copies = 1
if ($p.CanDuplex) { $p.Duplex = [Drawing.Printing.Duplex]::Simplex }
$page = $p.DefaultPageSettings
$page.Landscape = $false
$page.PaperSize = @($p.PaperSizes | Where-Object RawKind -eq $PaperKind)[0]
if ($Tray) { $page.PaperSource = @($p.PaperSources | Where-Object RawKind -eq $Tray)[0] }
$mode = $p.GetHdevmode($page)
$gs = Join-Path (Split-Path $PSScriptRoot) 'vendor\ghostscript\bin\gswin64c.exe'
Set-Location -LiteralPath (Split-Path $Pdf)
$dc = [CheckedPrint]::Open($Printer,$mode)
$finished = $false
try {
    $id = [CheckedPrint]::Begin($dc)
    [IO.File]::WriteAllText((Join-Path $PWD 'windows-job-id'),[string]$id)
    for ($i=1; $i -le $Pages; $i++) {
        $image = Join-Path $PWD 'page.bmp'
        [IO.File]::Delete($image)
        & $gs '-q' '-dSAFER' '-dBATCH' '-dNOPAUSE' '-dPDFSTOPONERROR' '-r600' '-sDEVICE=bmp16m' "-dFirstPage=$i" "-dLastPage=$i" '-sOutputFile=page.bmp' '-f' $Pdf
        if ($LASTEXITCODE -ne 0) { throw 'Page rendering failed.' }
        [CheckedPrint]::Page($dc,$image,$page.PaperSize.Width,$page.PaperSize.Height)
        [IO.File]::Delete($image)
    }
    [CheckedPrint]::Finish($dc)
    $finished = $true
} finally {
    [CheckedPrint]::Close($dc,$finished)
}
