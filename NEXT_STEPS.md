# Next steps for Matthew

## Done in this round

- A per-user x64 app for Windows 10/11, with HKCU startup/uninstall entries and no
  service. Optional virtual-printer setup is offered through UAC by default;
  cancellation, missing credentials or setup failure automatically selects PDF mode.
- Both modes share the vector reorder engine, settings and durable queue. Settings
  shows the active mode and supports switching later. PDF handoff uses a dedicated
  Inbox or manual PDF selection; closed, complete PDFs are received without moving
  or deleting originals. Persistent receipts prevent repeat printing after restart.
- All installed user-accessible printers are listed, with driver-reported paper
  sizes/trays/margins. Actual-size forwarding rejects mismatched sheets and requests
  one copy/simplex without fitting or automatic rotation. Offsets remain configurable.
- In-place per-user upgrades with stable identity, isolated payloads, graceful stop,
  immutable job settings, held waiting jobs, downgrade refusal, same-version repair,
  activation rollback and cleanup of old owned deployments. Settings/mode survive.
- Tests for both input paths, mode fallback, PDF readiness/duplicates, multiple paper
  sizes, update preservation/rollback/busy-worker behavior. CI adds native Windows
  standard-user install/upgrade/downgrade/repair/uninstall and UI construction checks.
- Public user guide, maintainer/build docs, complete third-party notices and matching
  source artifacts; GPL-3.0-or-later remains unchanged. No tag/release/merge is created.

## Still needs real Windows/QuickBooks/printer acceptance

The CI Windows host is not a Windows 10/11 office PC with QuickBooks and a physical
printer. Virtual-printer provisioning is covered with mocked Windows printer APIs;
its actual inbox-driver availability/UAC/spooler behavior must pass the hardware
checklist. Do not call the tool hardware-qualified or bank/MICR-certified yet.

1. Record Windows edition/build, QuickBooks year/edition/release, physical printer
   model/driver/connection/tray, and stock order/section heights.
2. On Win10 x64 and Win11 x64, install as a **standard user**. Decline UAC; confirm
   PDF mode works, no driver/port/service is added, and no repeated elevation occurs.
3. Select the real printer/paper/tray; print alignment on plain paper. Measure its
   ruler, edges and nudges. Test Letter and the actual non-Letter size if applicable.
4. Print a fake QuickBooks check through Print to PDF → Inbox, then test manual PDF
   selection. Check slow saves, restart, duplicate files and queue status. Originals
   must remain unchanged, and old Inbox files must not print again after restart.
5. Enable the virtual printer, including with **different administrator credentials**
   if used by the office. Print a fake QuickBooks check directly to Voucher Reorder.
   Confirm no Save dialog and the background app remains unelevated. Test UAC refusal,
   missing driver/policy restrictions, port conflict and switching back to PDF mode.
6. Print one real QuickBooks check to **plain paper only**, under the office's normal
   test/reprint bookkeeping rules. Overlay on stock; inspect all fields and MICR.
   Keep the real sheet private. Obtain approval before loading live stock.
7. In each mode, print fake multipage batches and consecutive jobs. Test offline and
   out-of-paper behavior. Check both queues and physical output before reprinting.
8. Upgrade while idle, with Settings open, with waiting jobs and during a fake print.
   Verify settings/mode persist, waiting jobs are held, the current job finishes or
   setup aborts safely, old files are cleaned, and no uncertain job auto-retries.
9. Try same-version repair, a downgrade and interrupted setup. Rerun setup to recover.
   Reboot and verify startup/shortcuts use only the active deployment. Check uninstall
   with UAC approved and declined, including settings/Inbox retention and reinstall.
10. Send checkbox results, redacted errors, versions, fake-page measurements/photos
    and queue observations. Never upload financial data, real PDFs or spool files.

The detailed scenarios and expected results are in TESTING_ON_WINDOWS.md.

## Questions still open for Matthew

- Which QuickBooks Desktop year, edition and release?
- Which physical printer make/model, driver, connection and paper tray?
- What is the stock's top/middle/bottom order and each measured section height?
- Are standard accounts, alternate admin credentials, organizational print policies,
  multiple users or ARM64 machines part of the intended audience?

## Remaining admin requirements and limitations

- **PDF mode app install/use/upgrade/uninstall needs no admin.** An absent Windows PDF
  feature, absent physical-printer driver or restrictive organization policy may
  still need IT action. An existing PDF exporter is a valid alternative.
- Optional creation/removal of the machine virtual printer needs admin. Its shared
  C++ runtime may need installation/download. Declining removal leaves that printer
  installed but dormant. The application itself remains per-user and unelevated.
- The earlier 0.1 prototype installed in Program Files and wrote a machine uninstall
  entry. A standard user cannot clean those machine resources. Back up profile data,
  have an administrator remove 0.1, then restore settings before using 0.2. Do not
  leave both background apps running. Seamless in-place upgrades apply to the new
  per-user 0.2+ architecture, in either mode; the prototype migration is an exception.
- PDF mode necessarily exposes one PDF Save/select step. Inbox originals are not
  automatically deleted. Private queued payloads/status expire after 24 hours only
  while the app runs/at restart; ordinary deletion is not secure erase.
- Identical job bytes within 24 hours are suppressed. There is no exactly-once
  guarantee across Windows and a physical printer. Uncertain attempts require human
  reconciliation; only unattempted held jobs can be resumed.
- Virtual mode's one machine queue/loopback port serves one signed-in user. Its LPR
  endpoint is unauthenticated to local processes. PDF mode supports separate users
  without a listening port. No unattended printing while signed out is promised.
- Hardware margins, paper feed/tray rules, driver overrides and MICR quality vary.
  Vectors are preserved in the engine; downstream printer rendering may rasterize.
- Locked old payload files are retained safely and retried for cleanup at a later
  successful install. Uninstall preserves user data intentionally. A hard crash or
  disk failure during activation may require rerunning the installer.
- Windows x64 is supported; native ARM64 and x64-on-ARM behavior are unqualified.
  Setup is unsigned, so SmartScreen may show a warning. Enterprise script/application
  controls can block the included UI or binaries; the app never bypasses site policy.

## Recommended next Codex rounds

1. **Run the hardware matrix first:** fix findings from both input modes, true UAC,
   alternate credentials, Win10/11 and physical printer tests before tagging a release.
2. **Printer calibration:** add only fake regression fixtures for observed layout,
   margin, tray, Unicode printer-name and font issues; validate actual-size/MICR output.
3. **Deployment hardening:** simulate power/disk failures, antivirus file locks,
   standard-user profiles/redirected folders and prototype migration; qualify ARM64
   only if demand justifies a separate runtime/driver compatibility matrix.
4. **Public release gate:** review dependency/source notices and security updates,
   optional signing and the completed Windows checklist, then let Matthew approve a
   release tag. Codex must not create a tag or merge this PR in this round.
