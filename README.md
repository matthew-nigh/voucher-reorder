# Voucher Reorder

A Windows desktop tool that moves the three horizontal sections of a QuickBooks
Desktop voucher check to match differently ordered check stock. The user installs
one setup executable, chooses their real printer and stock order, then prints to
**Voucher Reorder** from QuickBooks. PDFs and scripts stay behind the scenes.

**Initial implementation; real Windows/QuickBooks/printer acceptance is still required.**
Do not put live check stock in the printer until the plain-paper overlay tests pass.
See [USER_GUIDE.md](USER_GUIDE.md), [TESTING_ON_WINDOWS.md](TESTING_ON_WINDOWS.md),
and the handoff in [NEXT_STEPS.md](NEXT_STEPS.md).

## Supported initial scope

- Windows 10/11 **x64**, one interactive Windows account on one workstation.
- Install while signed into the administrator account that will run QuickBooks;
  normal printing runs with that account's **unelevated** desktop token.
  Alternate administrator credentials, shared print servers, fast user switching,
  ARM64, and unattended printing while logged out are not supported.
- Portrait US Letter, one check per page, one-sided physical output, actual size.
- All six section orders; source split lines measured from the top in inches;
  per-source-section x/y nudges. Positive x moves right; positive y moves down.
- Default thirds are **11/3 inches**, not 3.5 inches. For 3.5/3.5/4-inch input
  sections, use split lines **3.5 and 7**. Unequal bands retain their heights and
  are stacked in the selected order, without scaling. Nudges clip at slot edges.
- The standalone engine supports multiple and mixed page sizes, rotated pages,
  nonzero CropBox origins, text, fonts, images and vector graphics. Production
  forwarding rejects non-Letter pages, encrypted PDFs, annotations and unusual
  `/UserUnit` values rather than silently changing physical scale.

## Architecture and choice

```text
QuickBooks -> Microsoft's signed MS Publisher Imagesetter PostScript driver
           -> Windows Standard TCP/IP LPR port, 127.0.0.1:515 / queue "voucher"
           -> per-user Python background receiver and durable queue
           -> bundled Ghostscript pdfwrite -> vector PDF band imposition (pypdf)
           -> bundled SumatraPDF -print-to ... -print-settings noscale,...
           -> selected Windows printer queue -> physical printer
```

Python's official embeddable runtime plus pure-Python pypdf keeps the engine
portable and testable on Linux. The settings UI uses Windows' built-in PowerShell
and WinForms; this avoids bundling another UI runtime. NSIS produces the installer
on Linux and Windows. No Python installation, scripts, PDF viewer UI, custom kernel
driver or third-party port-monitor DLL is required for the office user.

