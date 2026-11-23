# Security review — current branch, 2026-11-23

## Microsoft Print to PDF Local Port investigation

The optional virtual queue stays on **MS Publisher Imagesetter and the protected
unique-job monitor**. The inbox v4 Microsoft Print to PDF driver rejects that
monitor (`AddPrinterW`, stage 170, Windows error 1801 in the earlier CI prototype).
Microsoft [documents that v4 drivers do not support non-Microsoft port
monitors](https://learn.microsoft.com/en-us/windows-hardware/drivers/print/v4-driver-connectivity-architecture).
The supported Local Port alternative names a **single fixed file**; Microsoft
[describes that exact setup](https://learn.microsoft.com/en-us/troubleshoot/windows-server/printing/print-to-file-without-user-intervention)
as saving every job to the configured path. In this app, a fixed file would
overwrite or collide with another job while the watcher is stopped or two jobs
arrive together, reopening CR-04. Changing a queue's port between jobs cannot
bind arbitrary QuickBooks submissions to distinct paths across offline periods.
`PORTPROMPT:` gives a per-job filename dialog, but loses the unattended virtual
queue behavior. The existing PDF Inbox mode already supports that manual path.

CR-02 also cannot be closed by *assuming* Local Port writes run as the submitting
user. Microsoft's [Print Services security overview](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-prsod/340e969b-3243-4116-bf79-47c45bb40264)
describes user impersonation for processing external resources, but does not
specify the token used by this driver/monitor when it opens a file port. The new
`scripts/probe_pdf_local_port.ps1` is a **diagnostic**, run by Windows CI after
the existing v4 vector-output test: it submits from a real standard-user account,
records the PDF file owner's SID, then redirects the same path through a junction
to a directory writable only by SYSTEM/administrators and reports whether a file
appears there. It does not change the installed queue and does not gate this
Imagesetter design. The results have **not yet been observed**; this Linux host
cannot establish Windows token or junction behavior. A user-owned PDF and a
blocked junction would support the narrow token hypothesis on that runner, but
would still leave the fixed-filename CR-04 failure. No v4 virtual-printer change
is shipped on the basis of this probe.

## Follow-up implementation status

The follow-up on this branch fixes CR-03's age-based retention and explicit
Dismiss deletion. Failure/review payloads and metadata expire after seven days by
default, configurable from one to 365 days through
`VOUCHER_REORDER_FAILURE_RETENTION_DAYS`. Cleanup runs when the watcher starts,
at least daily while it is running, and at processor recovery. Saved PDF output,
stopped installations, crash leftovers, backups and spooler copies remain outside
this retention guarantee. A daily scan does not impose a total byte budget.

CR-01, CR-02 and the CR-04 filename remainder are **fixed in source** by the
protected native printer package in this follow-up; Windows acceptance remains
pending. `PrinterDeploy.exe` must be independently verified by an administrator
in admin-protected staging. It deploys embedded helper/monitor bytes with protected
ACLs and verifies them. The per-user launcher elevates the installed
`PrinterSetup.exe` directly, with only install/remove and a canonical account SID;
it no longer elevates PowerShell or reads a per-user script into privileged code.
The helper also refuses execution outside its protected installed location.

The native monitor writes UUID-named PostScript jobs under an administrator/SYSTEM-owned
Program Files spool, never into a user-controlled folder. It rejects reparse points,
untrusted owners/ACLs and mismatched directory identities and holds ancestor handles without
delete sharing. Files use exclusive `CREATE_NEW`, are flushed, and are published
without replacement; user read/delete rights apply only to completed files. The
unprivileged handoff copies into the durable queue and records the UUID before
acknowledging the source, including across volumes and after restart. The old
pause/resume fixed-file guard is removed. Existing fixed-port installations fall
back to PDF mode until explicitly migrated. Removal still never restarts Spooler.
The v3 MS Publisher Imagesetter driver produces the PostScript; the bounded
Ghostscript worker converts it to PDF under the desktop user's account.

**Residual risk:** the new privileged native code and v3 printer driver/monitor
integration require Windows 10/11 UAC, ACL, reparse, offline burst and crash
qualification. Native acceptance harnesses are supplied but were not run on this
Linux host. Cross-compilation and portable tests do not establish those results.
Distribution remains unsigned (CR-09/CR-10); initial administrator verification of
the staged deployment package is the trust bootstrap, not a user-side hash check.
Existing changed helper bytes are refused; upgrades to loaded monitor code need
administrator maintenance. Old detached Local Port entries, unclaimed protected
PDFs and crash `.partial` files need administrator reconciliation/cleanup. There
is a 100 MiB per-job limit but no aggregate protected-spool budget or age limit.
Physical printing and spooler crash/retry are not an exactly-once guarantee.

CR-05 remains **open and explicitly deferred**: no Low-integrity sandbox was
implemented. Parsers/renderers retain the user's normal-integrity token;
Ghostscript already uses `-dSAFER`. Other findings are unchanged. CR-10's version
identity remains v0.2.6; native toolchain and distribution-provenance risks remain.
This status supersedes historical “Status” sentences below.

This review covers `codex/windows-test-fixes-2` / PR #6 at **1180ad8**, plus the
small hardening changes in the commit containing this report. Matthew's successful
functional test is useful evidence, but does not validate the privilege boundaries.
The requested build is identified as v0.2.6; **the checked-out project metadata and
workflow artifact names still say 0.2.4**. Findings are tied to the source revision,
not an assumed binary/tag match (CR-10). No GitHub CI was queried during this review.

**Release assessment:** the two High source-level boundaries are redesigned and
fixed in this follow-up, subject to the native qualification and trust-bootstrap
residuals above. PDF Inbox mode avoids privileged printer setup and the new port
monitor. Windows security acceptance is still required before broader virtual
printer rollout; no native exploit or native acceptance result is claimed here.

The entire earlier review is preserved verbatim under **Historical review record**.
Its line numbers, architecture, test counts and remediation statuses describe prior
releases. This section supersedes those statuses for the current code.

## Threat model and scope

| Asset / actor | Trust boundary and consequence |
| --- | --- |
| Check/voucher PDFs, bank/MICR data, document names | Original, queued, reordered, failed and spooled copies require confidentiality; altered, duplicated or omitted checks also have financial consequences. |
| User files | Inbox pickup, output publication, cleanup and uninstall must not overwrite/delete unrelated files or follow attacker-controlled paths. |
| Standard user / same-user processes | Can modify their installation, AppData, settings and inputs. Same-token file changes alone are not privilege escalation. Passing those bytes or paths to an administrator or SYSTEM creates a distinct boundary. |
| Other local users | Should be excluded by profile/file ACLs and printer SDDL. No production TCP/LPR listener remains. Shared/redirected output folders may intentionally have different permissions. |
| Malicious PDF or Inbox entry | Filename, PDF objects/streams, special files and reparse points are untrusted. A dropped PDF must not control executable arguments, escape storage or indefinitely stop other work. |
| Printer / network | Windows drivers, spooler, shared print servers, transport and physical device see sensitive data. The app does not add transport authentication/encryption or control remote retention. |
| Supply chain | Repository, Actions, runners, Python packages, native downloads, NSIS and distribution must preserve reviewed bytes. Hash pins are integrity checks, not publisher authentication. |

Reviewed NSIS, all application modules, PowerShell/C# helpers, build scripts,
dependency/license files, workflow permissions/triggers, and security-related tests.
Tests used only synthetic data and fake senders. Local environment: Linux,
CPython **3.13.5**, pypdf **7.1.1**, pytest **9.2.0**, Ruff **0.17.6**, PyMuPDF
**1.28.2**. The packaged/CI Python pin is **3.13.12**, not the local interpreter.
No Windows PowerShell runtime is available here. UAC, native junction/ACL semantics,
spooler impersonation, Windows Add-Type, Smart App Control (SAC), printer/network
traffic and physical output were **not executed**. This is not native fuzzing or a
complete advisory audit of all bundled C/C++ libraries.

## Severity-ranked current findings

| ID | Severity | Status in this commit | Finding |
| --- | --- | --- | --- |
| CR-01 | High | **Fixed in source; native acceptance and distribution trust remain** | Protected native helper replaces elevated user-writable PowerShell. |
| CR-02 | High, conditional | **Fixed in source; native acceptance pending** | Protected spool, ACL/final-handle checks, held ancestors and unprivileged handoff replace user-controlled port paths. |
| CR-03 | Medium | **Fixed for age-based retention and Dismiss; residual storage limits remain** | Failed/review payloads and status expire after seven days; Dismiss deletes both. |
| CR-04 | Medium | **Fixed in source; native offline/crash qualification pending** | Unique per-job files replace the shared Local Port filename; removal never restarts Spooler. |
| CR-05 | Medium | **Open; partially mitigated** | Parser processes have resource limits, but retain the user's filesystem/network authority. |
| CR-06 | Low | **Open** | Filesystem privacy and containment depend on inherited ACLs and stable parent directories. |
| CR-07 | Low | **Fixed** | Output publication could replace an existing destination despite its no-overwrite contract. |
| CR-08 | Low | **Fixed at input leaf; races remain CR-06** | Pickup did not reject all special files / Windows reparse attributes before opening. |
| CR-09 | Low | **Open** | Unsigned distribution and runtime compilation need SAC/WDAC validation and a trusted release process. |
| CR-10 | Low | **Version identity fixed; supply-chain coverage open** | Metadata, workflow artifact names, guidance and notices now identify v0.2.6; native provenance and release review remain. |
| CR-11 | Info | **Verified locally / no code fix needed** | Python advisory queries and manifest hashes passed within the stated scope. |

### CR-01 — High: UAC approves an interpreter, not the script's provenance

**Location:** `packaging/request_printer.ps1:8`, `:10`, `:15`;
`packaging/installer.nsi:21`; `packaging/printer.ps1`.

**Impact / evidence:** setup reads `printer.ps1` from the per-user deployment,
embeds its contents in `-EncodedCommand`, and runs system PowerShell with `-Verb
RunAs`. A standard user or same-user process can replace that script before the
snapshot. An administrator approving the legitimate-looking PowerShell prompt,
including alternate credentials, then executes those replacement bytes. Encoding
and the Microsoft signature on PowerShell do not authenticate the embedded code.
Snapshotting closes a later file-reopen race, not this provenance problem. This is
conditional on approval, **not a UAC bypass**. No elevated exploit was executed.

**Recommendation:** use a narrow, independently authenticated provisioning helper
installed in an administrator-protected location, with protected dependencies and
small validated inputs; or have an administrator provision from independently
verified trusted media. Bind approval to the code actually executed. A hash check
inside another user-writable script is insufficient. Until resolved, favor PDF
Inbox mode on machines where standard users must not influence elevated code.
**Follow-up status: fixed in source.** See `packaging/native/deploy.cpp`,
`setup.cpp`, `secure.hpp`, and `packaging/request_printer.ps1`. Initial deployment
uses independently verified admin-protected media, not an automatically elevated
per-user package. Deployed bytes are compared with embedded resources, all code
paths are protected and checked, and UAC approves the helper image itself. No
script or arbitrary executable/path input is accepted. Unsigned provenance and
native UAC qualification remain residual risks, not claimed fixed here.

### CR-02 — High, conditional: privileged fixed-port output follows mutable paths

**Location:** `packaging/printer.ps1:9`, `:71`, `:87`, `:90`, `:96`;
`packaging/request_printer.ps1:4`; `voucher_reorder/inbox.py:24`.

**Impact / evidence:** elevated setup canonicalizes the string, checks the SID
shape, rejects UNC paths and requires the leaf `job.pdf`. It does not bind the
path to the target SID's actual profile, validate every parent/file reparse point,
or hold a trusted directory handle. It adds SYSTEM access to the existing folder
and makes that user-owned path a Local Port output destination. A junction or
file replacement before setup or later writes could redirect an elevated ACL
operation or spooler write to an unintended location. Actual protected-file
impact depends on Windows Local Monitor/driver impersonation and reparse handling;
**no SYSTEM arbitrary-write or elevation exploit is claimed as demonstrated**.
The new input-leaf check runs after spooler output and cannot protect this boundary.

**Recommendation:** verify this in a disposable Windows VM with benign sentinel
files, both same-user and alternate-admin setup, before and after provisioning.
Trace the effective writer token and final handle target. Use an administrator-owned
spool destination with authenticated handoff or an equivalent handle-based design
that cannot be retargeted by the desktop user. Do not rely on a one-time `resolve`
or `Test-Path` check.
**Follow-up status: fixed in source.** `packaging/native/monitor.cpp` and
`secure.hpp` bind writes to protected Program Files directories, verify every
component without following reparses, check directory identities/ACLs/owners, and
hold ancestors against replacement. User ACLs cannot create entries or retarget
those directories; completed files permit read/delete only. Handoff occurs at
user privilege in `Queue.accept_file(protected_spool=True)`. Native tests cover
junction leaf/ancestor rejection, sentinel preservation, hostile writable ACLs,
held-handle replacement and restricted-token write denial; they are pending Windows
execution. Portable handoff tests cover cross-volume copying and recovery.

### CR-03 — Medium: 24 hours is not a universal retention limit

**Location:** `voucher_reorder/queue.py:68`, `:100`, `:137`, `:239`;
`voucher_reorder/worker.py:108`; `voucher_reorder/spool.py:113`;
`README.md:197`; `USER_GUIDE.md:65`.

**Impact / evidence:** `failed`/`review` inputs move to `Needs attention`; expiry
always preserves them, regardless of age. Dismiss removes only the status entry.
A synthetic old failed job retained both state and payload after `expire()`.
The 512 MiB admission accounting excludes `Needs attention`, so repeated rejected
arrivals can accumulate full documents until disk pressure stops work. Failed
states also remain in queue scans until dismissed. The 24-hour cleanup for other
states runs at processor startup, not continuously; an idle/stopped installation
has no hard deletion deadline. Saved output PDFs, unclaimed Inbox/Incoming files,
legacy receipts, spool document titles, crash leftovers, backups and printer/server
copies are outside that deadline. This is partly intentional recovery policy,
not a reason to silently destroy failed checks in a security patch.

**Recommendation:** define separate retention policies for failed checks, successful
status, manual exports and metadata; expose age/size and explicit deletion of
failure payloads; bound aggregate failure storage. Design cleanup scheduling and
crash recovery to match the promised deadline. Use disk encryption and local/private
output destinations as appropriate; ordinary unlink is not secure erasure.
**Status: open; existing recovery/retention behavior deliberately unchanged.**

### CR-04 — Medium: fixed-port serialization is best effort, not durable isolation

**Location:** `voucher_reorder/spool.py:95`, `:116`; `voucher_reorder/watcher.py:91`;
`packaging/printer.ps1:61`; `README.md` fixed-port concurrency guidance.

**Impact / evidence:** all virtual jobs write the same `Incoming/job.pdf`. The
notification broker attempts to pause competing jobs and warns when it observes
overlap, but cannot guarantee it acts before a second writer or while signed out,
stopped or blocked. Missing or overwritten check jobs are an integrity concern.
This is source-confirmed and documented; native concurrent-job testing was not
rerun. Queue SDDL is restricted to the owner plus SYSTEM/administrators, and the
existing-printer path explicitly disables sharing and retained printed jobs.
Port removal can restart the **machine-wide** Spooler after checking that no jobs
are queued; a new job can arrive between the check and restart.

**Recommendation:** use unique durable per-job destinations/authenticated handoff.
Until then enforce the documented one-job-at-a-time operational limit with an
active signed-in watcher and reconcile source batches against output. Make any
spooler restart a separately explained maintenance action; preserve unrelated
queues/ports.
**Follow-up status: fixed in source.** The custom port creates a new UUID file with
`CREATE_NEW` for each StartDoc, ignores application output names, and publishes
completed PDFs without replacement. Concurrent/offline jobs have independent files;
there is no watcher pause timing requirement. UUID-keyed copy/ack recovery prevents
pickup retries from becoming duplicate admissions. Tests cover offline bursts,
copy/commit interruptions, failed acknowledgement and retention. Native offline
printing is added to `scripts/test_clone_printer.ps1` but has not run on this host.
Spooler/power failures, partial spool storage and physical-print reconciliation
remain residual risks. Removal does not restart the machine Spooler.

### CR-05 — Medium: bounded execution is not an OS security sandbox

**Location:** `voucher_reorder/bounded.py:60`, `:134`, `:212`;
`voucher_reorder/printing.py:54`; `voucher_reorder/windows.py:26`;
`packaging/CheckedPrint.cs:103`.

**Impact / evidence:** untrusted pypdf parsing, PDFium rendering and legacy
Ghostscript conversion run with the user's token. Windows Job memory limits,
process-tree termination, deadlines, page/output limits and Ghostscript `-dSAFER`
reduce DoS but do not deny access to the user's other files or network. A native
parser exploit would retain those rights; **none was demonstrated or identified
by the Python audit**. Many bounded malicious jobs can still consume sustained
CPU. A 250-page print budget can exceed two hours by design.

**Recommendation:** investigate a restricted-token/AppContainer parser/renderer
with only private inputs/outputs accessible, and keep privileged provisioning
separate. Maintain native-library advisory monitoring and bounded fuzz corpora.
Existing tests cover malformed xref, resource/decode limits, timeout/reaping and
bad-job isolation; the new tests add corrupt page trees/truncated streams and
catalog/page-action removal. Fresh output omits catalog JavaScript/attachments,
page additional actions and source title in the tested fixture; it is not a
proof of arbitrary-PDF sanitization. **Status: open; existing resource controls retained.**

### CR-06 — Low: inherited ACLs and parent-path races remain assumptions

**Location:** `voucher_reorder/config.py:71`, `:92`, `:97`;
`voucher_reorder/queue.py:25`, `:53`, `:68`, `:166`;
`voucher_reorder/inbox.py:16`; `packaging/installer.nsi:116`.

**Impact / evidence:** Inbox, queue and output creation mostly inherit ACLs.
Python's mode `0700` is not a full Windows DACL policy; setup only adds SYSTEM to
Incoming, without removing pre-existing broad grants. Existing shared/redirected
folders may expose PDFs to other accounts. Output `resolve()` blocks aliases into
private folders at check time, but parents may change afterward. Queue enumeration
follows child directory links; a benign Linux reproduction linked a job directory
to an external synthetic folder and `update(..., 'sent')` deleted that folder's
`input.pdf`. This required write access to the queue, **not merely a dropped PDF**,
and establishes neither cross-user access nor escalation under normal profile ACLs.
Uninstall/cleanup also rely on trusted roots. The Inbox leaf check is not a
handle-based no-follow guarantee and its open/rename race remains.

**Recommendation:** verify effective owner/SYSTEM/admin-only access for AppData
and temp roots on native Windows, including upgraded/redirected profiles. Reject
unexpected reparse ancestors and validate final handles for reads/moves/deletes;
use ACL-protected roots to prevent concurrent directory substitution. Validate
queue state/schema and quarantine corrupt state rather than blocking all work.
Treat network/shared output permissions and printer transport security as explicit
user/admin decisions. **Status: open; no cross-user exposure was demonstrated.**

### CR-07 — Low: output publication could overwrite a destination

**Location:** `voucher_reorder/printing.py:29`, `:45`;
`voucher_reorder/filesystem.py:17` (new helper).

**Impact / evidence:** the old `os.replace` publication overwrote any existing
UUID destination, contrary to the function's contract. UUID unpredictability
makes accidental collision negligible and practical hostile placement difficult;
this is not arbitrary overwrite of a chosen filename. Forced-collision tests
reproduced replacement of both a normal file and a symlink directory entry
(the symlink's target was not overwritten).

**Recommendation / fix:** publish atomically with no replacement: Windows
`os.rename`, POSIX exclusive `os.link`, then clean the temporary source in the
existing `finally`. A collision fails and preserves the existing entry. Existing
bounded Windows sharing retries remain; metadata replacement keeps its old
semantics. POSIX filesystems without hard-link support fail closed. This does not
solve shared-folder ancestor races (CR-06).
**Status: fixed in this commit; collision and sharing-retry tests pass.**

### CR-08 — Low: special/reparse inputs reached the open operation

**Location:** `voucher_reorder/queue.py:115`; `voucher_reorder/inbox.py:16`.

**Impact / evidence:** pickup previously checked only `is_symlink()`. A FIFO named
`.pdf` on POSIX could block the event broker in `open` before bounded parsing;
Windows reparse files not classified as symbolic links were not excluded.
Directories were eventually rejected by open/seek, not explicitly at admission.
Three synthetic attribute cases prove that old code reached the open operation.
These tests do not create or validate a native Windows reparse attack. FIFO
behavior primarily concerns source/Linux use, not ordinary NTFS files.

**Recommendation / fix:** `lstat` before opening, require a regular file and
reject `FILE_ATTRIBUTE_REPARSE_POINT`. Existing ordinary PDFs and failed-file
continuation still work. This intentionally refuses reparse-backed cloud placeholders
rather than following them; use a locally materialized regular PDF. Parent changes
and check/open/rename races still require CR-06's handle-level work.
**Status: fixed for pre-existing input-leaf types in this commit.**

### CR-09 — Low: unsigned package and Add-Type are not deployment trust guarantees

**Location:** `packaging/installer.nsi:21`; `packaging/settings.ps1:6`;
`packaging/user_links.ps1:3`; `packaging/settings_identity.cs`;
`packaging/print_pages.ps1:14`; `voucher_reorder/windows.py:151`;
`.github/workflows/build.yml` release notes.

**Impact / evidence:** NSIS requests a standard-user install; HKCU/LocalAppData
integration does not require admin. There is no all-users/admin installer mode.
Optional setup is the only intentional elevation path (CR-01). Setup and app scripts
are unsigned. SAC/WDAC/AppLocker/Constrained Language can block setup, scripts,
DLLs or `Add-Type` compilation of `settings_identity.cs`/`CheckedPrint.cs` even when
Matthew's machine works. Process-scoped `-ExecutionPolicy Bypass` does not change
machine policy and is not an application-control bypass. Settings identity C#
uses fixed COM property keys and shell APIs, with no document text compiled into
source; tampering with it is same-user code execution unless launched elevated.

**Recommendation:** sign/authenticate distributed artifacts, validate clean Windows
10/11 and SAC/WDAC policies including runtime compilation, and publish checksums
through a trusted channel. Consider precompiled authenticated helpers where policy
requires them. Do not ask users to disable system-wide protections as a workaround.
**Status: open; no native application-control validation performed.**

### CR-10 — Low: release identity and native build provenance need follow-through

**Location:** `pyproject.toml:7`; `.github/workflows/build.yml`;
`packaging/dependencies.json`; `scripts/build_windows.py:75`, `:147`;
`THIRD_PARTY_NOTICES.md`.

**Impact / evidence:** requested v0.2.6 still builds as 0.2.4 in source/workflow;
notices refer to 0.2.1 archive names and a VC-runtime download which current setup
no longer performs. This impairs artifact identification and operational guidance.
Actions are full-SHA pinned; Python dependencies, including setuptools, are pinned
and the development lock uses hashes. Native downloads are SHA-256 pinned.
Hosted runner tools, Visual Studio/7-Zip, apt packages and the Chocolatey supply
chain remain external trust inputs, although NSIS is version-pinned and tool
versions are recorded. No recurring audit step is present in the workflow.

**Recommendation:** reconcile version/tag/artifact/notices before publishing,
record/verify native dependencies and toolchain provenance, run automated advisory
checks, and enforce release-environment reviewers and protected tags outside the
repository. Preserve GPL-3.0-or-later application and AGPL Ghostscript corresponding
sources alongside binaries; keep Python/pypdf/PDFium and transitive notices.
Source/notices packaging exists and PDFium wheel licenses are extracted, but this
review did not rebuild/audit a final v0.2.6 installer or establish legal completeness.
**Status: open; pins, licenses and workflow were not changed by this commit.**

### CR-11 — Info: dependency and hash checks passed within a bounded scope

**Location:** `requirements-dev.txt`; `pyproject.toml`;
`packaging/dependencies.json`; `scripts/build_windows.py:29`.

**Impact / evidence:** pip-audit **2.10.1**, installed in a separate temporary
virtual environment, reported **0 known vulnerabilities for 14 queried package
versions** on 2026-11-22. The hashed requirements query covered 12 applicable Linux
pins; a second explicit-pin query included Windows-only colorama and pypdfium2.
Audited pins: Pygments 2.21.0, charset-normalizer 3.5.2, colorama 0.4.6,
iniconfig 2.3.1, packaging 26.3, pillow 13.0.0, pluggy 1.7.0, pymupdf 1.28.2,
pypdf 7.1.1, pytest 9.2.0, reportlab 4.5.1, ruff 0.17.6, setuptools 84.2.1,
pypdfium2 5.15.2. Both queries used `--no-deps --disable-pip`; the queried target packages
were not installed or executed by the audit. All **7/7** pinned downloaded archives/wheels matched
the manifest SHA-256, including the two pypdf artifacts fetched for this check.

**Recommendation:** rerun before release. Python advisory results do **not** cover
CPython 3.13.12, Ghostscript 10.08.0, embedded PDFium 159.0.8149.0 or their complete
native dependency graphs, Windows drivers or NSIS. Querying the wrapper wheel is
not a complete PDFium CVE assessment. Matching hashes do not prove trusted upstream
origin or absence of vulnerabilities. **Status: verified checks; no code fix needed.**

## Additional reviewed controls and limits

| Area | Current result |
| --- | --- |
| Command construction | Python passes argument lists without `shell=True`; PowerShell uses `-File`, not evaluation of printer/PDF strings. UAC action is a ValidateSet, SID is locally obtained, and single quotes in the path are doubled before encoding. No filename/printer-name shell injection was found. User-controlled elevated script bytes remain CR-01. |
| Temp files | JSON and exported PDFs use unpredictable `mkstemp`, flush/fsync and publication; printing creates private per-job temp space and kills bounded children before cleanup. CLI inspection uses a randomly created system-temp directory. Abrupt process death can leave inspection/export temp copies; no startup sweep covers all such locations (CR-03/06). Settings Add-Type uses the current user's compiler temp environment; no check contents are deliberately compiled. |
| Logging | `ErrorCapture` caps retained diagnostics at 8 KiB and allowlists/redacts messages. `processing-error.json` stores operation/type/numeric codes; checked print job title is generic. Persistent queue/failure metadata, saved paths, spool metadata and legacy receipts can contain identifying filenames/titles. Elevated `Write-Error` may expose paths/queue metadata to local diagnostics. No PDF/MICR content logging was found in the normal worker; CLI tracebacks, crash dumps and external drivers are outside that guarantee. |
| PDF controls | Limits include 100 MiB admission, 250 pages, 256 MiB output/expanded checks, 768 MiB worker / 384 MiB Windows print job memory and deadlines. Fresh catalog, layer/annotation/image rejection and vector checks reduce unsafe/changed output. They do not authenticate the payee/amount or ensure a malicious document is financially correct. |
| CI authorization | `pull_request`, not `pull_request_target`; global `contents: read`; only the tag-push release job gets `contents: write`, with `environment: release`. No workflow reference to a custom secret was found; release uses the job token. Shell tag handling uses a quoted environment variable. SHA-pinned actions and synthetic fixture uploads are positive controls. Checkout persists its read token by default; environment protection settings were not queried. |
| Network/printer | No production TCP listener or telemetry/upload path found. Shared/network printers and UNC output folders remain possible: remote access, SMB/print transport, driver trust, device storage and spool cleanup are Windows/admin responsibilities. App deletion cannot erase those copies. |
| Install/uninstall | Per-user guard acquired before extraction, versioned staging and rollback/retirement controls remain. Uninstall preserves user data/held jobs; silent uninstall skips optional printer removal. No broad Everyone grant was found. Native concurrent installs, junction attacks, alternate-admin UAC and corrupted current.ini handling remain acceptance work; a per-user installation is not a boundary against its own owner. |

## Tests, small fixes and remaining acceptance

Only two runtime changes were made: **CR-07 atomic no-overwrite PDF publication**
and **CR-08 regular/non-reparse input-leaf admission**. The shared bounded retry
helper preserves metadata replacement behavior. No installer, elevation, printer,
retention, dependency or workflow behavior was changed. Added **17 security test
cases** in `tests/test_security_current.py`; adjusted the existing publication-retry
test to exercise the no-overwrite operation.

Baseline: **333 passed, 1 skipped**; Ruff lint passed. Five focused cases deliberately
failed against the original `1180ad8` runtime files (two output collisions, three
special/reparse input cases). Restoring the hardening made them pass. The focused
security/filesystem run passed **24 tests, 1 skipped**. Separate synthetic probes
confirmed external-folder mutation through a same-user queue directory link and
retention of an old failed payload; no real user data was touched.

Final checks for this commit:

```text
.venv/bin/python -m pytest -q                  # 350 passed, 1 skipped (15.87 s)
.venv/bin/ruff check .                        # passed; 0 lint errors
.venv/bin/ruff format --check .               # 51 files already formatted
git diff --check                             # no whitespace errors
```

Audit commands used (the second file contains the 13 lock pins, without platform
markers, plus `pypdfium2==5.15.2`):

```sh
/tmp/voucher-security-audit-venv/bin/pip-audit -r requirements-dev.txt --no-deps --disable-pip --format json --output /tmp/voucher-security-pip-audit.json
/tmp/voucher-security-audit-venv/bin/pip-audit -r /tmp/voucher-security-all-pins.txt --no-deps --disable-pip --format json --output /tmp/voucher-security-all-pins.json
```

Before wider virtual-printer use, perform the CR-01/02 native tests, inspect
AppData/temp/output ACLs from a second standard account, test pre/post-setup
junctions and handle targets, offline/overlapping fixed-port jobs, shared printer
transport/storage, and SAC/WDAC with Add-Type. Use fake vouchers and disposable
VMs. No Windows test, build, signing check or post-push CI result is claimed here.

## Relationship to earlier findings

SR-01's old pypdf version is replaced and bounded execution remains, with residual
CR-05. SR-02/SR-09's LPR listener is removed; fixed-port CR-02/04 replace those
threats. **SR-03's protected-helper mitigation no longer applies: CR-01 reopens it.**
SR-04 malformed-file isolation, SR-06 layer rejection and SR-07 installer locking
remain. New Inbox arrivals now move to unique jobs, superseding SR-05's receipt
model; legacy receipts/manual byte deduplication still exist. SR-08 no longer means
all terminal payloads are deleted: failed/review preservation is intentional
(CR-03). SR-10 now uses checked PDFium EMF/GDI rather than Sumatra; native printer
acceptance remains necessary. SR-11 pinning improved, with CR-09/10/11 limits.

---

## Historical review record — preserved verbatim, superseded above

# Independent security and quality review

> Historical notes below describe earlier releases. v0.2.3 replaces retained RAW
> spooling and the elevated provisioning package with a built-in PDF fixed-port
> clone and native event broker. Inbox arrivals now move to unique jobs; failed
> inputs remain in Needs attention for explicit retry. See README.md and
> TESTING_ON_WINDOWS.md for current behavior and fixed-port concurrency limits.


The original review covered `codex/initial-build` at `efec173`. The status table
records the remediation on `codex/security-fixes` and the Windows follow-up on
`codex/security-fixes-2`. The evidence, reproductions
and recommendations below the table describe the reviewed version.

The Windows follow-up diagnosed the original CI failure using bounded, sanitized
stderr capture: `OutOfMemoryException` in the 600-DPI bitmap allocation. That path
has been replaced with pinned PDFium vector EMF/GDI printing, with preflight refusal
of bitmap fallback and blank pages. Printing deadlines scale with page count. CI
now requires six consecutive ten-page jobs with nonblank, image-free file-port output and a measured Windows
Job peak below 256 MiB per job, flat across jobs (the print-tree cap is 384 MiB).

The main installer embeds a matching, hash-checked provisioning package and can
install/configure it with one optional UAC elevation. Provisioning has its own
uninstaller. Version mismatch on per-user upgrade falls back to PDF mode. No old
port-515 deployment exists, so the legacy update/uninstall hard block was removed
without adding migration. Native CI results for the final revision are recorded in
PR #4; physical MICR, driver compatibility and alternate-credential UAC still require
Windows 10/11 acceptance. Linux pytest and Ruff are run for every revision.

## Original scope and evidence

Inspected all application modules, packaging scripts, installer/uninstaller,
dependency manifest, CI workflow, existing tests and operational documentation.
Exercised synthetic PDFs, real loopback sockets through the existing suite,
queue/recovery and deployment fault scenarios. No real financial data was used.

Execution environment: Linux, Python 3.13, pypdf 6.9.1, PyMuPDF 1.28.2. The existing
71 tests passed, including the locally installed Ghostscript integration. All
eight cached artifacts named in `packaging/dependencies.json` matched their
SHA-256 pins. This verifies consistency with the manifest, not independent
upstream provenance or freedom from vulnerabilities. Inspected the hash-matched
SumatraPDF 3.6.1 source for print options and error propagation. Queried OSV for
the pinned pypdf version and checked the cited upstream advisories/patch.

Windows UAC, alternate credentials, native ACLs/reparse points/DLL loading,
Win10/11 printer drivers, QuickBooks and physical paper were **not exercised
locally**. Windows-specific findings distinguish source evidence from outstanding
native validation. Existing CI provisioning mocks do not establish those facts.
This is not an exhaustive CVE audit of every native/transitive dependency.

```sh
.venv/bin/python -m pytest -q
# 71 passed, 10 xfailed after adding this review's tests
.venv/bin/python -m pytest tests/test_security_review.py --runxfail -q
# 10 failed: deliberate reproductions of six distinct findings
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The new tests use `xfail(strict=True)` with specific expected exception classes.
Unexpected passes fail CI, requiring removal of the marker when a defect is
resolved. The malformed-xref test kills its child process after three seconds;
it cannot leave an infinite loop in the pytest process. No tests elevate, print,
modify installed applications or bind the real LPR port.

## Ranked findings

| Finding | Severity | Status | Change and remaining validation |
| --- | --- | --- | --- |
| SR-01 | High | Mitigated | pypdf 7.1.1 with matching wheel/source hashes. Separate processes bound time, memory and page count. PDF output writes are capped before extending files. Windows CI measures peak process-tree memory on six consecutive ten-page vector jobs; timeout and error-log regressions are covered. |
| SR-02 | High | Mitigated | Owner-restricted, unshared Windows spool queue retains RAW jobs on a local NUL: port. No legacy port-515 queue was deployed; it no longer blocks per-user update/uninstall. Two-account access and offline handoff need native validation. |
| SR-03 | High | Mitigated; bundled provisioning | Main setup embeds the version-matched admin package; one optional elevation installs/configures its protected native launcher/scripts. Separate package uninstall is supplied. Runtime staging and execution use the protected directory. Alternate-credential UAC and installer provenance require native acceptance and trusted distribution. |
| SR-04 | Medium | Fixed | A rejected file signature suppresses repeated parsing. An Inbox error allows other files and queued jobs to proceed. |
| SR-05 | Medium | Fixed | Admission journals the pending source receipt in durable job state. Receipt reconciliation precedes printing and expiry. |
| SR-06 | Medium | Fixed | Layered PDFs with optional-content catalog configuration are rejected with a flattening instruction. |
| SR-07 | Medium | Mitigated | Install and uninstall share an exclusive per-user handle before extraction. Cleanup targets retired activations. Uninstaller publication is staged. Native concurrent and disk-full tests remain pending. |
| SR-09 | Medium | Mitigated | Removed the production LPR server. Bounded, cancellable spool reads quarantine interrupted jobs. Private admission reserves disk space and caps aggregate input. Windows controls its own spool storage. |
| SR-10 | Medium | Mitigated; vector path | Replaced raster printing with pinned PDFium vector EMF and checked GDI calls; all pages preflight before StartDoc, raster fallback/blank pages fail closed, and CI verifies 60 vector output pages in order. Uncertain attempts enter review. Native failure injection, printer compatibility and MICR checks remain pending. |
| SR-08 | Low | Fixed | Startup and periodic cleanup retry terminal payload deletion while preserving delivery state. |
| SR-11 | Low | Mitigated | Actions use full SHAs, Python tooling has a hashed lock, and builds record native tool versions. Release reviewers, signing and hosted toolchain trust remain external controls. |

## Original findings and recommendations

### SR-01 — High: known vulnerable parser, no time/memory/page budget

**Locations:** `pyproject.toml:10`; `packaging/dependencies.json:13`;
`voucher_reorder/inbox.py:49`; `voucher_reorder/engine.py:19`, `:24`, `:41`;
`voucher_reorder/worker.py:95`.

**Impact:** a user-provided PDF can permanently consume the worker thread/CPU.
Other PDFs and already queued jobs stop; shutdown/upgrades wait and eventually
fail. In-process allocation attacks can terminate the worker or exhaust the
user's memory. The 100 MiB input cap does not bound decoded objects, page-tree
expansion or content-stream processing. `strict=True` is not a resource sandbox.
The external Ghostscript/Sumatra timeout does not cover Python parsing.

**Reproduction:** run `test_malformed_xref_finishes_in_bounded_time` with
`--runxfail`. A 144-byte file with a valid header/EOF marker and truncated xref
passes the handoff envelope checks but hangs `read_pdf`; the test terminates it
at three seconds. This reproduces
[GHSA-39mj-jf6j-2qj3](https://github.com/py-pdf/pypdf/security/advisories/GHSA-39mj-jf6j-2qj3),
fixed upstream in 6.20.0. The fixture is adapted from
[upstream PR 4170](https://github.com/py-pdf/pypdf/pull/4170).

Other OSV-reported affected paths include
[content-stream allocation](https://github.com/py-pdf/pypdf/security/advisories/GHSA-cgf9-327m-v77c)
(fixed 6.21.0),
[strict-mode exceptions](https://github.com/py-pdf/pypdf/security/advisories/GHSA-4vqv-7265-gm2w)
(fixed 6.21.3), and
[page-tree allocation](https://github.com/py-pdf/pypdf/security/advisories/GHSA-cggf-277g-3q54)
(fixed 6.21.4). Those allocation attacks were not run to exhaustion. These are
examples, not a claim that 6.21.4 resolves every current advisory.

**Recommended fix:** select a currently supported version after reviewing all
applicable advisories; update the development pin and packaged wheel/source hashes
together. Put parsing, conversion and rendering behind enforced wall-clock,
memory, expanded-output and page-count limits (Windows Job Objects/restricted
worker process). Reject/quarantine one offending job without blocking other jobs.
Avoid cloning unrelated catalog structures where only pages are required.

### SR-02 — High: loopback is a machine boundary, not a user boundary

**Locations:** `voucher_reorder/worker.py:83`; `voucher_reorder/lpr.py:19`, `:64`,
`:92`; `packaging/printer.ps1:41`, `:46`.

**Impact:** any local process able to connect to IPv4 loopback can submit arbitrary
PostScript to the worker, which converts and prints it as the receiving user.
Windows printer-queue permissions do not protect a direct TCP connection. This
permits unauthorized use of the victim's printer/check stock and exposes native
parsers to another local user's input. There is no sender identity check.

When the worker is stopped, signed out, updating or in PDF mode while the virtual
queue remains installed, another ordinary Windows user can bind TCP 515 first.
The Windows LPR monitor has no server authentication and will send that listener
the victim's queued check data. `SO_EXCLUSIVEADDRUSE` protects an existing bind;
it does not reserve the port while the worker is absent. No elevation is required
to bind an otherwise available low-numbered port on Windows. This capture route
is more serious than simple unauthorized printing and survives a restrictive
printer ACL. No LAN/internet listener was found; remote access would require a
separate proxy, forwarding or host compromise.

**Reproduction:** the existing `test_real_socket_handshake` demonstrates admission
from a plain socket without credentials, using an ephemeral loopback port. For
native confirmation use two disposable Windows accounts: let account A run
virtual mode, and have B send the same fake RFC1179 exchange to port 515. Then stop
A's worker, bind a test LPR receiver as B, and send a **fake** voucher through A's
Windows queue. Verify that B receives the payload. The two-account capture was
not performed here. README acknowledges unauthenticated local clients; it does
not mitigate or prevent this attack.

**Recommended fix:** replace the raw per-user LPR listener with a supported,
authenticated spool handoff and an access-controlled local transport/broker.
Authenticate both producer and receiver; reserve ownership throughout the
printer's lifetime and fail closed when its receiver is unavailable. A random
port or queue name alone is not authentication. Until redesigned, prefer PDF
mode and remove the dormant virtual queue on shared/untrusted-user machines.

### SR-03 — High: elevated helper is loaded from user-writable installation

**Locations:** `packaging/installer.nsi:14`, `:45`, `:59`;
`packaging/request_printer.ps1:4`, `:6`, `:8`.

**Impact:** the requesting standard user can edit `packaging/printer.ps1` under
their own LocalAppData installation. The app then starts the system PowerShell
binary with `-Verb RunAs -ExecutionPolicy Bypass -File` pointing at that mutable
script. An administrator approving what appears to be printer provisioning
(including entering different administrator credentials) authorizes arbitrary
attacker-modified code under the administrator token. No protected helper,
publisher verification or integrity boundary binds approval to the intended
printer operations. This is **conditional on legitimate UAC approval**, not a
demonstrated UAC bypass or automatic escalation by a different account that
cannot write the installation.

**Reproduction:** on a disposable standard-user install, replace the helper's
body with a harmless command that writes the current token identity to a test
file and exits. Choose Enable virtual printer and approve with a separate admin
account. The requested elevated process will execute the edited script. Source
establishes the writable-script execution path; the native UAC demonstration is
outstanding and no privileged code was run during this review.

**Recommended fix:** provide a separately authenticated, narrow provisioning
helper whose executable and all code/dependencies are installed and protected by
an administrator. Do not solve this by checking a hash in another user-writable
script. Bind the approved operation to trusted bytes and validate its small input
surface. Harden the elevated process's working directory, module/DLL search
paths and environment as part of that design.

Also review `packaging/printer.ps1:27-33`: the Microsoft runtime download has a
useful Authenticode publisher check, but validation and execution reopen a file
in inherited `$env:TEMP`. Verify that directory's ACL and replacement behavior
under both same-user elevation and alternate credentials; use protected staging
through execution. A successful replacement race was not demonstrated here.

### SR-04 — Medium: malformed Inbox file starves the whole worker

**Locations:** `voucher_reorder/inbox.py:81`, `:85`, `:87`;
`voucher_reorder/worker.py:95`, `:97`, `:100`, `:111`.

**Impact:** `PdfReadError` is neither `ValueError` nor `OSError`. A complete-looking
but invalid PDF escapes `Inbox.scan`. Every following iteration retries it and
skips `process_one` and expiry. This blocks already queued manual/virtual jobs,
not just the malformed Inbox item. The generic heartbeat can remain fresh while
no work progresses.

**Reproduction:** `test_bad_inbox_pdf_does_not_block_valid_job` places
`%PDF-1.7\nnot a PDF\n%%EOF\n` before a valid fake PDF. The second stable scan
raises `PdfReadError: startxref not found`; the valid file is never admitted.

**Recommended fix:** convert expected parser failures into per-file sanitized
errors, continue scanning, and process the durable queue independently of Inbox
scan success. Record a rejected-file signature to avoid parsing it every second;
retry only after it changes or the user requests a retry. Resource isolation in
SR-01 is still needed for failures that never raise.

### SR-05 — Medium: failed Inbox receipt persistence enables duplicate printing

**Locations:** `voucher_reorder/inbox.py:73`, `:82-86`;
`voucher_reorder/queue.py:65`, `:92`.

**Impact:** admission commits first; then `self.seen` is updated before the
persistent receipt is written. If that write fails, `OSError` is silently treated
as an open input file. The in-memory receipt causes later scans to skip the file
instead of retrying persistence. Once the job/digest expires after 24 hours, a
restart admits the unchanged original again. A transient disk-full/replace error
can therefore produce an unsolicited second check print days later.

**Reproduction:** `test_inbox_retries_receipt_after_transient_disk_failure` injects
one receipt-write failure after successful queue admission; a healthy later scan
still does not persist it. `test_receipt_failure_does_not_reprint_original_after_retention`
marks the first job sent, expires its status, restarts the Inbox and demonstrates
that the same unchanged file is queued again. No physical printing is performed.

**Recommended fix:** make admission and persistent source receipt one recoverable
transaction, or store source identity with the durable job and reconcile receipts
before processing/expiry. Update in-memory acknowledged state only after durable
write success, retry failed persistence and show a distinct storage error. Merely
moving `self.seen` assignment leaves a crash window between queue and receipt
commit, so test restart recovery as well.

### SR-06 — Medium: hidden PDF layers become visible

**Locations:** `voucher_reorder/engine.py:24-25`, `:48`, `:54`, `:77`.

**Impact:** page resources referencing optional-content groups are cloned into
the fresh output, but document-level `/OCProperties` and their visibility
configuration are discarded. A valid input with a hidden layer can print that
layer, altering amounts/text or obscuring a check even with identity section
order. Such PDFs can come from third-party exporters; ordinary synthetic RGB
band tests do not cover them.

**Reproduction:** `test_identity_reorder_preserves_hidden_layer_appearance` creates
a Letter PDF with one hidden black layer. MuPDF renders the input pixel white
and the reordered output pixel black. The test uses `(0, 1, 2)` order and no
offsets, isolating this from section geometry.

**Recommended fix:** reject optional-content PDFs with a clear flatten/export
instruction until view/print usage and visibility can be preserved correctly.
If supporting them, preserve the required catalog and group relationships and
test print-intent rendering, nested groups and transparency. Do not blindly copy
all document-level actions into printable output.

### SR-07 — Medium: install locking starts after staging; cleanup deletes peers

**Locations:** `packaging/installer.nsi:40-48`;
`voucher_reorder/deployment.py:46-60`, `:76`, `:82`, `:116`.

**Impact:** two installer instances may extract into distinct `app-*` directories
before either takes `install.lock`. The first successful activation removes every
other marked deployment, including the second installer's staged directory.
On Windows open binaries may protect some files but not all scripts/libraries,
so failure can leave a partially deleted candidate. The lock does not cover the
operation it needs to serialize. Uninstall also lacks that install lock and
later recursively removes the deployment tree (`installer.nsi:79`), giving an
additional install/uninstall race to validate natively.

**Reproduction:** `test_install_does_not_delete_another_staged_candidate` creates
two valid staged packages and activates the first. The second one's manifest and
payload disappear. Reproduce the complete user-facing race in a VM by starting
two setups and pausing one after extraction; that native test remains outstanding.

**Recommended fix:** acquire a per-user installation mutex before extraction and
hold it through integration, uninstaller publication and cleanup; uninstall must
share it. Distinguish staging directories from retired activated deployments,
and delete only known retired deployments. Validate interruption and disk-full
rollback while retaining a runnable prior deployment.

### SR-09 — Medium: per-read timeout permits indefinite slow-client occupation

**Locations:** `voucher_reorder/lpr.py:12`, `:48`, `:73`, `:83`;
`voucher_reorder/worker.py:92`, `:119`.

**Impact:** the serial server has a 60-second socket timeout, but no total receipt
deadline or minimum throughput. A client sending occasional bytes faster than
the timeout can occupy the sole handler indefinitely. Other Windows print jobs
wait. `server.shutdown()` waits for that handler, so mode switching/shutdown can
hang and setup cannot acquire `worker.lock`. The existing 100 MiB/control-file
limits bound completed sizes, not elapsed time. Filling the waiting queue can
also consume roughly 9.8 GiB before conversion overhead; there is no aggregate
byte or free-space reserve.

**Reproduction:** in an isolated loopback test, complete the receive-job command,
declare a large data block, then send one byte every 30 seconds without completing
it. A second request will not be serviced, and a concurrent shutdown will remain
blocked. This follows the blocking `TCPServer`/socket timeout semantics; the
multi-minute trickle was not run during this review.

**Recommended fix:** enforce a monotonic deadline over the entire exchange,
bound receive/admission time separately, close active sockets on cancellation,
and budget total queued bytes/free disk space. Avoid unbounded handler threads
as the replacement. Test shutdown while a client is incomplete and while
admission waits for the queue lock.

### SR-10 — Medium: renderer success can conceal a dropped/blank page

**Locations:** `voucher_reorder/windows.py:79-92`;
`voucher_reorder/worker.py:32-34`; `packaging/dependencies.json:33`.
Pinned upstream source:
[`sumatrapdf-3.6.1rel/src/Print.cpp:474`](https://github.com/sumatrapdfreader/sumatrapdf/blob/3.6.1rel/src/Print.cpp#L474),
`:535-569`, `:577-583`, `:1324`.

**Impact:** SumatraPDF 3.6.1's `PrintToDevice` continues to the next page after a
failed `StartPage`. It also continues after all bitmap-render/blit retries fail
(the source contains `TODO: abort if !ok?`). If later `EndPage`/`EndDoc` calls
succeed, it returns success. The application interprets process success as
`sent` and deletes payloads. A batch may contain omitted or blank checks with no
app-level review state. This is distinct from a spooler accepting a job and a
physical printer subsequently failing, which the docs already explain.

**Reproduction:** inspect the hash-matched upstream archive at those branches.
For native proof, inject a `StartPage` failure on the second page, or force
render/blit failure while `EndPage`/`EndDoc` succeed, using only fake pages. Check
renderer exit status, app status and resulting spool page count. No native GDI
fault injection was performed, so the end-to-end behavior remains to be verified.

**Recommended fix:** use a renderer/version that propagates every page-generation
failure; verify upstream behavior rather than depending solely on a zero exit
code. Capture a job identifier and page submission result where possible. Any
uncertain partial batch must enter review and must never auto-retry. Test large
pages and memory pressure; renderer downsampling also needs MICR/plain-paper
acceptance even though the intermediate PDF remains vector.

### SR-08 — Low: terminal-state crash recovery leaves sensitive payload copies

**Locations:** `voucher_reorder/queue.py:27-39`, `:50-56`.

**Impact:** state is committed before input/output files are deleted. A crash or
locked-file error between those steps leaves full financial documents attached
to a terminal job. Startup only cleans `converting`/`printing` states, so it does
not finish deletion for `sent`, `failed`, `review` or `discarded`. Copies can
remain until retention cleanup, or longer while the app is stopped/blocked.
This weakens prompt-deletion behavior; it does not itself bypass profile ACLs or
establish cross-user disclosure, hence Low severity.

**Reproduction:** the four cases of
`test_recovery_removes_payload_left_after_terminal_state_commit` model power loss
after state commit. A new recovery-enabled Queue leaves `input.pdf` behind.

**Recommended fix:** make terminal-state cleanup idempotent, run it at startup
and periodically, and report deferred deletion without changing a sent job back
to a retryable state. Include antivirus/file-lock failures. Keep the documented
distinction between ordinary deletion and secure erasure.

### SR-11 — Low: build/release supply chain is not fully pinned

**Locations:** `.github/workflows/build.yml:20-25`, `:34-39`, `:68`, `:82`;
`pyproject.toml:2`; `requirements-dev.txt:1`; `scripts/build_windows.py:101`, `:165`.

**Impact:** application downloads are hash-checked, but Actions use mutable major
tags, build setuptools has an open lower bound, development transitive packages
are unlocked/unhashed, and host-provided 7-Zip/NSIS/toolchains are outside that
manifest. The download-artifact Action runs in the release job with
`contents: write`. A compromised/moved dependency or action could affect build
outputs/release assets. No compromise or untrusted-PR write-token exposure was
found; this is a hardening gap, not evidence that pins are malicious.

**Reproduction:** inspect the workflow refs and install commands. Compare builds
on different runner/tool updates despite unchanged runtime hashes. A dependency
substitution attack was not performed.

**Recommended fix:** pin Actions to reviewed full commit SHAs, lock/hash build
dependencies including transitives, record compiler/extractor versions, automate
reviewed updates and vulnerability checks, and protect the release environment.
Use authenticated release attestations/signing where practical. Runtime hashes
prove expected bytes only after the manifest itself is trusted; keep corresponding
sources/notices alongside the binary as the current build already does.

## Other checks, accepted limitations and remaining acceptance work

| Area | Result and practical limit |
| --- | --- |
| HTTP/IPC reachability | No HTTP listener, web UI, service or named-pipe endpoint was found. LPR binds only `127.0.0.1`; PDF mode opens no listener. Local state/lock files rely on the user's filesystem permissions. SR-02/SR-09 cover LPR risks. |
| Paths and temporary files | LPR filenames/control metadata are ignored as paths; random `mkstemp` files live under the user's spool directory and are removed in `finally`. JSON uses replace and fsync; job payloads are flushed before admission. Normal CLI PDF reads reject symlinks and use an exclusive Windows handle. Deployment names/identity are validated before activation. |
| ACLs and reparse points | No broad grants to other desktop users appear in the app. Windows profile ACLs are assumed; POSIX modes alone do not prove Windows privacy. `is_symlink()` is not a complete junction/reparse/TOCTOU defense and uninstall recursively deletes the deployment tree. Validate actual handle targets and ACLs on native Windows, including redirected profiles. Same-user path tampering alone is not claimed as escalation; elevated execution is separately covered in SR-03. |
| DLL/executable search | Bundled Ghostscript/Sumatra and system PowerShell use explicit executable paths; subprocess arguments are lists without a shell. Embedded Python's `_pth` restricts import paths. No verified DLL hijack was demonstrated. Absolute executable paths do not prove safe DLL search: inspect missing DLL loads with Process Monitor from an attacker-controlled CWD and test elevated module/temp paths, especially the runtime installer in SR-03. Per-user binary replacement is already same-user code execution. |
| PDF/PS behavior | Encrypted input, annotations and nonstandard UserUnit are rejected. Output uses a new document catalog and does not deliberately carry document JavaScript/launch actions. Ghostscript runs with `-dSAFER` and a 120-second subprocess timeout, but full user-token native parsing is not an OS sandbox. Fonts/images/resources still reach native renderers. SR-01/SR-06 remain. |
| Logging/privacy | No persistent application financial-content log was found; worker status substitutes generic errors and subprocess output is mostly discarded. Sumatra preferences disable recent-file/document state for a fresh profile. `inbox-receipts.json` stores original filenames, which users may make sensitive. Direct console invocation can emit raw chained parser tracebacks, and upstream warnings are not centrally sanitized. Do not collect CLI stderr, crash dumps or filenames as public diagnostics without redaction. SR-08 addresses extra retained copies. |
| Queue delivery/recovery | Immutable settings snapshots, durable admission before LPR ACK, serialized processing, and non-retryable uncertain print states are useful controls. Exact-byte deduplication intentionally rejects deliberate identical reprints; metadata changes evade it. This is not semantic duplicate-check detection. A lost ACK can cause retransmission; digest retention reduces, not eliminates, that risk. SR-05 finds an avoidable duplicate path. |
| Queue expiry/data loss policy | `queue.py:92-95` deletes every old state, including queued/held jobs, rather than retaining an `expired` tombstone. Reinstall after more than 24 hours can erase jobs held during uninstall; Inbox receipts prevent automatic re-admission. This is documented retention behavior, not a newly undisclosed bug. Confirm that losing unprinted jobs/status is acceptable; prefer visible expired/canceled records and explicit reconciliation before erasure. |
| Corrupt local state | Malformed receipt JSON fails before the worker's main try/finally (`inbox.py:62`, `worker.py:72`); a corrupt job state can block recovery. Atomic writes reduce routine torn writes, but backup restores/disk corruption still need quarantine and actionable diagnostics rather than a startup loop. No new cross-user attack is claimed. |
| Upgrade/uninstall | Existing rollback, downgrade refusal, held-job and busy-worker tests pass. No elevated application service exists; HKCU integration is appropriate. SR-07 needs serialization repair. Test crashes between JSON/INI/registry/uninstaller publication, native file locks and failed rollback. Silent uninstall intentionally skips optional machine-printer removal; the remaining queue and unsigned setup remain operational concerns. |
| Section geometry/scaling | Existing tests cover all six orders, multiple/odd sizes, unequal sections, offsets, clipping, rotation/nonzero origins and multipage preservation. The known Sumatra options `noscale`, `simplex`, `1x`, `paperkind`, `bin` and `disable-auto-rotation` exist in the pinned source; its no-scale path anchors to the physical page origin. Paper/tray/orientation checks are useful. SR-06/SR-10 identify gaps beyond those tests. |
| Windows/printer compatibility | Win10/11 x64, alternate-admin UAC, Protected Print Mode/enterprise policies, availability of MS Publisher Imagesetter, shared/network/Unicode printers, non-Letter driver sizes, margins, feed direction, font/MICR quality and actual QuickBooks output remain hardware acceptance tasks. Linux Ghostscript success is not proof of the bundled Windows executable. ARM64 is already unqualified. Follow `TESTING_ON_WINDOWS.md` on plain paper. |
| CI authorization/secrets | PR builds use `pull_request`, not `pull_request_target`; global token scope is read-only, and write access is limited to a tag-push release job. The tag value is passed via an environment variable and quoted in shell. No committed credential was identified in the reviewed application/workflow files. Test-account passwords are generated at runtime. A compromised runner/action is still relevant to SR-11. |

Prioritize bounded parser execution and dependency updates first, then secure the
optional elevated/network boundaries. Queue receipt transactions and preserving
PDF appearance need dedicated fixes and regression promotion; they are not
addressed by merely documenting the existing print-reconciliation procedure.
