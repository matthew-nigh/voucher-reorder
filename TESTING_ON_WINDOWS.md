# Windows acceptance — v0.2.6

Use synthetic documents and plain paper. CI is Windows Server 2022 x64; it does
not qualify every Windows 10/11 driver, QuickBooks release, or interactive UAC path.
Record Windows build, QuickBooks version, printer/driver, paper/tray, account role,
installer SHA256 and BUILD_INFO.json revision. Never publish real checks or names.

## Automated coverage

The workflow runs pytest and ruff, builds Setup.exe/PrinterDeploy.exe/source/SHA256SUMS, and checks:

- Native `ReadDirectoryChangesW` notifications, locked/renamed Inbox arrivals,
  bursts, `watch_inbox` toggles, restart, persisted status, and no idle child spawns.
- A real standard-user install, upgrade from v0.2.0, old-worker shutdown and Run
  entry migration, settings/held-job preservation, repair, downgrade refusal and removal.
- Native ACL/reparse/final-path rejection and restricted-token write denial.
- Real legacy queue migration to **Microsoft Print To PDF**, the protected
  `VoucherReorder:<SID>` port, owner restriction and removal.
- `scripts/test_clone_printer.ps1` prints a text file with the ordinary WinForms
  `PrintDocument` path to **Voucher Reorder**. It supplies neither an output file
  nor `PrintToFile`, and has no UI to answer a Save As dialog. It requires one
  one-page and two offline back-to-back ten-page jobs to reach unique durable jobs,
  verifies two independent protected PDFs before restart, then page counts and
  deletion after success.
  The CI step has a timeout so a hidden Save As dialog fails rather than hangs.
- Six consecutive ten-page output jobs, vector content/page IDs, bounded memory,
  PDF reprint, image/layer/blank rejection, specific errors and scratch cleanup.
- WinForms construction, all 36 order mappings, 100/150/200% simulated DPI, small
  windows, PDF output, and asynchronous optional setup. The Settings title bar,
  taskbar, Start shortcut and installer use the printer icon.

The hosted runner already supports Microsoft's PDF driver and printer creation
in prior output tests. Clone tests are required, not silently skipped. If a future
runner removes that driver or disallows printer creation, record the exact Windows
error in CI and qualify on a Windows 10/11 VM before claiming support. Interactive
Notepad/Edge/QuickBooks and alternate-credential UAC remain manual tests below.
Test-harness sleeps/polls are intentional; the installed broker uses infinite
kernel waits. The active document supervisor still enforces resource deadlines.

## No-admin PDF mode and quiet idle

1. Run `VoucherReorder-0.2.6-Setup.exe` normally as a standard user. Only Setup.exe
   is for installation; source and checksums are for building/verifying.
2. Choose an output folder outside all private job folders, or a real printer.
   Save PDFs to Inbox using existing Microsoft Print to PDF or another exporter.
3. Confirm each complete closed arrival moves to a unique job, processes once,
   and disappears after successful output. Submit the identical PDF twice as two
   separate arrivals; both must print. Existing pre-upgrade receipted files must
   not reprint. Manual Print a PDF must leave the selected original intact.
4. Save slowly, hold open, rename `.tmp` to `.pdf`, and save consecutive jobs.
   No partial document may print. If a producer emits no usable close notification,
   finish saving and click Job status → Retry pickup. Do not wait for a timer.
5. Disable/re-enable Inbox watching and confirm pending files are picked up only
   when enabled. Sign out/in and restart the app; no successful job should replay.
   The checkbox is beside the Inbox controls and reads **Automatically reorder PDFs
   saved to the Inbox**.
6. Select **Save reordered PDF**. Confirm the output folder controls appear. Select
   a physical printer and confirm they disappear. Microsoft Print to PDF, XPS
   writers and Voucher Reorder must not appear as output printers; a saved PDF/XPS
   printer selection must open as Save reordered PDF.
7. In PDF output mode, click **Print alignment test**. Once saved, Explorer must
   open its folder and select the generated PDF. In printer mode, Job status keeps
   the existing queued job behavior.
8. Leave idle for five minutes with Task Manager/Process Explorer. Expect only a
   small `pythonw.exe` broker, no PDF worker, periodic child process, heartbeat
   writes or recurring busy cursor. Status reads must not start a processor.

## Admin clone and Save As qualification