The existing Windows spooler/driver/port combination is a conservative capture
choice: [LPR byte counting](https://learn.microsoft.com/en-us/powershell/module/printmanagement/add-printerport)
provides explicit job framing. A fixed-file Microsoft Print to PDF port risks
shared-file overwrite and completion races; its ordinary port prompts for a name.
A custom spooler DLL would add deployment and stability risks. Our receiver
implements the bounded receive-job subset of [RFC 1179](https://www.rfc-editor.org/rfc/rfc1179),
accepts control/data in either order, and acknowledges only after durable admission.
It binds **only** to loopback and ignores untrusted LPR filenames and user metadata.

The signed Microsoft PostScript driver must be available in the target Windows
image. Setup fails visibly if it is missing or legacy drivers are blocked (for
example Windows Protected Print Mode). It does not disable Windows security policy.
This is the principal deployment gate for this initial build.

The engine copies PDF resources into Form XObjects and uses clipping/translation;
**it never rasterizes, resamples images, or scales content**. Ghostscript
[pdfwrite](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html) normally
preserves PostScript text and vectors; it is not a byte-for-byte PS conversion.
Sumatra's documented [noscale printing](https://www.sumatrapdfreader.org/docs/Command-line-arguments)
is requested explicitly, with Letter, simplex and automatic rotation disabled.
Sumatra and the physical printer driver may render at device resolution. End-to-end
MICR quality and physical placement cannot be certified by the PDF tests.

## Jobs, failures and privacy

- The receiver runs at sign-in through the user's Run key; settings starts it too.
  Print data stays under `%LOCALAPPDATA%\VoucherReorder`, inheriting the user's
  private profile ACL. The printer queue grants printing to its installing user.
- A complete job is limited to 100 MiB; at most 100 jobs wait. Control messages
  have separate small limits; incomplete receipts are deleted. Jobs run serially.
- States are `queued -> converting -> printing -> sent`. `sent` means accepted
  by the print command, **not proven to have come out of the printer**.
- A timeout, forwarding failure, or interrupted in-flight job is held for review
  and **never automatically reprinted**. Review both Windows queues and physical
  sheets before initiating a new QuickBooks print. Settings exposes job status
  and cancellation of jobs still waiting in this app.
- Byte-identical receipts are suppressed for 24 hours to handle a lost LPR ACK.
  An intentional byte-identical reprint in that period is also suppressed. Do not
  use this as a general reprint utility; reconcile output before issuing a new job.
- Successful, failed and uncertain jobs immediately lose their local PS/PDF payloads.
  Waiting data and status/digest records expire after 24 hours **while the worker is
  running**, or at its next start. Ordinary deletion is not secure erasure. Windows
  spooler data and backups are governed separately by Windows/site policy.
- No print contents, payee names, bank details or raw exception text enter app logs.
  The project contains only generated, clearly fake samples. Never attach a real
  check, spool file or settings file to this public repository.

## Develop and test on Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
# Debian/Ubuntu: sudo apt-get install ghostscript nsis p7zip-full
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Tests generate fake PDFs at runtime. PyMuPDF renders them **only as a test oracle**
to verify visible placement; it is not part of the shipped application. Tests also
inspect font/vector resources, offsets/clips, uneven sections, rotation, multiple
pages, invalid settings, LPR framing, duplicate receipts, retention and crash/failure
behavior. The Ghostscript integration test skips when `gs` is absent.

## Build the Windows installer

Requires Python 3.11+ with no build-time third-party modules, NSIS 3.11+, and 7-Zip.

```bash
# Works on Linux, including this checkout:
python3 scripts/build_windows.py
# Output:
# dist/VoucherReorder-0.1.0-Setup.exe
# dist/VoucherReorder-0.1.0-sources.zip
# dist/SHA256SUMS.txt
```

On Windows, install NSIS and 7-Zip (or use `windows-latest`), then run
`python scripts/build_windows.py`. The script downloads **SHA-256-pinned** upstream
Windows binaries and corresponding sources listed in `packaging/dependencies.json`.
It packages official Windows binaries on Linux; it does not claim to cross-compile
CPython, Ghostscript or Sumatra themselves. `--stage-only` prepares a payload without
compiling NSIS. First build needs internet; downloads are cached and rechecked.

The installer is unsigned. Setup may fetch Microsoft's signed C++ system runtime
from Microsoft if absent; this requires internet. This proprietary prerequisite is
**not bundled as an extra redistributable**. The installer verifies its Authenticode
signature before executing it. The official Python runtime contains its customary
Microsoft system-runtime DLLs. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

[Windows build workflow](.github/workflows/build.yml) tests Linux, builds on
`windows-latest`, checks PowerShell syntax and the packaged runtime, and uploads the
installer **together with corresponding source and checksums**. A future `v*` tag
push attaches those same files to a GitHub Release. No tag or release is needed
for PR builds. The workflow does not merge branches.

## License

Copyright (C) 2026 Voucher Reorder contributors. Licensed under GNU GPL version 3
or (at your option) any later version: **GPL-3.0-or-later**, without warranty.
[LICENSE](LICENSE) contains the full official text fetched from GNU. The first
implementation-branch commit replaces the original MIT license. Third-party
components retain their own licenses and notices; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Always distribute the source archive
alongside the installer, including on mirrors.
