# Independent security and quality review

The original review covered `codex/initial-build` at `efec173`. The status table
records the remediation on `codex/security-fixes` and the Windows follow-up on
`codex/security-fixes-2`. The evidence, reproductions
and recommendations below the table describe the reviewed version.

The Windows follow-up diagnosed the original CI failure using bounded, sanitized
stderr capture: `OutOfMemoryException` in the 600-DPI bitmap allocation. That path
has been replaced with pinned PDFium vector EMF/GDI printing, with preflight refusal
of bitmap fallback and blank pages. Printing deadlines scale with page count. CI
now requires a 52-page, nonblank, image-free file-port output and a measured Windows
Job peak below 600 MiB (the process-tree cap stays 768 MiB).

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
| SR-01 | High | Mitigated | pypdf 7.1.1 with matching wheel/source hashes. Separate processes bound time, memory and page count. PDF output writes are capped before extending files. Windows CI measures peak process-tree memory on a 52-page vector batch; timeout and error-log regressions are covered. |
| SR-02 | High | Mitigated | Owner-restricted, unshared Windows spool queue retains RAW jobs on a local NUL: port. No legacy port-515 queue was deployed; it no longer blocks per-user update/uninstall. Two-account access and offline handoff need native validation. |
| SR-03 | High | Mitigated; bundled provisioning | Main setup embeds the version-matched admin package; one optional elevation installs/configures its protected native launcher/scripts. Separate package uninstall is supplied. Runtime staging and execution use the protected directory. Alternate-credential UAC and installer provenance require native acceptance and trusted distribution. |
| SR-04 | Medium | Fixed | A rejected file signature suppresses repeated parsing. An Inbox error allows other files and queued jobs to proceed. |
| SR-05 | Medium | Fixed | Admission journals the pending source receipt in durable job state. Receipt reconciliation precedes printing and expiry. |
| SR-06 | Medium | Fixed | Layered PDFs with optional-content catalog configuration are rejected with a flattening instruction. |
| SR-07 | Medium | Mitigated | Install and uninstall share an exclusive per-user handle before extraction. Cleanup targets retired activations. Uninstaller publication is staged. Native concurrent and disk-full tests remain pending. |
| SR-09 | Medium | Mitigated | Removed the production LPR server. Bounded, cancellable spool reads quarantine interrupted jobs. Private admission reserves disk space and caps aggregate input. Windows controls its own spool storage. |
| SR-10 | Medium | Mitigated; vector path | Replaced raster printing with pinned PDFium vector EMF and checked GDI calls; all pages preflight before StartDoc, raster fallback/blank pages fail closed, and CI verifies 52 vector output pages. Uncertain attempts enter review. Native failure injection, printer compatibility and MICR checks remain pending. |
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