1. **Deploy from trusted administrator staging first.** Obtain
   `VoucherReorder-0.2.6-PrinterDeploy.exe` and its checksum/provenance through an
   independently trusted release channel. In an administrator session create a
   fresh directory under Program Files with owner Administrators and a protected
   DACL granting only Administrators/SYSTEM write access. Copy the package there,
   set its owner to Administrators, and verify its SHA256 *there* against the
   independently obtained digest before running it. Do not elevate a package from
   Downloads, the per-user app, or a user-writable staging folder. A checksum next
   to an untrusted download is not authentication. The package refuses writable,
   reparse, or untrusted-owner staging; no user-side script verifies privileged code.
   It installs embedded helper bytes into `%ProgramFiles%\VoucherReorderPrinter`
   and the monitor into `%SystemRoot%\System32\VoucherReorderPort.dll` as required
   by AddMonitor, with admin/SYSTEM write and Users read/execute ACLs, and verifies
   the deployed bytes. Re-running the same package
   is allowed; a different installed binary fails closed. Updating loaded monitor
   code requires separate administrator maintenance after reconciling queues,
   removing the monitor, and removing the protected old files. No automatic
   spooler restart or privileged self-update is implemented.
2. Enable virtual printer in Setup or Settings. Expect one UAC elevation of the
   installed **PrinterSetup.exe**, not PowerShell. Repeat with alternate-admin
   credentials: the port must use the original desktop SID. Tamper with the
   per-user `request_printer.ps1`/old `printer.ps1` fixture and verify the installed
   helper never reads it. Standard users must be unable to modify the helper,
   monitor, protected spool directories or another user's completed PDFs.
3. Inspect `Get-Printer` and `Get-PrinterPort`: built-in Microsoft Print To PDF,
   `VoucherReorder:<SID>`, monitor **Voucher Reorder Secure Port**, unshared and
   owner-restricted. The default printer and unrelated queues must not change.
   Missing Microsoft Print To PDF must leave usable PDF mode; the administrator
   enables the Windows feature separately.
4. Print from Notepad, Edge and QuickBooks without Save As. Send two ten-page jobs
   back to back, including with the watcher stopped and while signed out. Verify
   distinct UUID PDFs in `%ProgramData%\VoucherReorderSpool\<SID>` and all 20 pages
   after restarting pickup. No pause/resume race is part of job isolation now.
5. In a disposable VM, preplant junctions at the spool root, SID directory, and
   helper directory; each operation must fail without touching an external benign
   sentinel. Repeat a directory-replacement attempt during StartDoc/Write/EndDoc:
   held handles must prevent replacement. Try planting hard links and alternate
   names as the standard user: directory creation/write must be denied. Trace
   effective tokens and final file handles; no SYSTEM write may enter LocalAppData.
   Run `scripts/test_virtual_setup.ps1` for the native automated checks.
6. Kill pickup before/after the copy and acknowledgement; retry must admit each
   UUID once. Test redirected profiles on another volume. Crash the spooler during
   a write: partial files must never be published or printed, and other completed
   jobs must remain intact. Reconcile partial jobs manually; this is not an exactly
   once physical-print guarantee. Unclaimed/partial protected files have no age or
   aggregate storage budget and need administrator review.
7. Decline UAC and test missing helper/policy/driver failures: PDF mode remains
   usable. Remove through Settings: the queue/secure monitor is removed without
   restarting Spooler; an in-use monitor reports failure for admin maintenance.
   Old detached Local Port registry entries and protected files are intentionally
   left for administrator cleanup. No unrelated/shared system port is deleted.

These new native checks are wired into the Windows workflow but have not been
executed in the Linux implementation environment. Do not infer UAC/ACL/driver
qualification from portable tests or cross-compilation alone.

## Failure, retry and upgrade

- Fail parsing or physical printing. Confirm input moves to Needs attention with
  reason.json, Job status lists it, Open folder opens that directory, and Retry
  asks for physical-output reconciliation before requeueing with current settings.
  Restart after 24 hours: failure input must remain. After the configured seven-day
  retention period, the watcher must remove both status and input. Successful retry
  deletes the original failure copy.
- Confirm **Clear finished** prompts and removes sent job entries immediately,
  without deleting saved PDFs. Confirm **Dismiss** prompts and removes the selected
  failed or review entry and its input PDF/PS from Needs attention.
- Crash during pickup or processing: receiving jobs with a moved PDF recover;
  interrupted printing is marked review and never automatically resent.
- Upgrade v0.2.x without elevation: old worker stops, its Run entry and known owned
  scheduled tasks disappear, and old virtual mode falls back to PDF with guidance.
  Enable virtual mode with admin: remove the owned old queue only after reconciling
  outstanding jobs; create the clone. Reject a foreign queue with the same name.
- Uninstall preserves settings and outstanding data. Refused optional printer
  removal must be explicit. Old provisioning installation files are not executed
  by this version. The new native PrinterDeploy package is distributed separately.

## Physical acceptance

Verify both source/output orders, unequal section heights, all paper/tray choices,
100% scale, portrait/simplex, alignment rulers and private overlay on intended
stock. Check first/middle/last pages of ten-page batches. Fail mid-batch and verify
no later pages print or automatically retry. Confirm vector text/fonts, not bitmap
fallback, and qualify MICR with the intended hardware. A successful Windows spool
submission is not proof that paper printed correctly.
