# Voucher Reorder

Move the three sections of a QuickBooks Desktop voucher check to match your check
stock. Choose source and output section orders, an output printer or PDF folder,
and alignment once; the app sends
reordered pages at **100% actual size**, one-sided.

**Windows 10 and Windows 11 x64.** No subscription, no upload of check data, GPLv3
free software. This is a public release candidate: complete the plain-paper test
on your QuickBooks/printer before putting live check stock in the tray.

## Install and choose a mode

Download `VoucherReorder-0.2.6-Setup.exe` from the PR's **Actions artifact** (or a
future tagged Release). Run it normally. Python and PDF tools are included.
The source archive and SHA256SUMS.txt are only for building from source or verifying
the download; there is no separate Provisioning executable.

| Mode | What you do in QuickBooks | Administrator needed? |
| --- | --- | --- |
| **Virtual printer — optional** | Print to **Voucher Reorder**; the app reorders and forwards automatically. No PDF Save dialog. | Only to create/remove the clone using built-in Windows PowerShell printer tools in one UAC elevation. No unsigned executable runs elevated. |
| **PDF handoff — default** | Print to an **already available** Microsoft Print to PDF, then save in the Inbox shown in the app. Alternatively save/export a PDF elsewhere and click **Print a PDF**. | **No** admin access to install, upgrade, run or remove the per-user app. |

Declining UAC, lacking credentials, a blocked driver, or a failed optional setup
leaves a working PDF-mode app. Settings clearly shows the active mode and has
**Enable virtual printer (UAC)** and **Switch to PDF handoff** buttons. Declining
printer removal still switches to PDF mode; the dormant Windows printer remains
until an administrator removes it. Setup runs in the background with a visible
status/progress indicator; its buttons are disabled until success or failure is
reported. It still uses exactly one UAC prompt. The app never changes your Windows default printer.

PDF mode adds a Save step; it cannot hide Windows' Print to PDF filename dialog.
If that Windows feature or your physical printer driver is missing, enabling or
installing it may require your administrator. An existing PDF exporter/printer
works too. The app never silently enables Windows features or changes security policy.

See the short [user guide](USER_GUIDE.md), exact
[Windows acceptance checklist](TESTING_ON_WINDOWS.md) and [handoff](NEXT_STEPS.md).

## Printers, paper and alignment

All installed printers visible to the current user are listed: USB, network,
Wi-Fi and shared queues use their normal Windows drivers. **Voucher Reorder itself
is never allowed as the output**, to prevent loops. Printer access permissions
and driver installation remain Windows responsibilities; universal hardware
compatibility is not claimed without testing each model.

For a PC with no physical printer, select **Save reordered PDF (test, no physical
printer)** and choose a folder outside the Inbox. Selecting a PDF/XPS writer such
as Microsoft Print to PDF uses the same direct PDF-file output, with no second
Save dialog or driver dependency. Alignment tests, manual PDFs, Inbox jobs and
virtual-printer input all use this output choice. Job status reports the saved
file path. Each job gets a unique filename; files remain until you delete them.
Saved PDFs can be submitted again. Set the input section order to match that PDF
before reordering it again. Output folders must remain outside the Inbox; Inbox arrivals are moved to unique queue files and deleted after successful output.
No PDF data is rasterized. This tests section placement, not physical margins/MICR.

Settings enumerates the selected driver's paper sizes and trays and shows its
reported printable margins. Letter, Legal, A4 and driver-specific sizes can be
selected. Every PDF page must match the selected physical paper dimensions;
mismatches fail **before** forwarding instead of being fitted or scaled. Set the
printer's default orientation to portrait. The print command explicitly requests
one copy, simplex, the selected paper/tray, `noscale` and no automatic rotation.
A driver can still override options or have unprintable margins: verify the ruler
and plain-paper overlay, and use per-section nudges. Nothing can print outside a
printer's physical printable area.

Both **Source page (QuickBooks)** and **Printed output (physical stock)** offer
all six section orders (36 combinations). Source defaults to Check / Stub 1 / Stub 2;
choose what the actual QuickBooks PDF shows. The left/right schematic previews
label all bands and show their source/destination positions. The layout scales
with DPI and scrolls in small windows. Nudges follow Check, Stub 1 and Stub 2 by name.

**Section heights: leave blank if your source page has three equal sections.**
For unequal sections, enter the two dividing-line distances **from the source
page's top**, not each section's individual height. Default Letter thirds are **11/3 inches**, not 3.5. For 3.5/3.5/4-inch
source sections, enter `3.5` and `7`. Sections retain their heights when moved;
nudges clip inside their destination slot. Positive X moves right; positive Y down.
The engine preserves PDF text, fonts, vector graphics and image data without
rasterization or scaling. Downstream renderer/driver/MICR quality needs a real test.

## In-place upgrades and removal

Run the newer installer; do **not** uninstall first. Both modes use the same
per-user identity, install root and data format:

