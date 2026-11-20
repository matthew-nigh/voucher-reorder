# SPDX-License-Identifier: GPL-3.0-or-later
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
$form.Text = 'Voucher Reorder Settings'
$form.ClientSize = New-Object Drawing.Size(640, 700)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object Drawing.Font('Segoe UI', 10)
function Label($text, $x, $y, $w = 580, $h = 25) {
    $c = New-Object Windows.Forms.Label
    $c.Text = $text; $c.SetBounds($x, $y, $w, $h)
    $form.Controls.Add($c)
    return $c
}
function Edit($text, $x, $y, $w = 100) {
    $c = New-Object Windows.Forms.TextBox
    $c.Text = [string]$text; $c.SetBounds($x, $y, $w, 27)
    $form.Controls.Add($c)
    return $c
}
function Button($text, $x, $y, $w, $action) {
    $c = New-Object Windows.Forms.Button
    $c.Text = $text; $c.SetBounds($x, $y, $w, 32)
    $c.Add_Click($action); $form.Controls.Add($c)
}
$null = Label '1. Choose the real printer that holds your check paper' 20 15
$printers = New-Object Windows.Forms.ComboBox
$printers.SetBounds(20, 45, 600, 28); $printers.DropDownStyle = 'DropDownList'
# Exclude known file writers and any queue on our own port to prevent loops.
Get-Printer | Where-Object {
    $_.Name -ne 'Voucher Reorder' -and $_.PortName -ne 'VoucherReorder_LPR' -and
    $_.Name -notmatch 'Microsoft Print to PDF|Microsoft XPS|OneNote|Fax' -and $_.PortName -ne 'FILE:'
} | Sort-Object Name | ForEach-Object { $null = $printers.Items.Add($_.Name) }
$printers.SelectedItem = $config.printer
$form.Controls.Add($printers)
$null = Label '2. Match the order on your stock (top to bottom)' 20 85
$names = @('Check', 'Stub 1', 'Stub 2')
$orders = @(@(0,1,2), @(0,2,1), @(1,0,2), @(1,2,0), @(2,0,1), @(2,1,0))
$order = New-Object Windows.Forms.ComboBox
$order.SetBounds(20, 115, 320, 28); $order.DropDownStyle = 'DropDownList'
foreach ($o in $orders) { $null = $order.Items.Add(($o | ForEach-Object { $names[$_] }) -join ' / ') }
for ($i=0; $i -lt 6; $i++) { if (($orders[$i] -join ',') -eq ($config.order -join ',')) { $order.SelectedIndex = $i } }
$form.Controls.Add($order)
$picture = @()
for ($i=0; $i -lt 3; $i++) {
    $c = Label '' 390 (112 + $i * 28) 220 28
    $c.BorderStyle = 'FixedSingle'; $c.TextAlign = 'MiddleCenter'
    $picture += $c
}
$draw = {
    if ($order.SelectedIndex -ge 0) {
        for ($j=0; $j -lt 3; $j++) {
            $index = $orders[$order.SelectedIndex][$j]
            $picture[$j].Text = $names[$index]
            $picture[$j].BackColor = @([Drawing.Color]::LightBlue, [Drawing.Color]::Honeydew, [Drawing.Color]::LemonChiffon)[$index]
        }
    }
}
$order.Add_SelectedIndexChanged($draw); & $draw
$null = Label '3. Alignment nudges in inches' 20 160 360
$null = Label 'Positive X moves right. Positive Y moves down.' 20 195
$null = Label 'Section' 20 228 110
$null = Label 'X (right / left)' 155 228 150
$null = Label 'Y (down / up)' 320 228 150
$xs = @(); $ys = @()
for ($i=0; $i -lt 3; $i++) {
    $null = Label $names[$i] 20 (260 + $i * 34) 110
    $xs += Edit $config.offsets[$i][0] 155 (258 + $i * 34)
    $ys += Edit $config.offsets[$i][1] 320 (258 + $i * 34)
}
$null = Label 'Source split lines, inches from top (leave both blank for equal thirds):' 20 365
$bound1 = Edit '' 20 395
$bound2 = Edit '' 155 395
if ($null -ne $config.boundaries) { $bound1.Text = $config.boundaries[0]; $bound2.Text = $config.boundaries[1] }
$null = Label 'For unequal sections, each section keeps its height when moved.' 20 430
$null = Label 'Optional: QuickBooks version' 20 460 260
$qb = Edit $config.quickbooks_version 290 458 320
$null = Label 'Optional: printer model' 20 495 260
$model = Edit $config.printer_model 290 493 320
$notice = Label 'Use plain paper until the alignment is confirmed. Letter, actual size, one-sided.' 20 535 600 45
function Save-Settings {
    if ($null -eq $printers.SelectedItem -or $order.SelectedIndex -lt 0) { throw 'Choose a real printer and section order.' }
    $offsets = @()
    for ($i=0; $i -lt 3; $i++) { $offsets += ,@([double]::Parse($xs[$i].Text), [double]::Parse($ys[$i].Text)) }
    $bounds = $null
    if ($bound1.Text -or $bound2.Text) { $bounds = @([double]::Parse($bound1.Text), [double]::Parse($bound2.Text)) }
    $value = @{printer=[string]$printers.SelectedItem; order=$orders[$order.SelectedIndex];
        boundaries=$bounds; offsets=$offsets; quickbooks_version=$qb.Text; printer_model=$model.Text}
    $temp = Join-Path $store ('settings-' + [guid]::NewGuid().ToString('N') + '.json')
    try {
        $value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temp -Encoding UTF8
        & $python $app validate --config $temp
        if ($LASTEXITCODE -ne 0) { throw 'Check the split lines and nudges. Nudges must be between -1 and +1 inch; split lines between 0 and 11.' }
        # Replace is atomic and preserves the existing file ACL.
        [IO.File]::Replace($temp, $configPath, $null)
        $notice.Text = 'Settings saved. Print an alignment page on plain paper.'
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp } }
}
function Show-Error($e) { $null = [Windows.Forms.MessageBox]::Show([string]$e, 'Voucher Reorder', 'OK', 'Warning') }
Button 'Save settings' 20 585 150 {
    try { Save-Settings } catch { Show-Error $_.Exception.Message }
}
Button 'Print alignment test page' 185 585 250 {
    try {
        Save-Settings
        $form.UseWaitCursor = $true
        & $python $app alignment
        if ($LASTEXITCODE -ne 0) { throw 'Printing did not complete. Check the real printer queue and plain paper before trying again.' }
        $notice.Text = 'Alignment page sent. Measure the ruler and check the section positions.'
    } catch { Show-Error $_.Exception.Message } finally { $form.UseWaitCursor = $false }
}
Button 'Job status' 450 585 160 {
    $text = (& $python $app status | Out-String)
    $null = [Windows.Forms.MessageBox]::Show($text, 'Voucher Reorder job status')
}
Button 'Cancel waiting jobs' 20 635 220 {
    $answer = [Windows.Forms.MessageBox]::Show('Cancel jobs waiting in this app? Jobs already sent to the real printer must also be canceled in Windows. Check the paper before reprinting.', 'Cancel waiting jobs', 'YesNo', 'Warning')
    if ($answer -eq 'Yes') {
        $form.UseWaitCursor = $true
        & $python $app discard
        $form.UseWaitCursor = $false
        if ($LASTEXITCODE -ne 0) { Show-Error 'Could not cancel safely. Check Windows printer queues.' }
    }
}
Button 'Close' 450 635 160 { $form.Close() }
$null = $form.ShowDialog()
