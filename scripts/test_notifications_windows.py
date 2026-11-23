"""Real kernel notifications and a real broker/processor, with synthetic jobs only."""

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import voucher_reorder
from voucher_reorder.alignment import create
from voucher_reorder.config import Settings, save
from voucher_reorder.process import background_options

# Instrument the real broker from inside its process. Its own descendants are
# recorded, including an accidental periodic spawn; the parent test may poll.
BOOTSTRAP = r"""
import json, sys
from voucher_reorder import watcher
from voucher_reorder.config import atomic_json, data_dir
root = data_dir()
metrics = {"launches": 0, "exits": 0}
def record():
    atomic_json(root / "metrics.json", metrics)
launch = watcher.launch_processor
def tracked(root):
    metrics["launches"] += 1
    record()
    return launch(root)
wait = watcher.Changes.wait
def waiting(self, timeout=None):
    # The retention sweep needs a daily deadline. Reject short polling waits.
    assert timeout is not None and 23 * 3600 <= timeout <= 24 * 3600, timeout
    # Metrics themselves generate an ignored directory event, so don't write here.
    result = wait(self, timeout)
    if "processor" in result:
        metrics["exits"] += 1
        record()
    return result
watcher.Changes.wait = waiting
assert 'pypdf' not in sys.modules
with watcher.FileLock(root / "worker.lock"):
    record()
    watcher._serve(root, launch=tracked)
assert 'pypdf' not in sys.modules
"""


def wait_for(check, description, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError(f"Timed out: {description}")


def main(virtual=False):
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        root = base / "VoucherReorder"
        root.mkdir()
        inbox = root / "Inbox"
        inbox.mkdir()
        config = Settings(
            mode="virtual" if virtual else "pdf", output_mode="pdf", output_folder=str(base / "saved")
        )
        save(root / "settings.json", config)
        env = dict(os.environ, LOCALAPPDATA=str(base))
        executable = Path(sys.executable).with_name("pythonw.exe")
        with subprocess.Popen([str(executable), "-c", BOOTSTRAP], env=env, **background_options()) as broker:

            def read(name):
                path = root / name
                return json.loads(path.read_text()) if path.exists() else {}

            def states():
                return [json.loads(p.read_text()) for p in (root / "jobs").glob("*/state.json")]

            def idle():
                data = read("metrics.json")
                return data and data["launches"] == data["exits"]

            def sent(count):
                jobs = states()
                diagnostics = read("processing-error.json")
                assert not any(j["state"] in {"failed", "review"} for j in jobs), (jobs, diagnostics)
                return sum(j["state"] == "sent" for j in jobs) == count

            def quiet():
                wait_for(idle, "processor exit")
                time.sleep(0.5)  # consume queued terminal notifications
                before = read("metrics.json")
                time.sleep(3)
                after = read("metrics.json")
                assert before == after, (before, after)
                assert broker.poll() is None

            try:
                wait_for(lambda: read("watcher.json").get("state") == "waiting", "broker readiness")
                quiet()
                assert read("metrics.json")["launches"] == 0
                # Real Inbox burst: new, renamed, and held open during a slow save.
                create(inbox / "first.pdf", config)
                create(inbox / "second.tmp", replace(config, order=(2, 0, 1)))
                (inbox / "second.tmp").rename(inbox / "second.pdf")
                third = base / "third.pdf"
                create(third, replace(config, order=(0, 2, 1)))
                with (inbox / "third.pdf").open("wb") as output:
                    output.write(third.read_bytes())
                    output.flush()
                    time.sleep(4)
                    assert not sent(3), "Must not accept an open PDF"
                wait_for(lambda: sent(3), "three Inbox jobs")
                quiet()
                assert read("metrics.json")["launches"] >= 1
                # The processor is gone; persisted status remains readable.
                result = subprocess.run(
                    [
                        sys.executable,
                        str(Path(voucher_reorder.__file__).resolve().parents[1] / "app.py"),
                        "status",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                assert "Worker: idle" in result.stdout and result.stdout.count("sent:") == 3
                # Disabling Inbox does not launch a processor; reenabling catches up.
                save(root / "settings.json", replace(config, watch_inbox=False))
                create(inbox / "disabled.pdf", config)
                quiet()
                assert sent(3)
                save(root / "settings.json", config)
                wait_for(lambda: sent(4), "Inbox reenabled")
                quiet()
                # Restart keeps receipts; unchanged originals do not spawn work.
                (root / "stop").touch()
                assert broker.wait(timeout=15) == 0
            finally:
                (root / "stop").touch()
                try:
                    broker.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    broker.kill()
                    raise
        (root / "stop").unlink()
        with subprocess.Popen(
            [str(executable), "-c", BOOTSTRAP], env=env, **background_options()
        ) as restarted:
            try:
                wait_for(lambda: read("watcher.json").get("state") == "waiting", "restart readiness")
                time.sleep(3)
                assert read("metrics.json")["launches"] == 0
            finally:
                (root / "stop").touch()
                assert restarted.wait(timeout=15) == 0
        print(
            f"PASS: {'virtual + PDF' if virtual else 'PDF'} event notifications, quiet idle, bursts, locked/renamed Inbox, toggle, exit, status and restart"
        )


if __name__ == "__main__":
    main("--virtual" in sys.argv)
