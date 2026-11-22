# Voucher Reorder — quick user guide

**Start with plain paper, not check stock.** Windows 10/11 x64 is supported.

1. **Install or upgrade.** Run `VoucherReorder-0.2.2-Setup.exe` normally. If SmartScreen
   appears, confirm the download came from this project, then choose **More info →
   Run anyway**. PDF mode needs no administrator access. For virtual mode, select
   **Virtual printer (one administrator prompt)** in setup. Setup includes the matching
   provisioning package; approve one UAC prompt or decline and use PDF mode. You can
   also enable it later in Settings. Run newer installers without uninstalling first.
   If the machine package is older, the app upgrades in PDF mode and explains how to
   update the optional component. Your printer/layout settings stay saved.
2. **Choose the output and both orders.** Open Voucher Reorder from Start. Choose
   your printer, matching paper size and tray. Without a physical printer, choose
   **Save reordered PDF (test, no physical printer)** and **Browse** to a folder
   outside the Inbox. Microsoft Print to PDF and PDF/XPS writer selections use this
   same direct PDF output. No physical printer or output-driver Save dialog is needed.
   On the Alignment tab, choose the **Source page (QuickBooks)** order on the left
   and **Printed output (physical stock)** order on the right, both top to bottom.
   The source defaults to Check / Stub 1 / Stub 2. Check the labeled previews and
   save. Both tabs scroll in small windows. Use portrait printer preferences.
3. **Align on plain paper.** Click **Print alignment test**. Measure the ruler:
   adjacent numbers must be exactly one inch apart. Overlay the sheet on unused
   stock. Adjust nudges in small steps, such as `0.02` inch: positive X moves right,
   positive Y down. Nudges follow the named section whichever source order you choose.
   Save and print another test. Leave **Section heights** blank for equal thirds.
   For unequal sections, measure both dividing lines from the top of the original
   source page: for heights 3.5 / 3.5 / 4 inches, enter `3.5` and `7`. Printer margins
   can clip text; the app will not shrink it to fit. In PDF output mode, the alignment
   test saves a vector PDF; **Job status** gives its path. Open it to check section
   placement. Physical alignment/MICR still require a real printer test.
4. **Print from QuickBooks using the active mode.**
   - **Virtual printer:** select **Voucher Reorder**, portrait, the matching paper
     size and one copy. Reordering and forwarding happen automatically.
   - **PDF handoff:** select an already available **Microsoft Print to PDF** (or your
     existing PDF exporter). Click **Copy Inbox path** in the app and paste that
     folder into the Save dialog. Save each new job under a new PDF filename. With
     automatic Inbox processing checked, it prints or saves the reordered PDF when saving finishes. Or save
     elsewhere, then click **Print a PDF** and choose the file. If no PDF printer or
     exporter exists, ask your administrator to enable one; this app does not do so.
5. **Approve the real layout.** Print one QuickBooks check to **plain paper only**,
   following your office's normal test/reprint procedure. Overlay it on unused stock
   and check every field, stub and bottom check line. Only then use check stock in
   the same tray and feed direction. Stay signed in while jobs are printing.

**PDF test output:** saved files have unique `VoucherReorder-...pdf` names and remain
in your chosen folder until you delete them. The Inbox and its subfolders cannot
be output folders. Generated files are refused as new input, including copies back
into the Inbox; always use the original QuickBooks PDF for a new test.

**After a 0.2.0 upgrade:** source order defaults to Check / Stub 1 / Stub 2; existing
output order and nudges stay unchanged, including held jobs. The unused QuickBooks
version and printer model fields are removed when settings are saved.

**After an update:** Settings closes while the app finishes the current job.
Waiting jobs are held. Check **Job status**, load the right paper, then choose
**Resume held jobs**. A failed/interrupted job is never automatically reprinted.
If setup is interrupted, run the installer again; do not install an older version.

Flatten layers before export and split batches larger than 250 pages.

**If nothing prints:** check Job status, the real Windows printer queue, and paper
already printed. “Sent” can still mean waiting in Windows. Do not simply print again.
Exact duplicate PDFs are suppressed for 24 hours. Cancel unwanted jobs in both the
app and Windows. Inbox originals remain until you delete them after checking output.

**Switch modes:** use the buttons at the top of the app. Adding/removing the virtual
printer needs UAC; PDF mode does not. During setup, “Setting up the Voucher Reorder
printer...” and a moving progress bar appear. The mode buttons are disabled while
it runs, and a success/failure message appears when finished. One UAC prompt is
expected; declining it leaves PDF handoff available. **Uninstall:** use Windows Settings → Apps.
Declining UAC can leave the optional printer installed but removes the per-user app.
Your settings, Inbox and held jobs remain for reinstall. After checking queues and
paper, you may delete `%LOCALAPPDATA%\VoucherReorder` to remove those saved files.

For help, share only Windows/QuickBooks versions, printer model, stock order and
measurements or photos of **fake alignment pages**. Never post real checks, bank
numbers, payee names, settings files or spool files to the public project.

Printing preserves vector text and paths through the Windows driver. Use a vector
PDF export: scanned/image PDFs, raster fallback and blank vector pages are refused.
The expected workload is ten pages or fewer per job; consecutive jobs run serially
with a fresh bounded print process each time. Printing time scales with page count. Recheck
alignment and MICR on the intended printer before using check stock.

To remove machine provisioning, reconcile/cancel Windows queue jobs and uninstall
**Voucher Reorder Printer Provisioning** from Windows Apps as administrator. The
per-user app and its PDF mode are independent of that package.
