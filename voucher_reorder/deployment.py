"""Versioned per-user installations; activation never overwrites a running runtime."""
import configparser
import json
import re
import shutil
from contextlib import ExitStack
from pathlib import Path

from .config import atomic_json
from .locking import FileLock
from .queue import Queue

IDENTITY = 'org.voucher-reorder.desktop'


def version_key(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Release versions must be major.minor.patch.')
    return tuple(int(n) for n in value.split('.'))


def active(root):
    file = root/'current.json'
    if not file.exists():
        return None
    value = json.loads(file.read_text())
    if value.get('identity') != IDENTITY or not re.fullmatch(r'app-[A-Za-z0-9_-]+', value['directory']):
        raise ValueError('Installation identity is invalid; no files were removed.')
    version_key(value['version'])
    return value


def publish(root, value):
    atomic_json(root/'current.json', value)
    config = configparser.ConfigParser()
    config['app'] = {'directory': 'deployments\\'+value['directory'], 'version': value['version']}
    target = root/'current.ini'
    temp = root/'current.ini.tmp'
    with temp.open('w', encoding='utf-8') as f:
        config.write(f)
    temp.replace(target)


def cleanup(root, keep):
    leftovers = []
    for folder in (root/'deployments').glob('app-*'):
        if folder.name == keep:
            continue
        marker = folder/'PACKAGE.json'
        if not marker.is_file() or folder.is_symlink():
            continue
        try:
            if json.loads(marker.read_text()).get('identity') == IDENTITY:
                shutil.rmtree(folder)
        except (OSError, ValueError):
            leftovers.append(folder.name)
    return leftovers


def install(root: Path, candidate: Path, data: Path, integrate, timeout=150):
    manifest = json.loads((candidate/'PACKAGE.json').read_text())
    if manifest.get('identity') != IDENTITY or candidate.parent.resolve() != (root/'deployments').resolve():
        raise ValueError('Invalid installation package.')
    if not re.fullmatch(r'app-[A-Za-z0-9_-]+', candidate.name):
        raise ValueError('Invalid deployment directory.')
    data.mkdir(parents=True, exist_ok=True)
    with FileLock(data/'install.lock', timeout=1):
        old = active(root)
        if old and version_key(manifest['version']) < version_key(old['version']):
            raise ValueError('A newer version is installed. Downgrades are blocked; your settings and jobs were not changed.')
        target = {'identity': IDENTITY, 'version': manifest['version'], 'directory': candidate.name}
        atomic_json(data/'maintenance.json', {'action': 'upgrade'})
        (data/'stop').touch()
        try:
            with ExitStack() as stack:
                for name in ('ui', 'worker', 'queue'):
                    stack.enter_context(FileLock(data/f'{name}.lock', timeout=timeout))
                queue = Queue(data/'jobs')
                for job in queue.jobs():
                    if queue.read(job)['state'] in ('printing', 'converting'):
                        queue.update(job, 'review', 'Interrupted job: inspect the printer queue and paper before reprinting.')
                queue.hold_waiting()
                try:
                    integrate(candidate, manifest['version'])
                    publish(root, target)
                except Exception:
                    if old:
                        integrate(root/'deployments'/old['directory'], old['version'])
                        publish(root, old)
                    raise
            leftovers = cleanup(root, candidate.name)
            return {'version': manifest['version'], 'leftovers': leftovers}
        finally:
            (data/'maintenance.json').unlink(missing_ok=True)
            (data/'stop').unlink(missing_ok=True)


def prepare_uninstall(data, timeout=150):
    atomic_json(data/'maintenance.json', {'action': 'uninstall'})
    (data/'stop').touch()
    try:
        with ExitStack() as stack:
            for name in ('ui', 'worker', 'queue'):
                stack.enter_context(FileLock(data/f'{name}.lock', timeout=timeout))
            queue = Queue(data/'jobs')
            queue.hold_waiting()
    except Exception:
        (data/'maintenance.json').unlink(missing_ok=True)
        raise
