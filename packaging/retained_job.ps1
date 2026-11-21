$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$p = Get-Printer -Name 'Voucher Reorder' -Full
if ($p.Comment -ne "VoucherReorder owner=$sid" -or $p.Shared -or
    $p.PortName -ne 'NUL:' -or -not $p.KeepPrintedJobs -or $p.DriverName -ne 'MS Publisher Imagesetter') {
    throw 'Enable the owner-restricted retained printer in Settings.'
}
$job = Get-PrintJob -PrinterName $p.Name | Where-Object {
    ($_.JobStatus -band 0x21080) -and -not ($_.JobStatus -band 0x18)
} | Sort-Object SubmittedTime | Select-Object -First 1
if ($null -eq $job) { 'null' } else { [int]$job.ID }
