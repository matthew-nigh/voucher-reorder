# Voucher Reorder

Move the three sections of a QuickBooks Desktop voucher check to match your check
stock. Choose your real printer, section order and alignment once; the app sends
reordered pages at **100% actual size**, one-sided.

**Windows 10 and Windows 11 x64.** No subscription, no upload of check data, GPLv3
free software. This is a public release candidate: complete the plain-paper test
on your QuickBooks/printer before putting live check stock in the tray.

## Install and choose a mode

Download `VoucherReorder-0.2.0-Setup.exe` from the PR's **Actions artifact** (or a
future tagged Release). Run it normally. Python and PDF tools are included.

| Mode | What you do in QuickBooks | Administrator needed? |
| --- | --- | --- |
| **Virtual printer — optional** | Print to **Voucher Reorder**; the app reorders and forwards automatically. No PDF Save dialog. | Only to install/remove the optional Windows printer and its prerequisite. An administrator first installs the separate provisioning package; Settings requests UAC and a different administrator can provide credentials for the signed-in user. |
| **PDF handoff — default** | Print to an **already available** Microsoft Print to PDF, then save in the Inbox shown in the app. Alternatively save/export a PDF elsewhere and click **Print a PDF**. | **No** admin access to install, upgrade, run or remove the per-user app. |

Declining UAC, lacking credentials, a blocked driver, or a failed optional setup
leaves a working PDF-mode app. Settings clearly shows the active mode and has
**Enable virtual printer (UAC)** and **Switch to PDF handoff** buttons. Declining
printer removal still switches to PDF mode; the dormant Windows printer remains
until an administrator removes it. The app never changes your Windows default printer.

PDF mode adds a Save step; it cannot hide Windows' Print to PDF filename dialog.
If that Windows feature or your physical printer driver is missing, enabling or
installing it may require your administrator. An existing PDF exporter/printer
works too. The app never silently enables Windows features or changes security policy.

See the short [user guide](USER_GUIDE.md), exact
[Windows acceptance checklist](TESTING_ON_WINDOWS.md) and [handoff](NEXT_STEPS.md).

## Printers, paper and alignment

All installed printers visible to the current user are listed: USB, network,
Wi-Fi and shared queues use their normal Windows drivers. Choose a real output
printer, not Voucher Reorder or the source PDF printer. Printer access permissions
and driver installation remain Windows responsibilities; universal hardware
compatibility is not claimed without testing each model.

Settings enumerates the selected driver's paper sizes and trays and shows its
reported printable margins. Letter, Legal, A4 and driver-specific sizes can be
selected. Every PDF page must match the selected physical paper dimensions;
mismatches fail **before** forwarding instead of being fitted or scaled. Set the
printer's default orientation to portrait. The print command explicitly requests
one copy, simplex, the selected paper/tray, `noscale` and no automatic rotation.
A driver can still override options or have unprintable margins: verify the ruler
and plain-paper overlay, and use per-section nudges. Nothing can print outside a
printer's physical printable area.

All six section orders are supported. Split lines are inches **from the source
page's top**. Default Letter thirds are **11/3 inches**, not 3.5. For 3.5/3.5/4-inch
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

Settings and mode persist. Activation updates the shortcuts/startup entry and
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

**Earlier 0.1 administrator-only prototype:** its Program Files installation and
machine printer cannot be deleted by a no-admin installer. Existing profile settings
are reused, but do not run the old and new apps together. An administrator must
remove that old machine installation. Back up the profile folder first: the old
0.1 uninstaller deletes it. Restore that backup before launching the new app and
reconcile/hold old pending jobs. Public per-user releases starting with 0.2 support
in-place upgrades in either mode; this pre-public migration needs supervised cleanup.

## Architecture and safety

```text
PDF mode:     existing PDF output -> dedicated Inbox / Print a PDF
Virtual mode: QuickBooks -> inbox Microsoft PostScript driver -> owner-restricted Windows spool queue -> Ghostscript PDF
Both:         private per-user queue -> vector pypdf reorder -> PDFium vector EMF -> checked GDI pages -> real printer
```

Python's official embeddable runtime and pure-Python pypdf make the core testable
on Linux. The native UI uses Windows PowerShell/WinForms. The per-user installer
starts in PDF mode with no administrator access. Select **Virtual printer (one
administrator prompt)** in setup, or **Enable virtual printer** in Settings, to
install the embedded, matching provisioning package and configure the queue in
one UAC elevation. No separate download is needed. Silent setup defaults to PDF;
`/S /VIRTUAL=1` explicitly enables the optional component. Declining UAC leaves PDF
mode usable. The elevated package runs only its native launcher and scripts in
protected Program Files; the per-user app stays unelevated. Use trusted installers
and verify the published checksums: these builds are unsigned.