- App: `%LOCALAPPDATA%\Programs\Voucher Reorder`, with isolated version deployments.
- Settings, private queue, Inbox: `%LOCALAPPDATA%\VoucherReorder`.
- Start menu, startup and Apps uninstall entry: current user only (HKCU).

An upgrade stages all new files before stopping the running app. Settings closes;
an in-flight print is allowed to finish, with a bounded wait and no forced kill.
Waiting jobs are **held**, retaining their original printer/layout settings. After
upgrade, inspect Job status and use **Resume held jobs** when the correct paper is
loaded. Interrupted print attempts are marked for review and never auto-retried.

Settings and mode persist. Version 0.2.0 files and queued-job snapshots load with
the original source order. The unused QuickBooks-version/printer-model fields are
ignored when loading and removed on the next settings save. Activation updates the shortcuts/startup entry and
current-version pointer; failures attempt to restore the previous version.
Same-version repair is allowed; lower versions are refused. Silent setup (`/S`)
installs/upgrades the per-user app without requesting UAC; enable the optional
virtual printer later from Settings. Old owned deployments
are removed after activation; files still locked by Windows/security software are
retained safely and cleanup is retried on the next successful install. If setup is
interrupted, rerun it: a maintenance marker deliberately prevents printing until
setup finishes. Downgrades are not a recovery method.

Uninstall from Windows Apps. Removing the optional printer requests UAC; refusing
it does not block removing the per-user app. Cancel jobs in the Windows virtual
queue first. Settings, Inbox originals and held jobs remain for safe reinstall;
remove `%LOCALAPPDATA%\VoucherReorder` yourself only after reconciling both printer
queues and any paper already printed. Shared Microsoft runtimes/drivers remain.

## Architecture and safety

```text
PDF mode:     existing PDF output -> watched Inbox
Virtual mode: app -> Microsoft Print To PDF clone -> Incoming/job.pdf
Both:         native event broker -> unique private job -> bounded PDF processor
Output:       PDF folder, or PDFium vector EMF -> checked GDI pages -> printer
```

The no-window broker waits on `ReadDirectoryChangesW`,
`FindFirstPrinterChangeNotification`, and an active processor's exit handle.
There are no background polling loops, timers, heartbeats, or periodic process
launches. PDF parsing and printing run only for a job; the processor drains the
queue and exits. Job status reads persisted records, not a heartbeat.

Optional setup elevates only Windows' signed `powershell.exe`, once, with a
snapshot of the printer commands. `Add-PrinterPort` and `Add-Printer` create an
owner-restricted, unshared **Voucher Reorder** printer using the built-in
**Microsoft Print To PDF** driver. Its local port is the literal absolute path
`%LOCALAPPDATA%\VoucherReorder\Incoming\job.pdf`, not `FILE:` or `PORTPROMPT:`.
That fixed port supplies the filename, so ordinary application printing needs no
Save As dialog. The user's data path is captured before elevation, including when
a different administrator supplies credentials. No provisioning executable,
signing setup, security-policy change, or runtime download is performed.
`/S /VIRTUAL=1` opts in; plain `/S` needs no administrator access.

The broker opens an arrival denying read/write sharing, checks PDF header and
EOF, then atomically renames it while holding that handle. Timestamp, UUID, and
sanitized document name/job ID (when spooler metadata is available) distinguish
jobs. Structural/vector validation runs in the bounded processor before printing.
Spooler events pause later jobs until pickup and resume only jobs the broker held.
An observed overlap or inability to pause is persisted in Job status. **A fixed
file port cannot guarantee lossless unattended bursts if the watcher is stopped,
the spooler outruns notification handling, or an application bypasses normal
spooling.** Do not print while signed out or the watcher is stopped. On an overlap
warning, reconcile source documents and output before reprinting. Unique Inbox
PDFs remain the reliable fallback for applications that fail this qualification.

Upgrade removes the old HKCU worker autostart and recognized owned scheduled
tasks. Old virtual installations fall back to PDF mode without elevation; enabling
the optional component replaces the owned Imagesetter/NUL or LPR queue, provided
it has no outstanding jobs. Dedicated unused ports are removed; shared `NUL:`
is left alone. Foreign queues are never replaced. A declined/blocked setup is
reported plainly and leaves PDF mode usable. The old Program Files provisioning
package is not executed by the new app; any historical installation files remain.

The expected workload is ten pages or fewer per job, including consecutive jobs.
Printing has a 384 MiB combined process-tree cap; PDF preparation retains its
768 MiB cap, 250-page validation ceiling, and 256 MiB expanded-content limit.
Inspection/conversion have 120-second deadlines;
printing gets 60 seconds for startup plus 30 seconds per page (six minutes for ten
pages), with a separate 30-second printer-probe allowance.
The pinned, hash-verified PDFium DLL uses its vector EMF/GDI print mode. Text and
paths remain vectors at the Windows driver boundary, at actual size with no fit,
shrink or auto-rotation. Windows drivers control their own final device encoding;
arbitrary drivers do not accept raw PDF bytes. There is no application raster path.
All pages are preflighted before starting the job, with a 64 MiB per-page EMF limit.
Bitmap drawing/fallback (including scanned/image PDFs) and blank vector pages are
rejected rather than silently rasterized; use a vector PDF export. Flatten optional
content in the source application without converting text to images. Recheck physical
alignment and MICR with the intended printer/stock after upgrading.

