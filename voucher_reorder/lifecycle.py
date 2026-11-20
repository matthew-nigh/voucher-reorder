"""Graceful worker shutdown, including recovery from stale heartbeat files."""

import socket
import time


def stop_worker(root, address=("127.0.0.1", 515), timeout=150):
    (root / "stop").touch()
    deadline = time.monotonic() + timeout
    while True:
        with socket.socket() as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(address)
            except OSError:
                # A listener (possibly a conflicting application) still owns the port.
                # Never kill it or assume that a stale heartbeat means it is safe.
                pass
            else:
                (root / "worker.json").unlink(missing_ok=True)
                return
        if time.monotonic() >= deadline:
            raise RuntimeError("Worker has not stopped. Check printer queues before trying again.")
        time.sleep(0.1)
