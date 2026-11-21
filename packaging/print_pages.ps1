param([string]$Printer,[int]$PaperKind,[int]$Tray,[string]$Pdf,[int]$Pages)
$ErrorActionPreference = 'Stop'
trap {
    $errorRecord = $_
    $e = $_.Exception
    while ($e) {
        [Console]::Error.WriteLine("VRPRINT {0} HRESULT={1} line={2}: {3}", $e.GetType().Name, $e.HResult, $errorRecord.InvocationInfo.ScriptLineNumber, $e.Message)
        $e = $e.InnerException
    }
    exit 7
}

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
$dc = [CheckedPrint]::Open($Printer,$mode)
$finished = $false
try {
    $library = Join-Path (Split-Path $PSScriptRoot) 'vendor\pdfium\pdfium.dll'
    [CheckedPrint]::Print($dc,$library,$Pdf,$Pages,$page.PaperSize.Width,$page.PaperSize.Height)
    $finished = $true
} finally {
    [CheckedPrint]::Close($dc,$finished)
}
