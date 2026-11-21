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
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapEncoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfPageRenderOptions,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$methods = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 }
$operation = $methods | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }
$action = $methods | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' }
function AwaitResult($async, $type) {
    $task = $operation.MakeGenericMethod($type).Invoke($null,@($async))
    $task.Wait()
    $task.Result
}
$file = AwaitResult ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Pdf)) ([Windows.Storage.StorageFile])
$document = AwaitResult ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
if ($document.PageCount -ne $Pages) { throw 'Page count changed in renderer.' }
Set-Location -LiteralPath (Split-Path $Pdf)
$dc = [CheckedPrint]::Open($Printer,$mode)
$finished = $false
try {
    $id = [CheckedPrint]::Begin($dc)
    [IO.File]::WriteAllText((Join-Path $PWD 'windows-job-id'),[string]$id)
    for ($i=1; $i -le $Pages; $i++) {
        $image = Join-Path $PWD 'page.bmp'
        [IO.File]::Delete($image)
        $sheet = $document.GetPage($i - 1)
        $memory = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
        try {
            $options = [Windows.Data.Pdf.PdfPageRenderOptions]::new()
            $options.DestinationWidth = [Math]::Round($sheet.Size.Width * 600 / 96)
            $options.DestinationHeight = [Math]::Round($sheet.Size.Height * 600 / 96)
            $options.BitmapEncoderId = [Windows.Graphics.Imaging.BitmapEncoder]::PngEncoderId
            $options.IsIgnoringHighContrast = $true
            if ([long]$options.DestinationWidth * $options.DestinationHeight * 4 -gt 256MB) { throw 'Rendered page exceeds limit.' }
            $render = $sheet.RenderToStreamAsync($memory,$options)
            $action.Invoke($null,@($render)).Wait()
            $memory.Seek(0)
            $stream = [IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($memory)
            $bitmap = [Drawing.Bitmap]::new($stream)
            try {
                $rgb = [Drawing.Bitmap]::new($bitmap.Width,$bitmap.Height,[Drawing.Imaging.PixelFormat]::Format24bppRgb)
                try {
                    $graphics = [Drawing.Graphics]::FromImage($rgb)
                    try {
                        $graphics.Clear([Drawing.Color]::White)
                        $graphics.DrawImageUnscaled($bitmap,0,0)
                    } finally { $graphics.Dispose() }
                    $rgb.Save($image,[Drawing.Imaging.ImageFormat]::Bmp)
                } finally { $rgb.Dispose() }
            } finally { $bitmap.Dispose(); $stream.Dispose() }
        } finally { $sheet.Dispose(); $memory.Dispose() }
        [CheckedPrint]::Page($dc,$image,$page.PaperSize.Width,$page.PaperSize.Height)
        [IO.File]::Delete($image)
    }
    [CheckedPrint]::Finish($dc)
    $finished = $true
} finally {
    [CheckedPrint]::Close($dc,$finished)
}