CI prints six consecutive ten-page jobs to Microsoft's PDF file port, checks every page
for nonblank vector output, absence of image XObjects and sequential vector page IDs.
It drains six queued jobs through the same worker, checking payload cleanup,
zero waiting/spool backlog, and flat worker memory. It requires the print tree's
measured peak commit to stay below 256 MiB per job, with less than 32 MiB variation
across six jobs, and worker private memory variation below 16 MiB after garbage
collection. Compiler scratch files live in private per-job directories, are removed
on exit, and are retried by terminal-job recovery if locked. Printer failures use distinct codes
(configuration 6, vector/spool 7, timeout 8, unexpected termination 9) and an 8 KiB sanitized local
`%LOCALAPPDATA%\VoucherReorder\print-error.log`; no document output is retained.

Inbox pickup is event-driven and controlled by `settings.watch_inbox`. Incomplete
or locked files stay in the watched folder until another change notification;
**Retry pickup** explicitly wakes the broker if an application closes without a
usable final notification. A partial file never launches the PDF processor.
Legacy Inbox receipts are honored so an upgrade does not reprint old originals.
New arrivals are moved, not copied; each arrival is a distinct job, even with
identical content. Manual submissions retain the legacy content deduplication.

Queue limits are 100 MiB/job, 100 waiting jobs, and 512 MiB of waiting inputs.
Successful input/output scratch files are deleted. Failed or uncertain jobs move
the input to `%LOCALAPPDATA%\VoucherReorder\Needs attention\<unique job>` with
`reason.json`. Job status lists them and offers **Open folder** and **Retry** using
current settings. Failed and review jobs expire after seven days at processor startup
(set `VOUCHER_REORDER_FAILURE_RETENTION_DAYS` to 1–365 to change this). **Dismiss**
confirms deletion of the status and private payload. Verify physical output before
retrying an uncertain print, since retry can duplicate it. Waiting/held jobs and
successful status records retain the existing 24-hour expiry. The signed-in watcher
checks retention at startup and at least daily; cleanup runs again at processor startup.

“Sent” means handed to Windows, not proof of physical printing. No exactly-once
guarantee is possible across spooler/device/power failures. Deletion is not secure
erasure; Windows spooling and backups are separate. Filenames and spool document
titles can contain private information: keep job folders and diagnostics local.
Never upload real checks or spool files to this public repository.

## Build and test

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
# Linux integration/build dependencies: ghostscript, nsis, p7zip-full
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
python3 scripts/build_windows.py
```

Outputs are in `dist/`: the installer, matching `-sources.zip`, and `SHA256SUMS.txt`.
The script packages official x64 Windows binaries from SHA-256-pinned downloads in
`packaging/dependencies.json`; it does not claim to cross-compile those upstream
programs. `--stage-only` prepares files; `--version 0.2.6` overrides the packaging
version for upgrade tests (no tag/release is created). Installations need no network
in PDF mode. Virtual setup uses the already available Windows PDF driver; policy or missing-driver failures fall back to PDF mode.

[CI](.github/workflows/build.yml) runs Linux tests; builds on `windows-2022`;
checks all 36 source/output mappings, simulated 100/150/200% UI scaling and small
windows, PDF output, responsive setup, PowerShell/UI construction, the packaged runtime and optional-printer logic;
and installs, upgrades, refuses a downgrade, repairs and uninstalls in an actual
standard-user Windows account, upgrading from the actual v0.2.0 source baseline. Artifacts include matching sources. Future `v*` tag
pushes attach the same files to a Release. Hardware/QuickBooks testing is separate.
Win10/11 **x64** are the supported targets; ARM64/x64-emulation is not yet qualified
and no native ARM64 installer is supplied.

## License and technical references

GPL-3.0-or-later, without warranty; the first branch commit replaced the original
MIT license with the [full official GPLv3 text](LICENSE). Third-party components
retain their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Always provide
the matching source archive alongside the installer.

Sources: [Microsoft driver installation permissions](https://learn.microsoft.com/en-us/windows-hardware/drivers/print/point-and-print-with-packages),
[Windows printer change notifications](https://learn.microsoft.com/en-us/windows/win32/printdocs/findfirstprinterchangenotification),
[PDFium printing API](https://pdfium.googlesource.com/pdfium/+/refs/heads/chromium/8149/public/fpdfview.h),
[Ghostscript vector output](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html).
