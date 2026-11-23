# Windows acceptance — v0.2.4

Use synthetic documents and plain paper. CI is Windows Server 2022 x64; it does
not qualify every Windows 10/11 driver, QuickBooks release, or interactive UAC path.
Record Windows build, QuickBooks version, printer/driver, paper/tray, account role,
installer SHA256 and BUILD_INFO.json revision. Never publish real checks or names.

## Automated coverage

The workflow runs pytest and ruff, builds Setup.exe/source/SHA256SUMS, and checks:

- Native `ReadDirectoryChangesW` notifications, locked/renamed Inbox arrivals,
  bursts, `watch_inbox` toggles, restart, persisted status, and no idle child spawns.
- A real standard-user install, upgrade from v0.2.0, old-worker shutdown and Run
  entry migration, settings/held-job preservation, repair, downgrade refusal and removal.
- Real legacy queue migration to **Microsoft Print To PDF**, fixed local port
  `%LOCALAPPDATA%\VoucherReorder\Incoming\job.pdf`, owner restriction and removal.
- `scripts/test_clone_printer.ps1` prints a text file with the ordinary WinForms
  `PrintDocument` path to **Voucher Reorder**. It supplies neither an output file
  nor `PrintToFile`, and has no UI to answer a Save As dialog. It requires one
  one-page and two back-to-back ten-page jobs to reach unique durable jobs, verifies
  output page counts and deletion after success, and fails on overlap warnings.
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

1. Run `VoucherReorder-0.2.4-Setup.exe` normally as a standard user. Only Setup.exe
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

1. Enable virtual printer in Setup or Settings. Expect **one UAC elevation of
   Windows PowerShell**, no separate unsigned provisioning executable. Repeat with
   an alternate administrator's credentials: the port must still use the desktop
   user's LocalAppData. The Windows default printer must remain unchanged.
2. Inspect `Get-Printer -Name 'Voucher Reorder'` and `Get-PrinterPort`: built-in
   `Microsoft Print To PDF`, local absolute `Incoming\job.pdf` port, unshared and
   restricted to the owner/admins. Another standard user must not submit to it.
3. Print a short document from **Notepad**, **Edge**, and **QuickBooks Desktop**.
   Select Voucher Reorder in each normal print UI. There must be **no Save As
   dialog**. Verify queue pickup and correct page count/output. Record app versions.
4. Send two ten-page jobs back to back. Verify distinct queue IDs and document
   names where metadata survives, all 20 pages and no overwritten/missing job.
   During pickup later jobs should be paused, then resumed. Repeat under load.
5. Stop the watcher and demonstrate the fixed-port limitation using synthetic
   data only: Windows does not provide an atomic per-job filename for a fixed port.
   Do not claim lossless offline printing. Overlap warnings or inability to hold
   must be visible in Job status. Use Inbox with unique filenames for unqualified
   producers. Fast spoolers can outrun event handling; no general lossless guarantee
   is claimed even if CI's back-to-back test passes.
6. Decline UAC; simulate policy/missing driver; verify explicit blocked/declined
   fallback and usable PDF mode. Remove through Settings: one built-in elevation,
   clone and dedicated unused port removed, shared driver and NUL: untouched.

## Failure, retry and upgrade

- Fail parsing or physical printing. Confirm input moves to Needs attention with
  reason.json, Job status lists it, Open folder opens that directory, and Retry
  asks for physical-output reconciliation before requeueing with current settings.
  Restart and wait past 24 hours: failure input must remain. Successful retry deletes it.
- Confirm **Clear finished** prompts and removes sent job entries immediately,
  without deleting saved PDFs. Confirm **Dismiss** removes only the selected failed
  or review entry while its input stays in Needs attention.
- Crash during pickup or processing: receiving jobs with a moved PDF recover;
  interrupted printing is marked review and never automatically resent.
- Upgrade v0.2.x without elevation: old worker stops, its Run entry and known owned
  scheduled tasks disappear, and old virtual mode falls back to PDF with guidance.
  Enable virtual mode with admin: remove the owned old queue only after reconciling
  outstanding jobs; create the clone. Reject a foreign queue with the same name.
- Uninstall preserves settings and outstanding data. Refused optional printer
  removal must be explicit. Old provisioning installation files are not executed
  by v0.2.4 and are not part of the new download.

## Physical acceptance

Verify both source/output orders, unequal section heights, all paper/tray choices,
100% scale, portrait/simplex, alignment rulers and private overlay on intended
stock. Check first/middle/last pages of ten-page batches. Fail mid-batch and verify
no later pages print or automatically retry. Confirm vector text/fonts, not bitmap
fallback, and qualify MICR with the intended hardware. A successful Windows spool
submission is not proof that paper printed correctly.
