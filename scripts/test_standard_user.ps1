# CI fixture only: the administrator runner creates an unprivileged test account.
param([string]$Installer,[string]$UpgradeInstaller)
$ErrorActionPreference='Stop'
$name='VoucherReorderCI'
$password=ConvertTo-SecureString ('Vr!'+[guid]::NewGuid().ToString('N')+'9a') -AsPlainText -Force
$credential=[Management.Automation.PSCredential]::new("$env:COMPUTERNAME\$name",$password)
$shared=Join-Path $env:PUBLIC ('VoucherReorderCI-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory $shared
try {
    $user=New-LocalUser -Name $name -Password $password
    Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $name
    $null=& icacls.exe $shared /grant "${name}:(OI)(CI)M"
    Copy-Item $Installer (Join-Path $shared 'install.exe')
    Copy-Item $UpgradeInstaller (Join-Path $shared 'upgrade.exe')
    Copy-Item (Join-Path $PSScriptRoot 'test_installer_user.ps1') $shared
    $result=Join-Path $shared 'result.txt'
    $args='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $shared 'test_installer_user.ps1')+'" -Installer "'+(Join-Path $shared 'install.exe')+'" -UpgradeInstaller "'+(Join-Path $shared 'upgrade.exe')+'" -Result "'+$result+'"'
    $p=Start-Process (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -Credential $credential -LoadUserProfile -ArgumentList $args -PassThru
    if (-not $p.WaitForExit(240000)) { Stop-Process -Id $p.Id; throw 'Standard-user test timed out' }
    if (-not (Test-Path $result)) { throw 'Standard-user test did not produce a result' }
    $text=Get-Content $result -Raw; Write-Output $text
    if ($text -notmatch '^PASS:') { throw 'Standard-user acceptance smoke failed' }
} finally {
    Remove-LocalUser -Name $name -ErrorAction SilentlyContinue
    Remove-Item $shared -Recurse -Force -ErrorAction SilentlyContinue
}
