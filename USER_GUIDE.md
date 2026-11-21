# Voucher Reorder — quick user guide

**Start with plain paper, not check stock.** Windows 10/11 x64 is supported.

1. **Install or upgrade.** Run `VoucherReorder-0.2.0-Setup.exe` normally. If SmartScreen
   appears, confirm the download came from this project, then choose **More info →
   Run anyway**. Setup asks permission to add the virtual printer. Approve UAC (an
   administrator can enter credentials), or decline to use the app without admin.
   Either way, the app installs for your Windows account. For updates, run the newer
   installer without uninstalling first. Your settings stay saved.
2. **Choose the real printer.** Open Voucher Reorder from Start. Its top line shows
   **Virtual printer** or **PDF handoff** mode. Select your real printer, matching
   paper size and tray. On the Alignment tab, match the three boxes to your stock's
   top-to-bottom order. Save. Use portrait orientation in the printer's preferences.
3. **Align on plain paper.** Click **Print alignment test**. Measure the ruler:
   adjacent numbers must be exactly one inch apart. Overlay the sheet on unused
   stock. Adjust nudges in small steps, such as `0.02` inch: positive X moves right,
   positive Y down. Save and print another test. Leave split lines blank for equal
   thirds unless you have measured the original QuickBooks sections. Printer margins
   can clip text; the app will not shrink it to fit.
4. **Print from QuickBooks using the active mode.**
   - **Virtual printer:** select **Voucher Reorder**, portrait, the matching paper
     size and one copy. Reordering and forwarding happen automatically.
   - **PDF handoff:** select an already available **Microsoft Print to PDF** (or your
     existing PDF exporter). Click **Copy Inbox path** in the app and paste that
     folder into the Save dialog. Save each new job under a new PDF filename. With
     automatic Inbox printing checked, it forwards when saving finishes. Or save
     elsewhere, then click **Print a PDF** and choose the file. If no PDF printer or
     exporter exists, ask your administrator to enable one; this app does not do so.
5. **Approve the real layout.** Print one QuickBooks check to **plain paper only**,
   following your office's normal test/reprint procedure. Overlay it on unused stock
   and check every field, stub and bottom check line. Only then use check stock in
   the same tray and feed direction. Stay signed in while jobs are printing.

**After an update:** Settings closes while the app finishes the current job.
Waiting jobs are held. Check **Job status**, load the right paper, then choose
**Resume held jobs**. A failed/interrupted job is never automatically reprinted.
If setup is interrupted, run the installer again; do not install an older version.

**If nothing prints:** check Job status, the real Windows printer queue, and paper
already printed. “Sent” can still mean waiting in Windows. Do not simply print again.
Exact duplicate PDFs are suppressed for 24 hours. Cancel unwanted jobs in both the
app and Windows. Inbox originals remain until you delete them after checking output.

**Switch modes:** use the buttons at the top of the app. Adding/removing the virtual
printer needs UAC; PDF mode does not. **Uninstall:** use Windows Settings → Apps.
Declining UAC can leave the optional printer installed but removes the per-user app.
Your settings, Inbox and held jobs remain for reinstall. After checking queues and
paper, you may delete `%LOCALAPPDATA%\VoucherReorder` to remove those saved files.

For help, share only Windows/QuickBooks versions, printer model, stock order and
measurements or photos of **fake alignment pages**. Never post real checks, bank
numbers, payee names, settings files or spool files to the public project.
