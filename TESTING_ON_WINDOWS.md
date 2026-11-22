# Windows acceptance checklist — both modes and upgrades

Use Windows 10 x64 and Windows 11 x64, QuickBooks Desktop, and the intended physical
printer. CI covers synthetic tests, not this hardware acceptance. Keep live financial
data local; use fake transactions except for the explicit private overlay test.

Force a page-render or GDI page failure partway through a synthetic batch. Verify
that the job enters review, no later pages print, and restart never resubmits it.
Exercise memory/time limits and check that the next ordinary job completes.

## Record

- [ ] Windows edition/build, x64, security/Protected Print Mode or organizational policy.
- [ ] QuickBooks Desktop year/edition/release (F2); printer make/model/driver/version,
      USB/network/shared connection, paper/tray; stock section order and measured heights.
- [ ] Installer version/checksum, installed BUILD_INFO.json revision, standard/admin
      account used (report role, not username), and whether PDF output already exists.

## v0.2.2 output, reprint, errors and idle cursor regressions

- [ ] Generate the alignment sheet, save its reordered PDF, and record both byte
      sizes. Direct output should be well below twice the input. Repeat through
      the Voucher Reorder printer and record the PostScript-converted PDF size;
      Windows drivers can turn text into larger vector outlines.
- [ ] Submit the saved output directly, then print it from Edge and Acrobat through
      Voucher Reorder. Repeat with Microsoft Print to PDF output. All should pass
      vector validation; set source section order to the saved document's order.
- [ ] A scanned/image-only PDF must show the explicit unsupported-scanned-PDF
      explanation in Job status. A 251-page PDF must name the 250-page limit.
      Test a blank PDF and a real recursive/deep Form PDF; both remain rejected.
- [ ] Leave the virtual worker idle for five minutes with Settings open and closed.
      No recurring Python/PowerShell children or app-starting mouse cursor. Submit
      a job, check its output, and confirm it returns to quiet idle operation.
- [ ] Compare embedded MICR font appearance/spacing on plain paper. The optimizer
      compresses streams and shares identical objects; it does not substitute,
      subset or re-encode font programs.

Portable measurements (same 5,916-byte generated alignment input): v0.2.1 direct
output 5,169 bytes; v0.2.2 direct output 2,038 bytes. A Poppler PostScript/Ghostscript
round trip produced an 8,762-byte input PDF: reorder output fell from 11,878 to
7,890 bytes. These are reproducible synthetic measurements, not a measurement of
Matthew's unavailable approximately 370 KB output file. Windows CI logs separate
native Microsoft PDF and MS Publisher Imagesetter round-trip measurements.

## v0.2.1 feedback regressions (include a PC with no physical printer)

- [ ] At Windows scaling 100%, 150% and 200%, select Stub 1 / Check / Stub 2 output.
      All three bands have readable labels, including the complete top Stub 1 band.
      Resize to a small window; scroll to every setting and button. Switch tabs and
      orders; no band overlaps a selector or another band. Repeat after reopening.
- [ ] Both source and output selectors offer all six orders. Check each of the 36
      mappings using fake alignment pages, equal thirds, unequal source heights
      (e.g. 2.75 / 4.25 / 4 inches), and positive/negative X/Y nudges. Each named
      section keeps its height and nudge; nothing bleeds into another slot.
- [ ] The QuickBooks version and printer model fields are absent. Section-height
      help explains blank defaults and distances from the source page's top.
- [ ] Click Enable virtual printer: immediate progress text, moving indicator and
      disabled mode buttons; the window can repaint, move and switch tabs throughout.
      Exactly one UAC prompt. Test approval, decline and setup failure; each produces
      a clear result and re-enables buttons. PDF handoff still works on failure.
- [ ] With no physical printer, choose Save reordered PDF, Letter and a new output
      folder. Save settings, run an alignment test, submit a fake PDF manually and
      save a fresh fake QuickBooks PDF into the Inbox. Each produces a vector PDF
      in that folder; Job status reports its path. Test consecutive ten-page jobs.
- [ ] Select Microsoft Print to PDF, then Microsoft XPS Document Writer if present:
      settings save successfully and use direct PDF output in the chosen folder.
      Voucher Reorder as output is always refused. No second output Save dialog.
