# SPDX-License-Identifier: GPL-3.0-or-later
param([switch]$SmokeTest, [double]$SmokeScale=1, [switch]$SmokeSmall, [string]$SmokeCapture)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public static class SettingsDpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
$null = [SettingsDpi]::SetProcessDPIAware()
[System.Windows.Forms.Application]::EnableVisualStyles()
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root 'runtime\python.exe'
$app = Join-Path $root 'app.py'
$store = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$configPath = Join-Path $store 'settings.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$statusFile = Join-Path $store 'mode-status.txt'
if (-not $SmokeTest -and (Test-Path $statusFile)) {
    $null = [Windows.Forms.MessageBox]::Show([IO.File]::ReadAllText($statusFile),'Voucher Reorder','OK','Information')
    Remove-Item $statusFile
}
$form = New-Object Windows.Forms.Form
$form.Text = 'Voucher Reorder'
$form.AutoScaleDimensions = [Drawing.SizeF]::new(96,96)
$form.AutoScaleMode = 'Dpi'
$form.MinimumSize = [Drawing.Size]::new(360,300)
$form.ClientSize = [Drawing.Size]::new(680, [Math]::Min(660, [Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Height - 80))
$form.StartPosition = 'CenterScreen'; $form.Font = New-Object Drawing.Font('Segoe UI', 10)
$form.Icon = [Drawing.Icon]::new((Join-Path $root 'packaging\printer.ico'))
$form.ShowInTaskbar = $true
function Fit-SettingsWindow {
    $area = [Windows.Forms.Screen]::FromControl($form).WorkingArea
    $form.Width = [Math]::Min($form.Width,$area.Width)
    $form.Height = [Math]::Min($form.Height,$area.Height)
    $form.Left = [Math]::Max($area.Left,[Math]::Min($form.Left,$area.Right-$form.Width))
    $form.Top = [Math]::Max($area.Top,[Math]::Min($form.Top,$area.Bottom-$form.Height))
}
$form.Add_Shown({ Fit-SettingsWindow; $form.TopMost = $true; $form.Activate(); $form.BringToFront(); $form.TopMost = $false })
$tabs = New-Object Windows.Forms.TabControl; $tabs.Dock = 'Fill'
$printTab = New-Object Windows.Forms.TabPage; $printTab.Text = 'Print and setup'; $printTab.AutoScroll = $true
$alignTab = New-Object Windows.Forms.TabPage; $alignTab.Text = 'Section order and alignment'; $alignTab.AutoScroll = $true
$tabs.TabPages.Add($printTab); $tabs.TabPages.Add($alignTab); $form.Controls.Add($tabs)
$script:container = $printTab
function Label($text, $x, $y, $w=620, $h=25) {
    $c = New-Object Windows.Forms.Label; $c.Text = $text; $c.SetBounds($x,$y,$w,$h)
    $script:container.Controls.Add($c); return $c
}
function Edit($text, $x, $y, $w=100) {
    $c = New-Object Windows.Forms.TextBox; $c.Text = [string]$text; $c.SetBounds($x,$y,$w,27)
    $script:container.Controls.Add($c); return $c
}
function Button($text, $x, $y, $w, $action) {
    $c = New-Object Windows.Forms.Button; $c.Text = $text; $c.SetBounds($x,$y,$w,32)
    $c.Add_Click($action); $script:container.Controls.Add($c); return $c
}
function Combo($x,$y,$w) {
    $c = New-Object Windows.Forms.ComboBox; $c.SetBounds($x,$y,$w,28); $c.DropDownStyle = 'DropDownList'
    $script:container.Controls.Add($c); return $c
}
function Show-Error($text) { $null = [Windows.Forms.MessageBox]::Show([string]$text,'Voucher Reorder','OK','Warning') }
$modeLabel = Label '' 15 12 620 27
function Refresh-Mode {
    $latest = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $modeLabel.Text = if ($latest.mode -eq 'virtual') { 'Active mode: Virtual printer (print to Voucher Reorder)' } else { 'Active mode: PDF handoff (no administrator needed)' }
}
Refresh-Mode
$script:setupProcess = $null
function Start-ModeSetup($action) {
    if ($null -ne $script:setupProcess) { return }
    try {
        Remove-Item -LiteralPath $statusFile -ErrorAction SilentlyContinue
        $modeLabel.Text = if ($action -eq 'virtual') { 'Setting up the Voucher Reorder printer...' } else { 'Switching to PDF handoff...' }
        $enableVirtual.Enabled = $false; $switchPdf.Enabled = $false
        $setupProgress.Visible = $true
        # No -Wait: Windows PowerShell requests the one optional elevation.
        if ($SmokeTest) {
            $script:setupProcess = Start-Process -FilePath $python -ArgumentList @('-c', '"import time; time.sleep(1)"') -WindowStyle Hidden -PassThru
            return
        }
        $script:setupProcess = Start-Process -FilePath $python -ArgumentList @(('"' + (Join-Path $root 'packaging\mode_setup.py') + '"'), $action, '--ui') -WindowStyle Hidden -PassThru
    } catch {
        $enableVirtual.Enabled = $true; $switchPdf.Enabled = $true; $setupProgress.Visible = $false
        $modeLabel.Text = 'Printer setup could not start. PDF handoff remains available.'
        Show-Error $modeLabel.Text
    }
}
$enableVirtual = Button 'Enable virtual printer (UAC)' 15 43 300 { Start-ModeSetup 'virtual' }
$switchPdf = Button 'Switch to PDF handoff' 335 43 300 { Start-ModeSetup 'pdf' }
$setupProgress = New-Object Windows.Forms.ProgressBar
$setupProgress.SetBounds(15,77,620,6); $setupProgress.Style = 'Marquee'; $setupProgress.Visible = $false
$printTab.Controls.Add($setupProgress)
$null = Label 'PDF handoff: print from QuickBooks to Microsoft Print to PDF (if available), then save a new PDF in this Inbox. Or use Print a PDF below. Originals stay until you delete them.' 15 85 620 55
$inbox = Edit (Join-Path $store 'Inbox') 15 145 620; $inbox.ReadOnly = $true
$null = Button 'Open Inbox' 15 180 140 { Start-Process explorer.exe -ArgumentList ('"' + $inbox.Text + '"') }
$null = Button 'Copy Inbox path' 165 180 180 { [Windows.Forms.Clipboard]::SetText($inbox.Text) }
$watch = New-Object Windows.Forms.CheckBox
$watch.Text = 'Automatically reorder PDFs saved to the Inbox'
$watch.Checked = $config.watch_inbox; $watch.SetBounds(15,218,620,30); $printTab.Controls.Add($watch)
$null = Label 'Output: printer or reordered PDF file' 15 258
$printers = Combo 15 285 620
$null = Label 'Paper size' 15 325 300
$null = Label 'Paper tray' 345 325 290
$paper = Combo 15 350 320; $tray = Combo 345 350 290
$paperInfo = Label '' 15 390 620 55
$pdfChoice = 'Save reordered PDF'
function Is-PdfOutput { return ($printers.SelectedItem -eq $pdfChoice) }
function Is-ExcludedPrinter($name) { return ([string]$name -match '(?i)PDF|XPS' -or ([string]$name).Trim() -eq 'Voucher Reorder') }
$script:papers = @(); $script:trays = @()
$refreshPaper = {
    try {
        $paper.Items.Clear(); $tray.Items.Clear(); $script:papers = @(); $script:trays = @()
        if ($null -eq $printers.SelectedItem) { return }
        $pdfOutput = Is-PdfOutput
        $outputLabel.Visible = $pdfOutput; $outputFolder.Visible = $pdfOutput; $browseOutput.Visible = $pdfOutput
        if ($pdfOutput) {
            $script:papers = @(
                [Drawing.Printing.PaperSize]::new('Letter',850,1100),
                [Drawing.Printing.PaperSize]::new('Legal',850,1400),
                [Drawing.Printing.PaperSize]::new('A4',827,1169))
            $script:papers[0].RawKind=1; $script:papers[1].RawKind=5; $script:papers[2].RawKind=9
            # Preserve a previously selected driver-specific paper size.
            if ($config.paper_kind -notin @(1,5,9)) {
                $custom = [Drawing.Printing.PaperSize]::new('Saved paper', [int]($config.paper_width*100), [int]($config.paper_height*100))
                $custom.RawKind = $config.paper_kind; $script:papers += $custom
            }
        } else {
            $p = New-Object Drawing.Printing.PrinterSettings; $p.PrinterName = [string]$printers.SelectedItem
            if (-not $p.IsValid) { throw 'This printer is unavailable. Check its Windows connection.' }
            $script:papers = @($p.PaperSizes | Where-Object { $_.RawKind -gt 0 })
        }
        foreach ($item in $script:papers) { $null = $paper.Items.Add(('{0} ({1} x {2} in)' -f $item.PaperName,($item.Width/100),($item.Height/100))) }
        for ($i=0; $i -lt $script:papers.Count; $i++) { if ($script:papers[$i].RawKind -eq $config.paper_kind) { $paper.SelectedIndex = $i; break } }
        if ($paper.SelectedIndex -lt 0 -and $paper.Items.Count) { $paper.SelectedIndex = 0 }
        $null = $tray.Items.Add('Printer default')
        $script:trays = if ($pdfOutput) { @() } else { @($p.PaperSources) }
        $tray.Enabled = -not $pdfOutput
        foreach ($item in $script:trays) { $null = $tray.Items.Add($item.SourceName) }
        $tray.SelectedIndex = 0
        for ($i=0; $i -lt $script:trays.Count; $i++) { if ($script:trays[$i].RawKind -eq $config.tray) { $tray.SelectedIndex = $i+1 } }
    } catch { $paperInfo.Text = 'Printer information unavailable. Refresh after reconnecting the printer.' }
}
$showMargins = {
    try {
        if ($paper.SelectedIndex -lt 0) { return }
        if (Is-PdfOutput) {
            $paperInfo.Text = 'Saves vector PDFs at actual size without a printer driver. Choose an output folder below, outside the Inbox.'
            return
        }
        $p = New-Object Drawing.Printing.PrinterSettings; $p.PrinterName = [string]$printers.SelectedItem
        $page = $p.DefaultPageSettings; $page.Landscape = $false; $page.PaperSize = $script:papers[$paper.SelectedIndex]
        $area = $page.PrintableArea
        $paperInfo.Text = '100% actual size, one-sided. Driver printable area: {0:N2} x {1:N2} in; starts {2:N2} in from left, {3:N2} in from top. Confirm with plain paper.' -f ($area.Width/100),($area.Height/100),($area.Left/100),($area.Top/100)
    } catch { $paperInfo.Text = 'Margins could not be read. Use an alignment page to measure them.' }
}
$paper.Add_SelectedIndexChanged($showMargins)
$printers.Add_SelectedIndexChanged($refreshPaper)
function Refresh-Printers {
    $selected = $printers.SelectedItem
    $printers.Items.Clear()
    $null = $printers.Items.Add($pdfChoice)
    [Drawing.Printing.PrinterSettings]::InstalledPrinters | Sort-Object | Where-Object { -not (Is-ExcludedPrinter $_) } | ForEach-Object { $null = $printers.Items.Add($_) }
    $choice = if ($selected) { $selected } elseif ($config.output_mode -eq 'pdf' -or (Is-ExcludedPrinter $config.printer)) { $pdfChoice } else { $config.printer }
    $printers.SelectedItem = if ($printers.Items.Contains($choice)) { $choice } else { $pdfChoice }
}
$outputLabel = Label 'Folder for reordered PDFs' 15 452 620 25
$outputFolder = Edit $config.output_folder 15 480 485
$browseOutput = Button 'Browse...' 510 478 125 {
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Choose a folder for reordered PDFs, outside the Inbox'
    $dialog.SelectedPath = $outputFolder.Text
    try { if ($dialog.ShowDialog() -eq 'OK') { $outputFolder.Text = $dialog.SelectedPath } } finally { $dialog.Dispose() }
}
Refresh-Printers
$null = Button 'Refresh printers' 355 180 280 { Refresh-Printers }
$notice = Label 'Start with plain paper. Confirm section order on the Alignment tab.' 15 525 620 60

# Layout owns every row: no absolutely positioned preview can overlap a selector.
$layout = New-Object Windows.Forms.TableLayoutPanel
$layout.Dock = 'Top'; $layout.AutoSize = $true; $layout.AutoSizeMode = 'GrowAndShrink'
$layout.ColumnCount = 2; $layout.Padding = [Windows.Forms.Padding]::new(12)
$layout.MinimumSize = [Drawing.Size]::new(0,0)
$null = $layout.ColumnStyles.Add([Windows.Forms.ColumnStyle]::new('Percent',50))
$null = $layout.ColumnStyles.Add([Windows.Forms.ColumnStyle]::new('Percent',50))
$alignTab.Controls.Add($layout)
function Cell($control,$column,$row,$span=1) {
    while ($layout.RowStyles.Count -le $row) { $null = $layout.RowStyles.Add([Windows.Forms.RowStyle]::new('AutoSize')) }
    $control.Margin = [Windows.Forms.Padding]::new(4,5,4,5)
    $control.Dock = 'Fill'; $layout.Controls.Add($control,$column,$row)
    if ($span -gt 1) { $layout.SetColumnSpan($control,$span) }
}
function Caption($text) {
    $c = New-Object Windows.Forms.Label; $c.Text = $text; $c.AutoSize = $true; return $c
}
Cell (Caption 'Source page (QuickBooks), top to bottom') 0 0
Cell (Caption 'Printed output (physical stock), top to bottom') 1 0
$names = @('Check','Stub 1','Stub 2')
$orders = @(@(0,1,2),@(0,2,1),@(1,0,2),@(1,2,0),@(2,0,1),@(2,1,0))
$sourceOrder = New-Object Windows.Forms.ComboBox; $sourceOrder.DropDownStyle = 'DropDownList'
$order = New-Object Windows.Forms.ComboBox; $order.DropDownStyle = 'DropDownList'
Cell $sourceOrder 0 1; Cell $order 1 1
foreach ($o in $orders) {
    $text = ($o | ForEach-Object { $names[$_] }) -join ' / '
    $null = $order.Items.Add($text); $null = $sourceOrder.Items.Add($text)
}
$sourceOrder.SelectedIndex = 0
for ($i=0; $i -lt 6; $i++) {
    if (($orders[$i] -join ',') -eq ($config.order -join ',')) { $order.SelectedIndex = $i }
    if (($orders[$i] -join ',') -eq ($config.source_order -join ',')) { $sourceOrder.SelectedIndex = $i }
}
$sourcePicture = @(); $picture = @()
for ($i=0; $i -lt 3; $i++) {
    foreach ($column in 0,1) {
        $c = New-Object Windows.Forms.Label
        $c.MinimumSize = [Drawing.Size]::new(0,45); $c.TextAlign = 'MiddleCenter'; $c.BorderStyle = 'FixedSingle'
        Cell $c $column ($i+2)
        if ($column -eq 0) { $sourcePicture += $c } else { $picture += $c }
    }
}
$draw = {
    if ($order.SelectedIndex -lt 0 -or $sourceOrder.SelectedIndex -lt 0) { return }
    $src = $orders[$sourceOrder.SelectedIndex]; $dst = $orders[$order.SelectedIndex]
    for ($j=0; $j -lt 3; $j++) {
        $section = $src[$j]; $destination = [array]::IndexOf($dst,$section)+1
        $sourcePicture[$j].Text = "{0}`nTo output section {1}" -f $names[$section],$destination
        $sourcePicture[$j].BackColor = @([Drawing.Color]::LightBlue,[Drawing.Color]::Honeydew,[Drawing.Color]::LemonChiffon)[$section]
        $section = $dst[$j]; $origin = [array]::IndexOf($src,$section)+1
        $picture[$j].Text = "{0}`nFrom source section {1}" -f $names[$section],$origin
        $picture[$j].BackColor = @([Drawing.Color]::LightBlue,[Drawing.Color]::Honeydew,[Drawing.Color]::LemonChiffon)[$section]
    }
}
$order.Add_SelectedIndexChanged($draw); $sourceOrder.Add_SelectedIndexChanged($draw); & $draw
Cell (Caption 'Order preview is schematic. Sections keep their source heights when moved.') 0 5 2
Cell (Caption 'Nudges in inches follow the named section: positive X moves right; positive Y moves down.') 0 6 2
$nudges = New-Object Windows.Forms.TableLayoutPanel; $nudges.AutoSize = $true; $nudges.ColumnCount = 3
$nudges.Controls.Add((Caption 'Section'),0,0); $nudges.Controls.Add((Caption 'X (right / left)'),1,0); $nudges.Controls.Add((Caption 'Y (down / up)'),2,0)
$xs=@(); $ys=@()
for ($i=0; $i -lt 3; $i++) {
    $nudges.Controls.Add((Caption $names[$i]),0,($i+1))
    $x=New-Object Windows.Forms.TextBox; $x.Text=[string]$config.offsets[$i][0]; $xs += $x
    $y=New-Object Windows.Forms.TextBox; $y.Text=[string]$config.offsets[$i][1]; $ys += $y
    $nudges.Controls.Add($x,1,($i+1)); $nudges.Controls.Add($y,2,($i+1))
}
Cell $nudges 0 7 2
Cell (Caption 'Section heights: leave blank if your source page has three equal sections.') 0 8 2
Cell (Caption 'For unequal sections, measure both dividing lines from the TOP of the SOURCE page, in inches. For heights 3.5 / 3.5 / 4, enter 3.5 and 7. Nudges clip at section edges.') 0 9 2
Cell (Caption 'First dividing line (inches from top)') 0 10
Cell (Caption 'Second dividing line (inches from top)') 1 10
$bound1=New-Object Windows.Forms.TextBox; $bound2=New-Object Windows.Forms.TextBox
if ($null -ne $config.boundaries) { $bound1.Text=$config.boundaries[0]; $bound2.Text=$config.boundaries[1] }
Cell $bound1 0 11; Cell $bound2 1 11
$alignmentNotice = Caption ''; Cell $alignmentNotice 0 12 2
function Save-Settings {
    if ($null -ne $script:setupProcess) { throw 'Wait for printer setup to finish before saving settings.' }
    if ($null -eq $printers.SelectedItem -or $paper.SelectedIndex -lt 0 -or $order.SelectedIndex -lt 0 -or $sourceOrder.SelectedIndex -lt 0) { throw 'Select an output, paper size and both section orders.' }
    if (([string]$printers.SelectedItem).Trim() -eq 'Voucher Reorder') { throw 'Voucher Reorder cannot be the output printer (printing loop).' }
    $offsets=@(); for ($i=0; $i -lt 3; $i++) { $offsets+=,@([double]::Parse($xs[$i].Text),[double]::Parse($ys[$i].Text)) }
    $bounds=$null; if ($bound1.Text -or $bound2.Text) { $bounds=@([double]::Parse($bound1.Text),[double]::Parse($bound2.Text)) }
    $latest=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $selectedPaper=$script:papers[$paper.SelectedIndex]
    $trayKind=0; if ($tray.SelectedIndex -gt 0) { $trayKind=$script:trays[$tray.SelectedIndex-1].RawKind }
    $pdfOutput=Is-PdfOutput
    if ($pdfOutput -and -not $outputFolder.Text) { throw 'Choose a folder for reordered PDFs using Browse.' }
    $outputMode=if ($pdfOutput) { 'pdf' } else { 'printer' }
    $printerName=if ($printers.SelectedItem -eq $pdfChoice) { '' } else { [string]$printers.SelectedItem }
    $value=@{printer=$printerName; output_mode=$outputMode; output_folder=$outputFolder.Text; mode=$latest.mode; watch_inbox=$watch.Checked;
        paper_kind=$selectedPaper.RawKind; paper_width=$selectedPaper.Width/100; paper_height=$selectedPaper.Height/100;
        tray=$trayKind; source_order=$orders[$sourceOrder.SelectedIndex]; order=$orders[$order.SelectedIndex]; boundaries=$bounds; offsets=$offsets}
    $temp=Join-Path $store ('settings-'+[guid]::NewGuid().ToString('N')+'.json')
    try {
        $value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temp -Encoding UTF8
        & $python $app validate --config $temp
        if ($LASTEXITCODE -ne 0) { throw 'Check dividing lines (inside the source sheet), nudges (-1 to +1 inch), and an absolute output folder outside the Inbox.' }
        [IO.File]::Replace($temp,$configPath,[NullString]::Value); $notice.Text='Settings saved. Check Job status after processing a test page.'; $alignmentNotice.Text=$notice.Text
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp } }
}
$saveAlignment = New-Object Windows.Forms.Button; $saveAlignment.Text = 'Save settings'; $saveAlignment.AutoSize = $true
$saveAlignment.Add_Click({ try { Save-Settings } catch { Show-Error $_.Exception.Message } }); Cell $saveAlignment 0 13 2
$script:container=$printTab
$null = Button 'Save settings' 15 600 150 { try { Save-Settings } catch { Show-Error $_.Exception.Message } }
$null = Button 'Print alignment test' 180 600 220 {
    try {
        Save-Settings
        $text=(& $python $app alignment | Out-String)
        if ($LASTEXITCODE -ne 0) { throw 'Could not queue the alignment page.' }
        $notice.Text=$text
        if ((Is-PdfOutput) -and $text -match 'Alignment job: ([a-zA-Z0-9-]+)') { $script:alignmentJob=$Matches[1] }
    } catch { Show-Error $_.Exception.Message }
}
$null = Button 'Print a PDF...' 415 600 220 {
    try {
        Save-Settings
        $dialog=New-Object Windows.Forms.OpenFileDialog; $dialog.Filter='PDF files (*.pdf)|*.pdf'; $dialog.InitialDirectory=$inbox.Text
        if ($dialog.ShowDialog() -eq 'OK') {
            $text=(& $python $app submit --file $dialog.FileName | Out-String)
            if ($LASTEXITCODE -ne 0) { throw 'PDF could not be received. Wait for saving to finish and check that it is unencrypted and under 100 MiB.' }
            $notice.Text=$text
        }
    } catch { Show-Error $_.Exception.Message }
}
$null = Button 'Job status' 15 645 150 {
    $dialog=New-Object Windows.Forms.Form
    $dialog.Text='Job status'; $dialog.Size=New-Object Drawing.Size(780,550)
    $dialog.StartPosition='CenterParent'
    $summary=New-Object Windows.Forms.TextBox
    $summary.Multiline=$true; $summary.ReadOnly=$true; $summary.ScrollBars='Vertical'
    $summary.SetBounds(15,15,730,180)
    $summary.Text=(& $python $app status | Out-String)
    $dialog.Controls.Add($summary)
    $list=New-Object Windows.Forms.ListBox
    $list.SetBounds(15,210,730,180)
    $failures=@(Get-ChildItem (Join-Path $store 'jobs\*\state.json') -ErrorAction SilentlyContinue | ForEach-Object {
        $job=Get-Content $_.FullName -Raw | ConvertFrom-Json
        if ($job.state -in @('failed','review')) {
            [pscustomobject]@{Id=$_.Directory.Name; Label="$($job.document) - $($job.state): $($job.message)"}
        }
    })
    $list.DisplayMember='Label'
    foreach ($failure in $failures) { $null=$list.Items.Add($failure) }
    $dialog.Controls.Add($list)
    $open=New-Object Windows.Forms.Button; $open.Text='Open folder'; $open.SetBounds(15,410,140,30)
    $open.Add_Click({
        $folder=Join-Path $store 'Needs attention'
        [IO.Directory]::CreateDirectory($folder) | Out-Null
        Start-Process explorer.exe -ArgumentList ('"'+$folder+'"')
    }); $dialog.Controls.Add($open)
    $retry=New-Object Windows.Forms.Button; $retry.Text='Retry'; $retry.SetBounds(170,410,140,30)
    $retry.Add_Click({
        if ($null -eq $list.SelectedItem) { return }
        $answer=[Windows.Forms.MessageBox]::Show('Check the physical output and printer queue first. Retry can print a duplicate. Retry this job with current settings?','Retry','YesNo','Warning')
        if ($answer -ne 'Yes') { return }
        & $python $app retry --file $list.SelectedItem.Id
        if ($LASTEXITCODE -eq 0) { $list.Items.Remove($list.SelectedItem) }
        $summary.Text=(& $python $app status | Out-String)
    }); $dialog.Controls.Add($retry)
    $pickup=New-Object Windows.Forms.Button; $pickup.Text='Retry pickup'; $pickup.SetBounds(325,410,140,30)
    $pickup.Add_Click({ & $python $app register }); $dialog.Controls.Add($pickup)
    $dismiss=New-Object Windows.Forms.Button; $dismiss.Text='Dismiss'; $dismiss.SetBounds(480,410,140,30)
    $dismiss.Add_Click({
        if ($null -eq $list.SelectedItem) { return }
        $selected=$list.SelectedItem
        & $python $app dismiss --file $selected.Id
        if ($LASTEXITCODE -eq 0) { $list.Items.Remove($selected) } else { Show-Error 'Could not dismiss this job.' }
        $summary.Text=(& $python $app status | Out-String)
    }); $dialog.Controls.Add($dismiss)
    $clear=New-Object Windows.Forms.Button; $clear.Text='Clear finished'; $clear.SetBounds(15,450,140,30)
    $clear.Add_Click({
        if ([Windows.Forms.MessageBox]::Show('Remove finished jobs from Job status now? Saved reordered PDFs remain in their output folder.','Clear finished','YesNo','Question') -ne 'Yes') { return }
        & $python $app clear-finished
        if ($LASTEXITCODE -ne 0) { Show-Error 'Could not clear finished jobs.' }
        $summary.Text=(& $python $app status | Out-String)
    }); $dialog.Controls.Add($clear)
    $null=$dialog.ShowDialog($form)
    $dialog.Dispose()
}
$null = Button 'Resume held jobs' 180 645 220 {
    if ([Windows.Forms.MessageBox]::Show('Resume jobs held during an update? They use the printer and alignment settings saved when received. Confirm the correct paper is loaded.','Resume held jobs','YesNo') -eq 'Yes') { & $python $app resume }
}
$null = Button 'Cancel waiting jobs' 415 645 220 {
    if ([Windows.Forms.MessageBox]::Show('Cancel waiting/held app jobs? Jobs already sent must be canceled in the real Windows printer queue. Check paper before reprinting.','Cancel jobs','YesNo') -eq 'Yes') { & $python $app discard }
}
$timer=New-Object Windows.Forms.Timer; $timer.Interval=500
$timer.Add_Tick({
    if ($script:alignmentJob) {
        $statePath=Join-Path $store ("jobs\$($script:alignmentJob)\state.json")
        if (Test-Path -LiteralPath $statePath) {
            $job=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            if ($job.state -eq 'sent' -and $job.message -like 'Saved reordered PDF: *') {
                $savedPath=$job.message.Substring('Saved reordered PDF: '.Length)
                $script:alignmentJob=$null
                if (Test-Path -LiteralPath $savedPath) { Start-Process explorer.exe -ArgumentList ('/select,"'+$savedPath+'"') }
            } elseif ($job.state -in @('failed','review')) { $script:alignmentJob=$null }
        }
    }
    if ($null -ne $script:setupProcess -and $script:setupProcess.HasExited) {
        $code = $script:setupProcess.ExitCode
        $script:setupProcess.Dispose(); $script:setupProcess = $null
        $enableVirtual.Enabled = $true; $switchPdf.Enabled = $true; $setupProgress.Visible = $false
        Refresh-Mode
        $detail = if (Test-Path -LiteralPath $statusFile) { [IO.File]::ReadAllText($statusFile) } else { 'Printer setup failed or was interrupted. PDF handoff remains available; try setup again.' }
        Remove-Item -LiteralPath $statusFile -ErrorAction SilentlyContinue
        $notice.Text = $detail
        $icon = if ($code -eq 0 -and $detail -notmatch 'failed|declined|unavailable|not removed|interrupted') { 'Information' } else { 'Warning' }
        if (-not $SmokeTest) { $null = [Windows.Forms.MessageBox]::Show($form,$detail,'Voucher Reorder','OK',$icon) }
    }
    if (Test-Path (Join-Path $store 'maintenance.json')) { $form.Close() }
})
if ($SmokeTest) {
    try {
        $form.Show(); $tabs.SelectedTab = $alignTab
        if ($SmokeScale -ne 1) {
            $form.Scale([Drawing.SizeF]::new($SmokeScale,$SmokeScale))
            $form.Font = [Drawing.Font]::new('Segoe UI', [single](10*$SmokeScale))
        }
        if ($SmokeSmall) { $form.ClientSize = [Drawing.Size]::new(420,320) }
        Fit-SettingsWindow
        [Windows.Forms.Application]::DoEvents()
        for ($a=0; $a -lt 6; $a++) {
            for ($b=0; $b -lt 6; $b++) {
                $sourceOrder.SelectedIndex=$a; $order.SelectedIndex=$b
                $layout.PerformLayout(); [Windows.Forms.Application]::DoEvents()
                foreach ($bands in @($sourcePicture,$picture)) {
                    for ($j=0; $j -lt 3; $j++) {
                        $band=$bands[$j]
                        if (-not $band.Text -or $band.Height -lt 40*$SmokeScale) { throw 'Preview band clipped or unlabeled' }
                        if ($j -gt 0 -and $band.Top -lt $bands[$j-1].Bottom) { throw 'Preview bands overlap' }
                        if ($band.Top -lt $order.Bottom) { throw 'Preview overlaps selector' }
                        if ($layout.Left+$band.Left -lt 0 -or $layout.Left+$band.Right -gt $alignTab.ClientSize.Width) { throw 'Preview requires horizontal scrolling' }
                        $measure=[Windows.Forms.TextRenderer]::MeasureText($band.Text,$band.Font)
                        if ($measure.Width -gt $band.Width -or $measure.Height -gt $band.Height) { throw 'Preview label does not fit' }
                    }
                }
            }
        }
        if ($SmokeCapture) {
            $sourceOrder.SelectedIndex=0; $order.SelectedIndex=2
            [Windows.Forms.Application]::DoEvents()
            $bitmap=[Drawing.Bitmap]::new($form.Width,$form.Height)
            try {
                $form.DrawToBitmap($bitmap,[Drawing.Rectangle]::new(0,0,$form.Width,$form.Height))
                $bitmap.Save($SmokeCapture,[Drawing.Imaging.ImageFormat]::Png)
            } finally { $bitmap.Dispose() }
            $sourceOrder.SelectedIndex=5; $order.SelectedIndex=5
        }
        # Small windows must scroll to the final settings action without losing bands.
        $alignTab.ScrollControlIntoView($saveAlignment); [Windows.Forms.Application]::DoEvents()
        if (-not $saveAlignment.Visible) { throw 'Cannot reach alignment save button' }
        $tabs.SelectedTab=$printTab
        $printers.SelectedItem=$pdfChoice
        if ($paper.Items.Count -lt 3 -or -not $outputFolder.Visible -or -not $outputLabel.Visible -or -not $browseOutput.Visible) { throw 'Printer-free PDF settings unavailable' }
        $outputFolder.Text=Join-Path $store 'Reordered'
        foreach ($choice in @('Microsoft Print to PDF','Microsoft XPS Document Writer','Voucher Reorder')) { if ($printers.Items.Contains($choice)) { throw 'Excluded printer is visible' } }
        Save-Settings
        $saved=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        if ($saved.output_mode -ne 'pdf' -or ($saved.source_order -join ',') -ne '2,1,0') { throw 'PDF output or source order was not saved' }
        if ($null -ne $saved.quickbooks_version -or $null -ne $saved.printer_model) { throw 'Obsolete fields remain' }
        $config.printer='Microsoft Print to PDF'; $config.output_mode='printer'; $printers.SelectedItem=$null; Refresh-Printers
        if ($printers.SelectedItem -ne $pdfChoice) { throw 'Legacy PDF printer was not mapped to PDF output' }
        $null=$printers.Items.Add('FAKE OFFICE PRINTER'); $printers.SelectedItem='FAKE OFFICE PRINTER'
        if ($outputFolder.Visible -or $outputLabel.Visible -or $browseOutput.Visible) { throw 'PDF folder controls visible for printer output' }
        $printers.SelectedItem=$pdfChoice
        $timer.Start(); Start-ModeSetup 'virtual'
        if ($enableVirtual.Enabled -or -not $setupProgress.Visible -or $modeLabel.Text -notlike 'Setting up*') { throw 'Setup feedback missing' }
        $deadline=(Get-Date).AddSeconds(15); $ticks=0
        while ($null -ne $script:setupProcess) {
            [Windows.Forms.Application]::DoEvents(); $ticks++
            if ((Get-Date) -gt $deadline) { throw 'Asynchronous setup did not complete' }
            Start-Sleep -Milliseconds 10
        }
        if ($ticks -lt 5 -or -not $enableVirtual.Enabled -or $setupProgress.Visible) { throw 'UI did not remain responsive through setup' }
        Write-Output "PASS: all 36 preview mappings, scale=$SmokeScale, small=$SmokeSmall, PDF output and responsive setup"
    } finally { $timer.Stop(); $timer.Dispose(); $form.Dispose() }
    exit 0
}
$form.Add_FormClosing({
    param($sender,$event)
    if ($null -ne $script:setupProcess -and -not (Test-Path (Join-Path $store 'maintenance.json'))) {
        $event.Cancel=$true
        $notice.Text='Printer setup is still running. Please wait for its result before closing.'
    }
})
$timer.Start()
try { $null=$form.ShowDialog() } finally { $timer.Stop(); $timer.Dispose(); $form.Dispose() }
