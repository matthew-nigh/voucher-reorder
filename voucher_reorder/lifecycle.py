"""Stop without killing a possibly in-flight physical print."""
from .locking import FileLock


def stop_worker(root, timeout=150):
    (root/'stop').touch()
    with FileLock(root/'worker.lock', timeout=timeout):
        (root/'worker.json').unlink(missing_ok=True)
