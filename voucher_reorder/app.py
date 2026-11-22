"""User commands used by the native UI and installer."""

import argparse
import json
import tempfile
from pathlib import Path

from .config import data_dir, load, save
from .locking import FileLock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="settings",
        choices=[
            "settings",
            "worker",
            "watch",
            "process",
            "register",
            "alignment",
            "validate",
            "status",
            "retry",
            "submit",
            "discard",
            "resume",
            "stop",
        ],
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = args.config or root / "settings.json"
    if (root / "maintenance.json").exists() and args.command not in ("stop", "status"):
        raise ValueError("Setup is in progress or was interrupted. Run the installer again to finish.")
    if args.command in ("worker", "watch"):
        from .watcher import serve

        serve()
    elif args.command == "process":
        from .worker import serve

        serve()
    elif args.command == "register":
        from .windows import register_user

        register_user()
    elif args.command == "settings":
        from .windows import powershell, register_user, run

        with FileLock(root / "ui.lock"):
            register_user()
            save(config, load(config))  # add new fields while preserving older settings
            (root / "Inbox").mkdir(exist_ok=True)
            run(powershell("settings.ps1"), timeout=None)
    elif args.command == "validate":
        settings = load(config)
        settings.edges(settings.paper_height * 72)
        if not settings.output_ready:
            raise ValueError("Choose an output printer or a folder for reordered PDFs.")
    elif args.command in ("alignment", "submit"):
        from . import alignment
        from .inbox import read_pdf
        from .queue import Queue

        settings = load(config)
        if not settings.output_ready:
            raise ValueError("Choose an output printer or PDF folder first.")
        with tempfile.TemporaryDirectory(dir=root) as folder:
            source = Path(folder) / "sample.pdf"
            if args.command == "alignment":
                alignment.create(source, settings)
            else:
                source = args.file
                if source is None:
                    raise ValueError("Choose a PDF.")
            accepted = Queue(root / "jobs").accept_bytes(read_pdf(source), settings)
            if not accepted:
                print("This exact PDF was already received in the last 24 hours; it was not printed again.")
            else:
                print("Job queued. Inspect Job status for the saved PDF or printer submission.")
        from .windows import register_user

        register_user()
    elif args.command == "retry":
        from .queue import Queue
        from .windows import register_user

        if not args.file:
            raise ValueError("Select a failed job to retry.")
        Queue(root / "jobs").retry(str(args.file), load(config))
        register_user()
    elif args.command == "status":
        print(f"Mode: {load(config).mode}. Job status is saved on disk.")
        for name in ("watcher.json", "worker.json", "printer-warning.json"):
            path = root / name
            health = json.loads(path.read_text()) if path.exists() else {}
            if health.get("state"):
                print(f"{name.removesuffix('.json').capitalize()}: {health['state']} (last saved state).")
            if health.get("error"):
                print(health["error"])
        for state in sorted((root / "jobs").glob("*/state.json"))[-15:]:
            item = json.loads(state.read_text())
            print(item["state"] + ": " + item["message"])
    elif args.command == "stop":
        from .lifecycle import stop_worker

        stop_worker(root)
    else:
        from .queue import Queue

        queue = Queue(root / "jobs")
        with queue.transaction():
            for job in queue.jobs():
                state = queue.read(job)["state"]
                if args.command == "discard" and state in ("queued", "held"):
                    queue.update(job, "discarded", "Canceled by user")
                if args.command == "resume" and state == "held":
                    queue.update(job, "queued", "Released by user")
        if args.command == "resume":
            from .windows import register_user

            register_user()


if __name__ == "__main__":
    main()
