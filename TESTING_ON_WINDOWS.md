# Windows acceptance checklist

Status: automated Linux tests and packaging are not proof of hardware correctness.
Run this checklist on Windows 10 x64 and Windows 11 x64, with the actual QuickBooks
Desktop version and physical printer. Use a test company/fake transaction wherever
possible. Keep any live QuickBooks check locally; never upload it to GitHub.

## Record the environment

- [ ] Windows edition/build (`winver`), x64, and whether Protected Print Mode or
      organization policy restricts legacy drivers.
- [ ] QuickBooks Desktop year/edition/release (F2/Product Information).
- [ ] Printer make/model, driver name/version, USB/network connection and tray.
- [ ] Physical stock's top/middle/bottom order and measured section heights.
- [ ] Artifact SHA-256, commit in installed `BUILD_INFO.json`, install date.

## Install and first run

1. [ ] Sign into the same administrator account that will run QuickBooks. Do not
       supply credentials for a different administrator. Close QuickBooks.
2. [ ] Download the installer and accompanying source/checksums from the same build.
       Verify the installer hash. Run it; record any SmartScreen/UAC messages.
3. [ ] On a clean machine lacking the C++ runtime, confirm setup obtains Microsoft's
       signed prerequisite automatically. With internet unavailable, confirm a
       clear failure rather than a partially working app.
4. [ ] Verify **Voucher Reorder** appears in Windows printers, uses **MS Publisher
       Imagesetter**, Letter, simplex, and the `VoucherReorder_LPR` LPR port pointing
       at `127.0.0.1`, queue `voucher`, byte counting enabled. Default printer should
       be unchanged. Verify port binding is loopback only, not `0.0.0.0`.
5. [ ] Settings opens without a console/PDF dialog. Choose the real printer and stock
       order. Confirm all six selections match the diagram. Save and reopen; values
       persist. Negative/positive nudges, decimal input and invalid values behave.
6. [ ] Verify the background `pythonw.exe` belonging to this app is **not elevated**
       (Task Manager's Elevated column), including immediately after installer launch.
7. [ ] Sign out/in and reboot. Verify the worker starts automatically and Settings →
       Job status reports it running. Keep the same account signed in while printing.

## Alignment and actual print path

8. [ ] Load plain Letter paper, disable driver scaling/duplex, set the intended tray.
       Print alignment from Settings. Exactly one sheet emerges with all three labels.
9. [ ] Measure the ruler over several inches; no fit-to-page shrinkage is acceptable.
       Compare frame/edges to measured stock. Set X/Y by 0.02 inch and verify direction
       and distance for each source section. Verify clipping never overlaps a neighbor.
10. [ ] Exercise all six orders on plain paper. Test default equal thirds and measured
        3.5/7 boundaries if applicable; unequal sections must retain their heights.
11. [ ] **Exercise the virtual printer**, which the Settings alignment button bypasses:
        open QuickBooks, select voucher checks and Voucher Reorder, Letter portrait,
        one copy. First use a clearly fake test-company check on plain paper. Confirm
        no file-save/PDF/script UI appears and the job forwards automatically.
12. [ ] Print a real QuickBooks check **to plain paper only**, following the office's
        bookkeeping rules for test/reprint status. Hold it against unused stock in
        bright light. Verify every field, both stubs, amount, check number and MICR
        line fit. Keep this sheet/data private. This is the go/no-go gate for stock.
13. [ ] Print a three-page fake batch and two consecutive fake jobs. Verify exact page
        count, original page order, no extra blank pages and no swapped/duplicated
        checks. Check copy-count behavior; production support is one copy.
14. [ ] Inspect small text/MICR visually under magnification and have the office's
        responsible person confirm its normal banking/MICR requirements. The app
        does not supply MICR fonts, magnetic toner, or bank acceptance certification.

## Failure cases, isolation, and uninstall

15. [ ] Turn the real printer offline, send a fake job, then restore it. Identify which
        queue owns it; confirm the app does not create a duplicate. Out-of-paper jobs
        may remain in Windows after the app reports “sent.”
16. [ ] Stop the app during fake conversion/forwarding, restart Settings, inspect status.
        Interrupted in-flight jobs must show review and must not print automatically.
        Inspect paper and both queues before any manual reprint.
17. [ ] Send an exact duplicate fake spool job in a controlled test; expect suppression
        within 24 hours. Test canceled waiting jobs and stale-job expiry; no automatic
        retry button should bypass duplicate-check precautions.
18. [ ] Verify `%LOCALAPPDATA%\VoucherReorder` has user-private inherited ACLs. Successful
        job directories retain only state/digest, no PS/PDF. Verify no raw print data
        appears in logs. Another account must not be able to print to this queue.
19. [ ] On separate clean test snapshots, test port-515 conflict, missing driver, and
        restrictive print policy. Setup must fail visibly without deleting existing
        unrelated queues/ports or disabling security. No custom driver should appear.
20. [ ] Cancel pending jobs in both Windows queues. Close QuickBooks and Settings.
        Uninstall from the installing account. Verify the virtual printer/port,
        Program Files directory, Start shortcuts, Run entry and app data are gone.
        Other printers, default printer and shared Microsoft components must remain.
21. [ ] Reboot, confirm no worker returns, then reinstall and repeat one fake print.

## Send back

Send checkbox results, environment details above, exact error dialog text (redact
usernames), fake-page ruler measurements in inches, expected/actual section order,
and timing/queue observations. Fake alignment-page photos are useful. **Do not send
real checks, bank/routing/account numbers, payee names, settings JSON, PS/PDF spool
files, or unredacted screenshots to this public repository.**
