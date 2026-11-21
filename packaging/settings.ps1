# SPDX-License-Identifier: GPL-3.0-or-later
param([switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root 'runtime\python.exe'
$app = Join-Path $root 'app.py'
$store = Join-Path $env:LOCALAPPDATA 'VoucherReorder'
$configPath = Join-Path $store 'settings.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$form = New-Object Windows.Forms.Form
$form.Text = 'Voucher Reorder'
$form.ClientSize = [Drawing.Size]::new(680, [Math]::Min(660, [Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Height - 80))
$form.StartPosition = 'CenterScreen'; $form.Font = New-Object Drawing.Font('Segoe UI', 10)
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
    $c.Add_Click($action); $script:container.Controls.Add($c)
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
Button 'Enable virtual printer (UAC)' 15 43 300 {
    & $python (Join-Path $root 'packaging\mode_setup.py') virtual
    Refresh-Mode
}
Button 'Switch to PDF handoff' 335 43 300 {
    & $python (Join-Path $root 'packaging\mode_setup.py') pdf
    Refresh-Mode
}
$null = Label 'PDF handoff: print from QuickBooks to Microsoft Print to PDF (if available), then save a new PDF in this Inbox. Or use Print a PDF below. Originals stay until you delete them.' 15 85 620 55
$inbox = Edit (Join-Path $store 'Inbox') 15 145 620; $inbox.ReadOnly = $true
Button 'Open Inbox' 15 180 140 { Start-Process explorer.exe -ArgumentList ('"' + $inbox.Text + '"') }
Button 'Copy Inbox path' 165 180 180 { [Windows.Forms.Clipboard]::SetText($inbox.Text) }
$null = Label 'Real printer (all installed printers are listed)' 15 225
$printers = Combo 15 255 620
$null = Label 'Paper size' 15 295 300
$null = Label 'Paper tray' 345 295 290
$paper = Combo 15 325 320; $tray = Combo 345 325 290
$paperInfo = Label '' 15 365 620 55
$script:papers = @(); $script:trays = @()
$refreshPaper = {
    try {
        $paper.Items.Clear(); $tray.Items.Clear(); $script:papers = @(); $script:trays = @()
        if ($null -eq $printers.SelectedItem) { return }
        $p = New-Object Drawing.Printing.PrinterSettings; $p.PrinterName = [string]$printers.SelectedItem
        if (-not $p.IsValid) { throw 'This printer is unavailable. Check its Windows connection.' }
        $script:papers = @($p.PaperSizes | Where-Object { $_.RawKind -gt 0 })
        foreach ($item in $script:papers) { $null = $paper.Items.Add(('{0} ({1} x {2} in)' -f $item.PaperName,($item.Width/100),($item.Height/100))) }
        for ($i=0; $i -lt $script:papers.Count; $i++) { if ($script:papers[$i].RawKind -eq $config.paper_kind) { $paper.SelectedIndex = $i; break } }
        if ($paper.SelectedIndex -lt 0 -and $paper.Items.Count) { $paper.SelectedIndex = 0 }
        $null = $tray.Items.Add('Printer default')
        $script:trays = @($p.PaperSources)
        foreach ($item in $script:trays) { $null = $tray.Items.Add($item.SourceName) }
        $tray.SelectedIndex = 0
        for ($i=0; $i -lt $script:trays.Count; $i++) { if ($script:trays[$i].RawKind -eq $config.tray) { $tray.SelectedIndex = $i+1 } }
    } catch { $paperInfo.Text = 'Printer information unavailable. Refresh after reconnecting the printer.' }
}
$showMargins = {
    try {
        if ($paper.SelectedIndex -lt 0) { return }
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
    [Drawing.Printing.PrinterSettings]::InstalledPrinters | Sort-Object | ForEach-Object { $null = $printers.Items.Add($_) }
    $printers.SelectedItem = if ($selected) { $selected } else { $config.printer }
}
Refresh-Printers
Button 'Refresh printers' 355 180 280 { Refresh-Printers }
$watch = New-Object Windows.Forms.CheckBox
$watch.Text = 'Automatically print completed PDFs saved in this Inbox'
$watch.Checked = $config.watch_inbox; $watch.SetBounds(15,430,620,30); $printTab.Controls.Add($watch)
$notice = Label 'Start with plain paper. Confirm section order on the Alignment tab.' 15 468 620 40

$script:container = $alignTab
$null = Label 'Match the physical stock, top to bottom' 15 15
$names = @('Check','Stub 1','Stub 2')
$orders = @(@(0,1,2),@(0,2,1),@(1,0,2),@(1,2,0),@(2,0,1),@(2,1,0))
$order = Combo 15 45 320
foreach ($o in $orders) { $null = $order.Items.Add(($o | ForEach-Object { $names[$_] }) -join ' / ') }
for ($i=0; $i -lt 6; $i++) { if (($orders[$i] -join ',') -eq ($config.order -join ',')) { $order.SelectedIndex = $i } }
$picture = @()
for ($i=0; $i -lt 3; $i++) {
    $c = Label '' 370 (20+$i*32) 250 32; $c.BorderStyle='FixedSingle'; $c.TextAlign='MiddleCenter'; $picture += $c
}
$draw = {
    if ($order.SelectedIndex -ge 0) {
        for ($j=0; $j -lt 3; $j++) {
            $index = $orders[$order.SelectedIndex][$j]; $picture[$j].Text = $names[$index]
            $picture[$j].BackColor = @([Drawing.Color]::LightBlue,[Drawing.Color]::Honeydew,[Drawing.Color]::LemonChiffon)[$index]
        }
    }
}
$order.Add_SelectedIndexChanged($draw); & $draw
$null = Label 'Nudges in inches: positive X moves right; positive Y moves down.' 15 145
$null = Label 'Section' 15 180 110; $null = Label 'X (right / left)' 155 180 150; $null = Label 'Y (down / up)' 320 180 150
$xs=@(); $ys=@()
for ($i=0; $i -lt 3; $i++) {
    $null=Label $names[$i] 15 (215+$i*40) 110
    $xs+=Edit $config.offsets[$i][0] 155 (213+$i*40); $ys+=Edit $config.offsets[$i][1] 320 (213+$i*40)
}
$null=Label 'Source split lines from top, inches (both blank = equal thirds)' 15 345
$bound1=Edit '' 15 380; $bound2=Edit '' 155 380
if ($null -ne $config.boundaries) { $bound1.Text=$config.boundaries[0]; $bound2.Text=$config.boundaries[1] }
$null=Label 'Unequal sections retain their height. Nudges clip at section edges.' 15 420
$null=Label 'QuickBooks version (optional)' 15 465 260; $qb=Edit $config.quickbooks_version 290 463 320
$null=Label 'Printer model (optional)' 15 505 260; $model=Edit $config.printer_model 290 503 320
function Save-Settings {
    if ($null -eq $printers.SelectedItem -or $paper.SelectedIndex -lt 0 -or $order.SelectedIndex -lt 0) { throw 'Select your real printer, paper and section order.' }
    if ([string]$printers.SelectedItem -match '^(Voucher Reorder|Microsoft Print to PDF|Microsoft XPS Document Writer)$') { throw 'Choose the real output printer, not the PDF source or Voucher Reorder.' }
    $offsets=@(); for ($i=0; $i -lt 3; $i++) { $offsets+=,@([double]::Parse($xs[$i].Text),[double]::Parse($ys[$i].Text)) }
    $bounds=$null; if ($bound1.Text -or $bound2.Text) { $bounds=@([double]::Parse($bound1.Text),[double]::Parse($bound2.Text)) }
    $latest=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $selectedPaper=$script:papers[$paper.SelectedIndex]
    $trayKind=0; if ($tray.SelectedIndex -gt 0) { $trayKind=$script:trays[$tray.SelectedIndex-1].RawKind }
    $value=@{printer=[string]$printers.SelectedItem; mode=$latest.mode; watch_inbox=$watch.Checked;
        paper_kind=$selectedPaper.RawKind; paper_width=$selectedPaper.Width/100; paper_height=$selectedPaper.Height/100;
        tray=$trayKind; order=$orders[$order.SelectedIndex]; boundaries=$bounds; offsets=$offsets;
        quickbooks_version=$qb.Text; printer_model=$model.Text}
    $temp=Join-Path $store ('settings-'+[guid]::NewGuid().ToString('N')+'.json')
    try {
        $value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temp -Encoding UTF8
        & $python $app validate --config $temp
        if ($LASTEXITCODE -ne 0) { throw 'Check split lines and nudges (between -1 and +1 inch). The split lines must be inside the selected sheet.' }
        [IO.File]::Replace($temp,$configPath,$null); $notice.Text='Settings saved. Use plain paper until alignment is confirmed.'
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp } }
}
Button 'Save settings' 15 555 200 { try { Save-Settings } catch { Show-Error $_.Exception.Message } }
$script:container=$printTab
Button 'Save settings' 15 515 150 { try { Save-Settings } catch { Show-Error $_.Exception.Message } }
Button 'Print alignment test' 180 515 220 {
    try { Save-Settings; $text=(& $python $app alignment | Out-String); if ($LASTEXITCODE -ne 0) { throw 'Could not queue the alignment page.' }; $notice.Text=$text } catch { Show-Error $_.Exception.Message }
}
Button 'Print a PDF...' 415 515 220 {
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
Button 'Job status' 15 560 150 { $text=(& $python $app status | Out-String); $null=[Windows.Forms.MessageBox]::Show($text,'Voucher Reorder') }
Button 'Resume held jobs' 180 560 220 {
    if ([Windows.Forms.MessageBox]::Show('Resume jobs held during an update? They use the printer and alignment settings saved when received. Confirm the correct paper is loaded.','Resume held jobs','YesNo') -eq 'Yes') { & $python $app resume }
}
Button 'Cancel waiting jobs' 415 560 220 {
    if ([Windows.Forms.MessageBox]::Show('Cancel waiting/held app jobs? Jobs already sent must be canceled in the real Windows printer queue. Check paper before reprinting.','Cancel jobs','YesNo') -eq 'Yes') { & $python $app discard }
}
$timer=New-Object Windows.Forms.Timer; $timer.Interval=500
$timer.Add_Tick({ if (Test-Path (Join-Path $store 'maintenance.json')) { $form.Close() } })
if ($SmokeTest) { $form.Dispose(); exit 0 }
$timer.Start()
try { $null=$form.ShowDialog() } finally { $timer.Stop(); $timer.Dispose(); $form.Dispose() }
