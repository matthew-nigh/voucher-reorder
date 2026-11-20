"""CLI is for packaging/tests; office users only see the native settings window."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from . import alignment
from .config import data_dir, load, save
from .engine import reorder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "desktop-settings",
            "settings",
            "worker",
            "register",
            "alignment",
            "validate",
            "status",
            "discard",
            "stop",
        ],
        nargs="?",
        default="settings",
    )
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = args.config or root / "settings.json"
    if args.command == "desktop-settings":
        from .windows import launch_desktop_settings

        launch_desktop_settings()
    elif args.command == "worker":
        from .worker import serve

        serve()
    elif args.command == "register":
        from .windows import register_user

        register_user()
    elif args.command == "settings":
        from .windows import powershell, register_user, run

        register_user()
        if not config.exists():
            save(config, load(config))
        run(powershell("settings.ps1"), timeout=None)
    elif args.command == "validate":
        settings = load(config)
        settings.edges(792)
        if not settings.printer:
            raise ValueError("Choose a physical printer.")
    elif args.command == "alignment":
        from .windows import forward

        settings = load(config)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            source, output = Path(folder) / "sample.pdf", Path(folder) / "alignment.pdf"
            alignment.create(source, settings)
            reorder(source, output, settings)
            forward(output, settings.printer, root / "sumatra")
    elif args.command == "status":
        states = []
        for state in sorted((root / "jobs").glob("*/state.json")):
            item = json.loads(state.read_text())
            states.append(item["state"] + ": " + item["message"])
        heartbeat = root / "worker.json"
        active = heartbeat.exists() and time.time() - json.loads(heartbeat.read_text())["heartbeat"] < 15
        print(
            (
                "Background app running."
                if active
                else "Background app is not responding. Close and reopen Settings."
            )
            + "\n"
            + "\n".join(states[-10:])
        )
    elif args.command in ("stop", "discard"):
        (root / "stop").touch()
        for _ in range(150):
            if not (root / "worker.json").exists():
                break
            time.sleep(1)
        else:
            raise RuntimeError("Worker has not stopped. Check printer queues before trying again.")
        if args.command == "discard":
            from .queue import Queue

            queue = Queue(root / "jobs")
            for job in queue.jobs():
                if queue.read(job)["state"] == "queued":
                    queue.update(job, "discarded", "Canceled by user")
            from .windows import register_user

            register_user()


if __name__ == "__main__":
    main()
