param([string]$Printer, [int]$PaperKind = 1)
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

[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Drawing
$p = New-Object Drawing.Printing.PrinterSettings
$p.PrinterName = $Printer
if (-not $p.IsValid) { throw 'The selected printer is not installed or accessible.' }
$paper = @($p.PaperSizes | Where-Object { $_.RawKind -eq $PaperKind })
if ($paper.Count -ne 1) { throw 'Select a supported paper size in Settings.' }
$page = $p.DefaultPageSettings
$landscape = $page.Landscape
$page.Landscape = $false
$page.PaperSize = $paper[0]
$area = $page.PrintableArea
@{width=$paper[0].Width/100; height=$paper[0].Height/100; landscape=$landscape;
  left=$area.Left/100; top=$area.Top/100; printable_width=$area.Width/100;
  printable_height=$area.Height/100; trays=@($p.PaperSources | ForEach-Object { $_.RawKind })} | ConvertTo-Json -Compress
