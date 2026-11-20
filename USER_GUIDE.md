# Voucher Reorder — quick user guide

**Start with plain Letter paper, not check stock.** This first version needs a
plain-paper test on your computer before you use it for checks.

1. **Install.** Sign into the Windows administrator account you use for QuickBooks.
   Close QuickBooks. Run `VoucherReorder-0.1.0-Setup.exe` and allow installation.
   If Windows SmartScreen appears, choose **More info → Run anyway** after checking
   that the file came from this project's download. Setup may need internet to
   install a Microsoft runtime. Leave **Open Voucher Reorder Settings** selected.
   If setup reports that the printer driver is unavailable, ask your installer for
   help; do not change Windows security settings yourself.
2. **Choose your printer.** In Settings, select the real printer that holds your
   paper. Choose the order that matches your check stock **from top to bottom**.
   The three boxes show where Check, Stub 1 and Stub 2 will go. Save settings.
3. **Print the test.** Put plain Letter paper in the real printer. Click
   **Print alignment test page**. Hold the sheet over unused check stock against a
   light. The labeled sections should match the stock. Measure two numbered ruler
   marks: adjacent numbers should be exactly one inch apart.
4. **Adjust if needed.** Enter small nudges for the section that needs moving:
   positive X moves right, negative X left; positive Y moves down, negative Y up.
   Start with `0.02` inch. Save and print another test. Leave split lines blank for
   equal thirds. Only change them if your installer has measured the original
   QuickBooks layout (for example `3.5` and `7` inches from the top).
5. **Try QuickBooks on plain paper.** Reopen QuickBooks, select its three-part
   voucher check layout, and select **Voucher Reorder** as its printer. Use Letter,
   portrait and one copy. Print one check to plain paper, then overlay it on stock.
   Check the payee, amount, voucher text and bottom check line. Follow your normal
   bookkeeping procedure for that test; avoid accidentally issuing a duplicate.
6. **Use it.** After the overlay is approved, load the stock in the same direction
   and tray and print to **Voucher Reorder**. Stay signed in. You will not need to
   open or save a PDF. Reopen **Voucher Reorder → Settings** from Start to adjust.

**If nothing prints or you see a warning:** open Settings → **Job status**. Check
both the Voucher Reorder and real printer queues in Windows, and look at the paper
already printed. A job marked “sent” can still be waiting in Windows. Do not just
print it again. **Cancel waiting jobs** cancels only jobs still waiting in this app;
also cancel unwanted jobs in Windows. Ask for help if you are unsure.

**Remove it:** cancel pending jobs in both printer queues, close Settings and
QuickBooks, then use Windows **Settings → Apps → Voucher Reorder → Uninstall**
from the account that installed it. This removes the app, its printer, startup
entry and its saved local jobs/settings. Shared Microsoft drivers/runtimes remain.

**When asking for help:** send the Windows and QuickBooks versions, printer model,
section order, and measurements from a **fake alignment page**. Never post a real
check, bank details, payee names or spool files to the public project.
