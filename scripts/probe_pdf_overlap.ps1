# CI diagnostic only: hypothetical v4 Microsoft Print to PDF + standard Local Port.
# Uses the VOID FAKE labeled-page fixture from test_clone_printer.ps1. No installed
# printer path uses this port. Hosted CI runners are likely faster than typical PCs.
param(
    [switch]$ChildPrint,
    [string]$PrinterName,
    [int]$Pages,
    [string]$Title,
    [string]$Marker
)
$ErrorActionPreference = 'Stop'
if ($ChildPrint) {
    Add-Type -AssemblyName System.Drawing
    $document = [Drawing.Printing.PrintDocument]::new()
    $document.PrinterSettings.PrinterName = $PrinterName
    $document.PrintController = [Drawing.Printing.StandardPrintController]::new()
    $document.DocumentName = $Title
    $script:page = 0
    $script:pageCount = $Pages
    $script:sourceText = "VOID FAKE $Title"
    $document.add_PrintPage({
        param($sender, $event)
        $script:page++
        $font = [Drawing.Font]::new('Arial', 12)
        try { $event.Graphics.DrawString("$script:sourceText PAGE $script:page", $font, [Drawing.Brushes]::Black, 72, 72) }
        finally { $font.Dispose() }
        $event.HasMorePages = $script:page -lt $script:pageCount
    })
    try {
        [IO.File]::WriteAllText("$Marker.tmp", [Diagnostics.Stopwatch]::GetTimestamp().ToString())
        [IO.File]::Move("$Marker.tmp", $Marker)
        $document.Print()
    } finally { $document.Dispose() }
    exit 0
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('VoucherPdfOverlap-' + [guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($root)
$fixed = Join-Path $root 'fixed.pdf'
$printer = 'Voucher PDF overlap ' + [guid]::NewGuid().ToString('N')
$portCreated = $false
$printerCreated = $false
$frequency = [Diagnostics.Stopwatch]::Frequency
$runs = [Collections.Generic.List[object]]::new()
$processes = [Collections.Generic.List[object]]::new()

function Start-ProbeJob($runId, $label, $count) {
    $marker = Join-Path $root "$runId-$label.tick"
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -ChildPrint -PrinterName "' + $printer + '" -Pages ' + $count + ' -Title "' + $label + '" -Marker "' + $marker + '"'
    $process = Start-Process (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $processes.Add($process)
    return [pscustomobject]@{ Process = $process; Marker = $marker; Label = $label }
}

function Collect-Run($runId, $jobs, $gap = $null) {
    $jobs = @($jobs)
    $saved = [Collections.Generic.List[object]]::new()
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    $quietSince = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($null -ne $gap -and $jobs.Count -eq 1 -and [IO.File]::Exists($jobs[0].Marker)) {
            $firstTick = [long][IO.File]::ReadAllText($jobs[0].Marker)
            if ([Diagnostics.Stopwatch]::GetTimestamp() -ge $firstTick + $gap * $frequency) {
                $jobs += Start-ProbeJob $runId 'GAP-B' 3
            }
        }
        if ([IO.File]::Exists($fixed)) {
            try {
                # FileShare.None is the earliest observation that the writer closed it.
                $handle = [IO.File]::Open($fixed, 'Open', 'Read', 'None')
                $closedTick = [Diagnostics.Stopwatch]::GetTimestamp()
                $handle.Dispose()
                $destination = Join-Path $root "$runId-$($saved.Count).pdf"
                [IO.File]::Move($fixed, $destination)
                $saved.Add([pscustomobject]@{ Name = [IO.Path]::GetFileName($destination); Tick = $closedTick })
                $quietSince = $null
            } catch [IO.IOException] {
                # The spooler still holds the file, or changed it during the check.
            }
        }
        $done = $true
        if ($null -ne $gap -and $jobs.Count -eq 1) { $done = $false }
        foreach ($job in $jobs) { if (-not $job.Process.HasExited) { $done = $false } }
        $queued = @()
        if ($done -and -not [IO.File]::Exists($fixed)) {
            $queued = @(Get-PrintJob -PrinterName $printer -ErrorAction SilentlyContinue)
        }
        if ($done -and -not [IO.File]::Exists($fixed) -and $queued.Count -eq 0) {
            if ($null -eq $quietSince) { $quietSince = [DateTime]::UtcNow }
            if (([DateTime]::UtcNow - $quietSince).TotalSeconds -ge 5) { break }
        } else { $quietSince = $null }
        Start-Sleep -Milliseconds 10
    }
    if ([DateTime]::UtcNow -ge $deadline) { throw "Run $runId timed out" }
    foreach ($job in $jobs) {
        if ($job.Process.ExitCode) { throw "Print child $($job.Label) exited $($job.Process.ExitCode)" }
        if (-not [IO.File]::Exists($job.Marker)) { throw "Print child $($job.Label) never reached Print()" }
    }
    $runs.Add([pscustomobject]@{ Id = $runId; Jobs = $jobs; Saved = $saved.ToArray(); Gap = $gap })
}

try {
    $driver = Get-PrinterDriver -Name 'Microsoft Print To PDF' -ErrorAction Stop
    Add-PrinterPort -Name $fixed
    $portCreated = $true
    Add-Printer -Name $printer -PortName $fixed -DriverName $driver.Name
    $printerCreated = $true

    foreach ($count in @(1, 3, 10)) {
        for ($trial = 1; $trial -le 3; $trial++) {
            $id = "time-$count-$trial"
            Collect-Run $id @(Start-ProbeJob $id "TIMING-$count-$trial" $count)
        }
    }
    # Serial reference outputs let rendered pixels identify each job in a pair.
    foreach ($label in @('A', 'B')) {
        $id = "reference-$label"
        Collect-Run $id @(Start-ProbeJob $id "GAP-$label" 3)
    }
    foreach ($gap in @(0, 0.5, 1, 2, 5)) {
        for ($trial = 1; $trial -le 3; $trial++) {
            $id = "gap-$gap-$trial"
            $first = Start-ProbeJob $id 'GAP-A' 3
            Collect-Run $id @($first) $gap
        }
    }

    $verify = Join-Path $PSScriptRoot 'verify_pdf_overlap.py'
    $pdfs = & python $verify $root | ConvertFrom-Json
    if ($LASTEXITCODE) { throw 'PDF verification failed' }
    $byName = @{}
    foreach ($pdf in $pdfs) { $byName[$pdf.name] = $pdf }
    foreach ($count in @(1, 3, 10)) {
        $samples = @()
        foreach ($run in @($runs | Where-Object { $_.Id -like "time-$count-*" })) {
            if ($run.Saved.Count -ne 1) { throw "$($run.Id) produced $($run.Saved.Count) files" }
            $pdf = $byName[$run.Saved[0].Name]
            if (-not $pdf.valid -or $pdf.pages -ne $count) { throw "$($run.Id) produced incomplete PDF" }
            $submitted = [long][IO.File]::ReadAllText($run.Jobs[0].Marker)
            $samples += [math]::Round(1000 * ($run.Saved[0].Tick - $submitted) / $frequency, 1)
        }
        $ordered = @($samples | Sort-Object)
        Write-Output "PDF OVERLAP TIMING: pages=$count trials=3 submit-to-closed-ms min=$($ordered[0]) median=$($ordered[1]) max=$($ordered[2])"
    }
    $references = @{}
    foreach ($label in @('A', 'B')) {
        $run = @($runs | Where-Object Id -eq "reference-$label")[0]
        if ($run.Saved.Count -ne 1) { throw "Reference $label produced $($run.Saved.Count) files" }
        $pdf = $byName[$run.Saved[0].Name]
        if (-not $pdf.valid -or $pdf.pages -ne 3) { throw "Reference $label incomplete" }
        $references[$label] = $pdf.fingerprint
    }
    $gapSuccess = @{}
    foreach ($gap in @(0, 0.5, 1, 2, 5)) {
        $successes = 0
        foreach ($run in @($runs | Where-Object { $_.Id -like "gap-$gap-*" })) {
            $seen = @()
            foreach ($saved in $run.Saved) {
                $pdf = $byName[$saved.Name]
                if ($pdf.valid -and $pdf.pages -eq 3) {
                    foreach ($label in @('A', 'B')) {
                        if ($pdf.fingerprint -eq $references[$label]) { $seen += $label }
                    }
                }
            }
            $firstTick = [long][IO.File]::ReadAllText($run.Jobs[0].Marker)
            $secondTick = [long][IO.File]::ReadAllText($run.Jobs[1].Marker)
            $actual = [math]::Round(($secondTick - $firstTick) / $frequency, 3)
            $preserved = (@($seen | Sort-Object -Unique) -join ',')
            $both = @($seen | Sort-Object -Unique).Count -eq 2
            if ($both) { $successes++ }
            Write-Output "PDF OVERLAP GAP: requested-s=$gap actual-submit-s=$actual trial=$($run.Id) files=$($run.Saved.Count) preserved=$preserved both=$both"
        }
        $gapSuccess[$gap] = $successes
        Write-Output "PDF OVERLAP GAP: requested-s=$gap preserved-both=$successes/3"
    }
    $threshold = 'none of the tested gaps'
    foreach ($gap in @(0, 0.5, 1, 2, 5)) {
        if ($gapSuccess[$gap] -eq 3) { $threshold = "$gap seconds"; break }
    }
    Write-Output "PDF OVERLAP GAP: first-all-preserved=$threshold (three trials per gap; larger gaps may vary)"
} catch {
    Write-Warning "PDF OVERLAP INCONCLUSIVE: $($_.Exception.Message)"
} finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    if ($printerCreated) { Remove-Printer -Name $printer -ErrorAction SilentlyContinue }
    if ($portCreated) { Remove-PrinterPort -Name $fixed -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
