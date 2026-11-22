"""Bounded publication retries for short-lived Windows sharing violations."""

import os
import time


def replace_file(source, destination):
    """Retry only atomic rename, never document processing or printer submission.

    Windows readers and scanners can briefly deny DELETE sharing even after a
    writer has closed its file. Keep the same complete temporary file and target
    throughout; permanent errors still propagate after at most 3.25s of backoff.
    """
    delay = 0.05
    for attempt in range(10):
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 9:
                raise
            time.sleep(delay)
            delay = min(0.5, delay * 2)
