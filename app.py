"""Installed entry point; never write financial data or exception details to logs."""
from voucher_reorder.app import main

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import sys
        if len(sys.argv) < 2 or sys.argv[1] in ("settings", "register", "desktop-settings"):
            from voucher_reorder.windows import message
            message("Voucher Reorder could not start. Open the user guide or ask your installer for help.")
        raise SystemExit(1)
