# Next steps for Matthew

## Done

- GPL-3.0-or-later change is the first branch commit, including the full official
  GPLv3 text, README notice and package metadata.
- Vector PDF reorder engine: all six orders, inch-based split lines and per-source
  nudges, multiple pages, unequal/odd page sizes, crop origins and rotation.
- Bounded local LPR receiver, durable queue, duplicate suppression and conservative
  crash/failure handling; Ghostscript conversion and silent actual-size forwarding.
- Native Windows settings with real-printer choice, section picture, offsets,
  optional environment notes, job status/cancel, and fake alignment page.
- NSIS installer packaging official pinned x64 runtimes, printer setup/rollback,
  desktop-token startup and uninstall; source/license archive and checksums.
- GitHub Actions Linux tests and Windows installer/artifact build; future v* tag
  pushes attach binary, sources and checksums to a Release.
- User guide, maintainer architecture/build docs, and detailed Windows checklist.

## Not done / not yet proven

This is an initial implementation, not a hardware-qualified release. No real
Windows workstation, QuickBooks session, physical printer or check stock was
available in the Linux development environment. The installer build and CI checks
do not prove successful installation, native settings behavior, queue behavior or
MICR/physical alignment on the intended office machine. No tags or releases are
created by this work. Code signing is intentionally absent.

The initial scope requires the QuickBooks user's own administrator account for
installation. Standard-user/alternate-admin onboarding, multiple active accounts,
print servers, ARM64, unattended printing while logged out, and automatic upgrades
are not implemented. Uninstall the previous version before reinstalling.

## Next real-machine steps (in order)

1. Record the Windows/QuickBooks versions, printer model/driver/tray and stock order.
   Download the PR's Windows artifact with its matching source/checksum archive.
2. Install while logged into the QuickBooks administrator account. Confirm the new
   printer, native settings, non-elevated worker and automatic startup after reboot.
3. Use only plain Letter paper. Select the real printer/order and print alignment.
   Measure the ruler (one inch between numbers), section edges and nudge direction.
4. Exercise all six orders and measured split lines. Confirm no scale changes or
   overlap when sections have different heights.
5. Print a fake QuickBooks voucher through **Voucher Reorder**; the Settings test
   button alone does not exercise the virtual printer. Check for unwanted dialogs.
6. Print one real QuickBooks check to plain paper, applying the office's normal
   test/reprint bookkeeping rules. Overlay it on unused stock, inspect every field
   and MICR line. Keep all real documents private. Obtain approval before using stock.
7. Print a fake multi-page batch and consecutive jobs; count sheets and check order.
8. Test offline printer, out-of-paper, crash/restart, cancellation and duplicate
   receipt behavior. Reconcile paper plus both queues before reprinting anything.
9. Inspect local data cleanup and account isolation. Uninstall, reboot, confirm
   cleanup and reinstall. Complete every item in TESTING_ON_WINDOWS.md.
10. Send only environment facts, checkbox outcomes, exact redacted errors, ruler
    measurements and fake-page images. Never upload real check/bank/spool data.

## Questions for Matthew

- Which QuickBooks Desktop year, edition and release is used?
- Which physical printer make/model, Windows driver, connection and paper tray?
- What is the stock's top-to-bottom section order and each section's measured height?
- Is Windows 10 or 11 used, is the account an administrator, and is Protected Print
  Mode or an organizational printer policy enabled?
- Are multiple users/computers expected to share this workflow?

The first three are deliberately configurable: version/model notes and section
order/split lines are in Settings. They remain unknown until Matthew supplies them.

## Known risks and limitations

- The Microsoft inbox PostScript driver may be unavailable or blocked. Setup must
  fail clearly; do not work around organizational security without the administrator.
- The loopback LPR endpoint is unauthenticated; other local processes can submit
  jobs directly. Printer ACLs do not protect that TCP endpoint. Use a trusted
  single-user workstation.
- LPR uses local port 515; an existing LPD service or another signed-in worker can
  conflict. The supported scope is one account. No new inbound firewall rule is used.
- End-to-end fonts, MICR, paper origin, feed direction, printer margins and actual
  scale require hardware testing. The reorder engine preserves vectors; downstream
  renderer/driver behavior is distinct and can rasterize at device resolution.
- Interrupted forwarding has an unknown physical outcome. There is no exactly-once
  guarantee across Windows, the printer and power failures. The app avoids automatic
  retries; operators must reconcile output. Byte-identical jobs are suppressed for
  24 hours, including intentional identical reprints.
- Waiting jobs can contain financial data locally until completed/canceled/expired.
  Expiry runs only while the app runs or at next start; deletion is not secure erase.
  Windows spooling/backup retention is separate. No financial data belongs in GitHub.
- The engine can reorder arbitrary sizes; automatic forwarding deliberately supports
  only portrait Letter. Nudges are clipped to section slots; they cannot recover
  content outside the physical printer's printable area.
- Unsigned setup triggers SmartScreen. Missing Microsoft C++ runtime requires an
  internet connection for a signature-checked download from Microsoft. Shared system
  prerequisites remain after uninstall. Full component notices/source accompany builds.

## Recommended next Codex rounds

1. **Windows acceptance fixes:** use the completed checklist to resolve driver
   registration, startup token, settings, LPR behavior, and uninstall issues. Do not
   expand scope before a full plain-paper QuickBooks print succeeds.
2. **Printer-specific alignment:** calibrate with Matthew's model/stock; confirm
   fonts/MICR, tray settings and offset precision. Add regression fixtures made only
   from fake data reproducing observed layout issues.
3. **Deployment hardening:** standard-user installation, upgrades/repair, clearer
   background-health reporting, queue recovery UX and multi-user needs if required.
4. **Release preparation:** dependency/security and corresponding-source review,
   optional signing, additional Windows matrix tests, and a maintainer-approved tag
   only after the real-machine acceptance gate passes.
