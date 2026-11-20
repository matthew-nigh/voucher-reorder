param([ValidateSet('install','remove')][string]$Action, [string]$Candidate)
$ErrorActionPreference = 'Stop'
$folder = Join-Path ([Environment]::GetFolderPath('Programs')) 'Voucher Reorder'
if ($Action -eq 'remove') {
    if (Test-Path -LiteralPath $folder) { Remove-Item -LiteralPath $folder -Recurse -Force }
    exit
}
$null = New-Item -ItemType Directory -Path $folder -Force
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $folder 'Voucher Reorder.lnk'))
$link.TargetPath = Join-Path $Candidate 'runtime\pythonw.exe'
$link.Arguments = '"' + (Join-Path $Candidate 'app.py') + '" settings'
$link.WorkingDirectory = $Candidate
$link.Save()
$guide = $shell.CreateShortcut((Join-Path $folder 'User Guide.lnk'))
$guide.TargetPath = Join-Path $Candidate 'USER_GUIDE.txt'
$guide.Save()
