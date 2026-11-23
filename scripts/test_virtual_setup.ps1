# Native trust-boundary acceptance. Run elevated in a disposable Windows VM.
$ErrorActionPreference='Stop'
$test=Join-Path $PSScriptRoot '..\build\printer\PrinterSecurityTest.exe'
& $test
if ($LASTEXITCODE) { throw 'Native ACL/token tests failed' }
$root=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'VoucherReorderSecurityFixture'
$target=Join-Path $root 'target'
$junction=Join-Path $root 'redirect'
try {
    New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
    $acl=New-Object Security.AccessControl.DirectorySecurity
    $admins=New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $acl.SetOwner($admins)
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($sid in @('S-1-5-18','S-1-5-32-544')) {
        $identity=New-Object Security.Principal.SecurityIdentifier($sid)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
    }
    Set-Acl -LiteralPath $root -AclObject $acl
    New-Item -ItemType Directory -Path $target | Out-Null
    Set-Content -LiteralPath (Join-Path $target 'sentinel') -Value 'FAKE unchanged'
    New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
    & $test --reject $junction
    if ($LASTEXITCODE) { throw 'Junction leaf was accepted' }
    & $test --reject (Join-Path $junction 'child')
    if ($LASTEXITCODE) { throw 'Junction ancestor was accepted' }
    if ((Get-Content (Join-Path $target 'sentinel')) -ne 'FAKE unchanged') { throw 'Redirect target was touched' }
    # The executable refuses operation outside its protected installed location.
    & (Join-Path $PSScriptRoot '..\build\printer\PrinterSetup.exe') install 'S-1-5-21-1-2-3-1001'
    if (-not $LASTEXITCODE) { throw 'Uninstalled helper accepted setup' }
} finally {
    if (Test-Path -LiteralPath $junction) { [IO.Directory]::Delete($junction) }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
Write-Output 'PASS: native ACL/token checks, junction leaf/ancestor refusal, sentinel preservation, helper location'
exit 0
