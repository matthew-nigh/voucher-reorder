"""Durable PDF/PS jobs with immutable settings and conservative print recovery."""
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .config import Settings, atomic_json
from .locking import FileLock

RETENTION = 24 * 3600
MAX_JOB = 100 * 1024 * 1024


class Queue:
    def __init__(self, root: Path, recover=False):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        if recover:
            with self.transaction():
                for job in self.jobs():
                    if self.read(job)['state'] in ('converting', 'printing'):
                        self.update(job, 'review', 'Interrupted job: inspect the real printer queue and paper before reprinting.')
                for folder in root.iterdir():
                    if folder.is_dir() and not (folder/'state.json').exists():
                        shutil.rmtree(folder)
                for partial in root.glob('receiving-*'):
                    partial.unlink(missing_ok=True)
                self.expire()

    def transaction(self):
        return FileLock(self.root.parent/'queue.lock', timeout=150)

    def jobs(self):
        return sorted(self.root.glob('*/state.json'), key=lambda p: p.parent.name)

    def read(self, job):
        return json.loads(job.read_text(encoding='utf-8'))

    def update(self, job, state, message=''):
        data = self.read(job)
        data.update(state=state, message=message)
        atomic_json(job, data)
        if state in ('sent', 'review', 'failed', 'discarded', 'expired'):
            for name in ('input.ps', 'input.pdf', 'output.pdf'):
                (job.parent/name).unlink(missing_ok=True)

    def accept_bytes(self, payload, settings: Settings, kind='pdf'):
        if kind not in ('pdf', 'ps') or not 0 < len(payload) <= MAX_JOB:
            raise ValueError('Job must be a PDF or PostScript file under 100 MiB.')
        digest = hashlib.sha256(payload).hexdigest()
        with self.lock, self.transaction():
            if (self.root.parent/'maintenance.json').exists():
                raise ValueError('An update is in progress. Try again after setup finishes.')
            for job in self.jobs():
                if self.read(job)['digest'] == digest:
                    return False
            if sum(self.read(j)['state'] in ('queued', 'held') for j in self.jobs()) >= 100:
                raise ValueError('The waiting queue is full. Open Job status.')
            folder = self.root/f'{time.time_ns()}-{uuid.uuid4().hex}'
            folder.mkdir(mode=0o700)
            with (folder/f'input.{kind}').open('wb') as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            atomic_json(folder/'state.json', {'state': 'queued', 'created': time.time(),
                'digest': digest, 'kind': kind, 'settings': asdict(settings), 'message': 'Waiting to print'})
            return True

    def accept(self, path, settings=None):
        return self.accept_bytes(path.read_bytes(), settings or Settings(), 'ps')

    def expire(self):
        for job in self.jobs():
            if time.time() - self.read(job)['created'] > RETENTION:
                shutil.rmtree(job.parent)

    def hold_waiting(self):
        for job in self.jobs():
            if self.read(job)['state'] == 'queued':
                self.update(job, 'held', 'Held during update. Use Resume held jobs when ready.')