The protected helper configures one unshared Windows printer using Microsoft
MS Publisher Imagesetter, the local NUL: port, and retained RAW jobs. The signed-in
owner consumes jobs through spooler RPC. Offline jobs stay in that restricted queue.
Reconcile paper and both queues before resubmitting any job in review. The package
has its own **Voucher Reorder Printer Provisioning** entry in Windows Apps; uninstall
it as administrator after reconciling/canceling queued jobs. Shared runtimes and OS
drivers remain installed. Per-user updates/uninstall never block on a legacy LPR
queue; no port-515 migration is supplied because that queue was never deployed.

Provisioning metadata, executable hash and app version are checked before elevation.
An app upgrade with an older provisioning package falls back to PDF mode and explains
how to enable the updated optional component. App installation itself needs no UAC.

Processing allows 250 pages, 768 MiB of combined print-child/process-tree memory,
and 256 MiB of expanded PDF content. Inspection/conversion have 120-second deadlines;
printing gets 120 seconds times (page count + 1), plus supervisor startup allowance.
The pinned, hash-verified PDFium DLL uses its vector EMF/GDI print mode. Text and
paths remain vectors at the Windows driver boundary, at actual size with no fit,
shrink or auto-rotation. Windows drivers control their own final device encoding;
arbitrary drivers do not accept raw PDF bytes. There is no application raster path.
All pages are preflighted before starting the job, with a 64 MiB per-page EMF limit.
Bitmap drawing/fallback (including scanned/image PDFs) and blank vector pages are
rejected rather than silently rasterized; use a vector PDF export. Flatten optional
content in the source application without converting text to images. Recheck physical
alignment and MICR with the intended printer/stock after upgrading.

CI prints a 52-page synthetic batch to Microsoft's PDF file port, checks every page
for nonblank output and absence of image XObjects, and requires the worker tree's
measured peak commit to stay below 600 MiB. Printer failures use distinct codes
(configuration 6, vector/spool 7, timeout 8) and an 8 KiB sanitized local
`%LOCALAPPDATA%\VoucherReorder\print-error.log`; no document output is retained.

PDF Inbox ingestion waits for stable size/time, a complete parseable PDF and an
exclusive Windows read handle. Source PDFs are **not deleted or moved**. Persistent
receipts prevent old Inbox files from printing again after restart/queue expiry.
Use new filenames for new jobs; leave unrelated files outside this dedicated folder.
Copies in the private queue are capped at 100 MiB/job and 100 waiting jobs, with a 512 MiB aggregate input limit. They are
removed after sending, failure or review; waiting copies/status expire after 24
hours while the app runs or at next start. Inbox originals remain until you delete
them. Deletion is not secure erasure; Windows spooling and backups are separate.

Duplicate identical job payloads within 24 hours are suppressed, including deliberate
identical reprints. Use a fresh QuickBooks output after reconciling paper and queues.
A “sent” status means handed to Windows, not proof of physical printing. There is
no exactly-once guarantee across spooler/device/power failures. Settings provides
job status, cancellation and release of **unattempted held** jobs only. Raw financial
contents and parser errors are not logged. Never upload real checks or spool files
to this public repository.

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
programs. `--stage-only` prepares files; `--version 0.2.1` overrides the packaging
version for upgrade tests (no tag/release is created). Installations need no network
in PDF mode. Virtual setup may download Microsoft's signature-checked C++ runtime.

[CI](.github/workflows/build.yml) runs Linux tests; builds on `windows-latest`;
checks PowerShell/UI construction, the packaged runtime and optional-printer logic;
and installs, upgrades, refuses a downgrade, repairs and uninstalls in an actual
standard-user Windows account. Artifacts include matching sources. Future `v*` tag
pushes attach the same files to a Release. Hardware/QuickBooks testing is separate.
Win10/11 **x64** are the supported targets; ARM64/x64-emulation is not yet qualified
and no native ARM64 installer is supplied.

## License and technical references

GPL-3.0-or-later, without warranty; the first branch commit replaced the original
MIT license with the [full official GPLv3 text](LICENSE). Third-party components
retain their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Always provide
the matching source archive alongside the installer.

Sources: [Microsoft driver installation permissions](https://learn.microsoft.com/en-us/windows-hardware/drivers/print/point-and-print-with-packages),
[Windows spool job reads](https://learn.microsoft.com/en-us/windows/win32/printdocs/readprinter),
[Windows PDF renderer](https://learn.microsoft.com/uwp/api/windows.data.pdf),
[Ghostscript vector output](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html).