- [ ] Reject an output folder equal to or below the Inbox (including a folder alias).
      Copy generated output back into the Inbox: it is accepted once. Restart the app
      and verify it is not processed again. Existing source files are not reprocessed. Reject
      scanned/image PDFs and blank pages; confirm saved test text remains searchable.
- [ ] Upgrade an actual 0.2.0 installation with nondefault layout/nudges and held
      jobs to 0.2.2 without uninstalling. Load/save Settings and resume a held fake
      job: default source order and old output/nudges preserved; obsolete fields
      disappear on save. No additional UAC for the per-user update.

## No-admin path (must pass independently)

1. [ ] Sign in as a standard user, run the per-user setup normally.
       Installation completes in LocalAppData. Settings clearly says **PDF handoff**.
       No Program Files/HKLM app installation, service, driver or printer port is added.
2. [ ] Reopen from Start and sign out/in. Background app starts unelevated with no UAC.
       A second account has separate settings/Inbox/queue. Verify app data ACL privacy.
3. [ ] Enumerate all installed printers, including USB/network/shared/Unicode names.
       Select the physical printer, a supported paper size and tray. Confirm reported
       margins. Disconnect it, refresh and restore; errors must not silently select
       another printer or the Windows default printer.
4. [ ] On plain paper, print alignment. Measure several ruler inches: no fit/shrink.
       Test all 36 source/output orders, positive/negative X/Y, equal thirds and measured unequal
       splits. Check that nudges cannot leak into neighboring sections.
5. [ ] Test Letter, Legal/A4 or a driver-specific size actually supported by this printer.
       Match QuickBooks/PDF page size to paper. Deliberately mismatch them: no sheet
       should be forwarded. Test changed/removed tray and landscape defaults: clear
       status error, no silent scaling/rotation. Verify driver-specific defaults too.
6. [ ] From QuickBooks, print a fake voucher through existing Print to PDF into the app
       Inbox under a new name. A Save dialog is expected; after saving, forwarding is
       automatic. Test manual **Print a PDF** from another folder as well.
7. [ ] Simulate a slow/open/partially written PDF; nothing should print until it closes
       and parses completely. Test invalid/encrypted/oversized input and duplicate
       identical files. Restart/reboot: old Inbox PDFs must not print again. Confirm
       originals are unchanged and remain for explicit user cleanup.
8. [ ] If Print to PDF is absent, confirm the app does not request elevation to enable
       it automatically. Use an existing PDF exporter or report the prerequisite to IT.

## Optional virtual path (must pass before promoting it)

9. [ ] Select the optional Virtual printer component in the main installer. Confirm
       exactly one UAC prompt installs the embedded package AND configures the queue.
       Repeat via Enable virtual printer in Settings. Also test a standard desktop user with
       different administrator credentials. Queue access must go to the original user.
       The app remains in LocalAppData and its worker remains unelevated.
10. [ ] Verify queue **Voucher Reorder**, Microsoft **MS Publisher Imagesetter** driver,
        Letter default/simplex, local NUL: port, unshared queue, RAW spooling and retained jobs.
        Stop the worker and submit a synthetic voucher. From another standard account
        verify that submitting, reading and deleting jobs are denied. Restart as owner:
        verify one durable admission, removal from the Windows queue and a single output.
        Windows default printer stays unchanged. Settings shows Virtual printer mode.
11. [ ] Print a fake QuickBooks voucher to Voucher Reorder, portrait/matching paper/one
        copy. No PDF Save/script/viewer UI should appear. Verify physical placement.
12. [ ] On separate snapshots, test UAC decline, unavailable credentials, missing inbox
        driver, printer policy, mismatched provisioning version/hash and missing C++ runtime/offline setup.
        Failure must leave a working PDF mode without modifying unrelated queues.
13. [ ] Switch back to PDF mode; approve removal, then repeat with removal declined.
        On decline, PDF mode still works and the remaining virtual queue is documented
        as dormant. No queued Windows jobs should be silently duplicated or lost.

## Physical acceptance and failure recovery — repeat in both modes

14. [ ] Print one real QuickBooks check **to plain paper only**, following the office's
        test/reprint accounting procedure. Overlay against unused stock under light.
        Check payee, amount, check number, both stubs and MICR. Keep the sheet private.
        Obtain the responsible person's approval before loading actual check stock.
