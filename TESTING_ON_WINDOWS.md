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
       Test all six orders, positive/negative X/Y, equal thirds and measured unequal
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
24. [ ] If migrating the old administrator-only 0.1 prototype, back up the profile folder
        and supervise admin cleanup first. Its uninstaller deletes profile data. Restore
        settings, reconcile old jobs, and ensure the old worker does not remain running.

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

CI requires the PDF file-port driver (absence fails), prints 52 synthetic vector
pages, checks page count, Letter dimensions, ink on every page and no image XObjects,
and records Windows Job peak memory below 600 MiB. Vector preflight rejects raster
fallback and blank pages before StartDoc; test unsupported real exports separately.
CI also exercises the real provisioning package install/upgrade/uninstall and version
mismatch rejection, followed by a real standard-user install/upgrade/repair/uninstall.
Interactive UAC with alternate credentials and physical MICR remain manual acceptance.
Inspect only the sanitized `print-error.log` when diagnosing code 6/7/8 failures.
