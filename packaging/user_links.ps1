param([ValidateSet('install','remove')][string]$Action, [string]$Candidate)
$ErrorActionPreference = 'Stop'
# v0.2.x shipped the HKCU Run worker. Also retire known older per-user tasks,
# only when their action belongs to this installation and principal is this user.
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$tasks = $service.GetFolder('\')
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$ownedRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Voucher Reorder\'
foreach ($task in @($tasks.GetTasks(1))) {
    if ($task.Name -notin @('VoucherReorder','Voucher Reorder')) { continue }
    $principal = $task.Definition.Principal.UserId
    if ($principal -notin @($identity.Name,$identity.User.Value)) { continue }
    $actions = @($task.Definition.Actions)
    if ($actions.Count -ne 1) { continue }
    $action = $actions[0]
    if ($action.Type -ne 0 -or -not $action.Path.Trim('"').StartsWith($ownedRoot,[StringComparison]::OrdinalIgnoreCase) -or $action.Arguments -notmatch 'app\.py"?\s+worker(?:\s|$)') { continue }
    $tasks.DeleteTask($task.Name,0)
}
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
$link.IconLocation = (Join-Path $Candidate 'packaging\printer.ico') + ',0'
$link.Save()
$guide = $shell.CreateShortcut((Join-Path $folder 'User Guide.lnk'))
$guide.TargetPath = Join-Path $Candidate 'USER_GUIDE.txt'
$guide.Save()