15. [ ] Print a fake three-page batch and two consecutive jobs; count sheets and verify
        page order. Confirm one-sided/one-copy behavior and correct tray/feed direction.
16. [ ] Test offline/out-of-paper and recovery. “Sent” can still be waiting in Windows.
        Inspect both Windows queues and physical sheets before reprinting anything.
17. [ ] Interrupt the app during a fake print, then restart. Uncertain attempts show
        review and never auto-retry. Cancel waiting jobs; confirm already submitted
        jobs must be canceled in the actual printer queue separately.
18. [ ] Check private queue PS/PDF deletion after completion/failure, 24-hour expiry,
        persistent Inbox receipts, and untouched originals. No raw financial contents
        should appear in app status/logs. Windows spooling/backup retention is separate.

## Upgrade matrix — run separately for PDF and Virtual mode

19. [ ] Install version A; set a nondefault printer/order/paper/tray/nudges. Upgrade to B
        without uninstalling. Printer/layout settings survive; no UAC is needed
        for the per-user app update. If provisioning versions differ, expect PDF mode
        and a clear message; selecting the optional component updates it with one UAC. Reopening/Run entry targets only B's deployment.
20. [ ] Upgrade with Settings open: it closes gracefully. Upgrade with waiting jobs:
        jobs become held, with original printer/layout snapshots and payloads intact.
        After checking stock, Resume held jobs prints each unattempted job once.
21. [ ] Upgrade during a fake in-flight print. Setup waits for safe completion or aborts
        without forcing/killing the print. Reconcile output if interrupted. No uncertain
        job can be resumed automatically or by Resume held jobs.
22. [ ] Reinstall B (repair), then attempt A (downgrade). Repair works; downgrade fails
        without changing active B, settings or jobs. Inspect old-deployment cleanup.
23. [ ] Kill setup before activation and after activation on disposable snapshots.
        Rerunning setup must recover. Test disk-full and files locked by security
        software: old usable version/settings are preserved where rollback is possible;
        never delete an unknown folder. Retained old payloads must be cleaned later.
24. [ ] Confirm unrelated or obsolete printer queues do not block the per-user app's
        update/uninstall. No port-515 migration is required or provided.

## Uninstall, reinstall and report

25. [ ] Cancel Windows queue jobs. Uninstall as the ordinary user. Test optional printer
        removal with UAC allowed and declined. Per-user binaries, shortcuts, Run entry
        and HKCU Apps entry disappear. Other printers/defaults and shared runtimes stay.
26. [ ] Settings, Inbox originals and held jobs are intentionally retained. Reinstall
        and confirm settings persist and old held jobs do not resume without action.
        After reconciliation, delete the profile folder to test a completely fresh start.
27. [ ] Reboot after uninstall; no worker returns. Test high DPI and a small screen;
        both tabs/buttons should remain accessible by scrolling/resizing.

Send checkbox results, versions/models, redacted dialog text, fake-page ruler
measurements/photos and queue observations. **Never send real check PDFs, bank or
routing/account numbers, payee names, spool files, settings JSON or unredacted
screenshots to this public repository.**

## Automated Windows regression coverage

CI requires the PDF file-port driver (absence fails), prints six consecutive ten-page vector
jobs, checks page count, Letter dimensions, visible vector content, sequential page
markers and no image XObjects. It measures Windows Job peaks below 256 MiB per job
with less than 32 MiB variation, worker private memory variation below 16 MiB after
garbage collection, payload/compiler-temp cleanup and empty waiting/spool queues. Vector preflight rejects raster
fallback and blank pages before StartDoc; test unsupported real exports separately.
CI exercises the native settings form with all 36 preview mappings, simulated
100/150/200% scaling, normal/small windows, printer-free PDF saving and event-loop
responsiveness during a simulated setup child. Actual Windows display scaling and
interactive UAC still need the checks above. Linux tests cover all 36 vector PDF
mappings with unequal heights/nudges, migration, file output and Inbox loop guards.
CI also exercises the real provisioning package install/upgrade/uninstall and version
mismatch rejection, followed by a real standard-user install/upgrade/repair/uninstall from the pinned
v0.2.0 baseline to v0.2.2, including settings and held-job snapshot migration.
Interactive UAC with alternate credentials and physical MICR remain manual acceptance.
Inspect only the sanitized `print-error.log` when diagnosing code 6/7/8 failures.
