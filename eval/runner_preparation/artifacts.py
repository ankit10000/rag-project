"""Exclusive, atomic publication of development-only scorer comparisons.

The complete directory becomes visible in one native no-replace rename. A crash
before that point leaves an incomplete private stage/claim, never a final bundle.
Crash leftovers are deliberately not stolen or deleted by a retry. Ordinary
failures clean only the claim and stage inodes created by this invocation.
"""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

REQUIRED_FILES = frozenset({'comparison.v2.jsonl', 'comparison.v2.jsonl.scoring.json',
                            'comparison.v2.diff.md', 'provenance.json'})
MANIFEST = 'artifact-manifest.json'
COMPLETED = 'COMPLETED.json'
MANIFEST_FORMAT = 'wp7-development-artifacts/1'
COMPLETION_FORMAT = 'wp7-development-completion/1'
_NOFOLLOW = os.O_NOFOLLOW | os.O_DIRECTORY
_OFFICIAL = Path(__file__).absolute().parents[1] / 'phase35' / 'results'


class PublicationDurabilityError(OSError):
    """The complete bundle was committed, but parent fsync failed.

    ``path`` identifies the valid committed bundle. Retrying the same run ID is
    refused, preserving its data; no claim is retained after this outcome.
    """
    def __init__(self, path, error):
        super().__init__(error.errno, 'bundle committed; directory durability confirmation failed')
        self.path = path


def _canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n').encode()


def _identity(info):
    return info.st_dev, info.st_ino


def _same(parent, name, identity):
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        return stat.S_ISDIR(info.st_mode) and _identity(info) == identity
    except FileNotFoundError:
        return False


def _open_tree(path):
    """Walk without following any symlink, including dangling parent links."""
    path = Path(os.path.abspath(os.fspath(path)))
    fd = os.open(path.anchor, os.O_RDONLY | _NOFOLLOW)
    try:
        for component in path.parts[1:]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | _NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _rename_exclusive(parent, source, target):
    """No check-then-rename race: even an empty target cannot be replaced."""
    libc = ctypes.CDLL(None, use_errno=True)
    name, flag = ('renameatx_np', 4) if sys.platform == 'darwin' else ('renameat2', 1)
    function = getattr(libc, name, None)
    if function is None:
        raise NotImplementedError('atomic no-replace directory rename is unavailable')
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(parent, os.fsencode(source), parent, os.fsencode(target), flag):
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError(code, 'comparison run already exists', target)
        raise OSError(code, os.strerror(code), target)


def _remove_owned(parent, name, identity):
    if not _same(parent, name, identity):
        return
    directory = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=parent)
    try:
        if _identity(os.fstat(directory)) != identity:
            return
        for child in os.listdir(directory):
            info = os.stat(child, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                _remove_owned(directory, child, _identity(info))
            else:
                os.unlink(child, dir_fd=directory)
    finally:
        os.close(directory)
    if _same(parent, name, identity):
        os.rmdir(name, dir_fd=parent)


def _write_exclusive(directory, name, payload):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as output:
            output.write(payload); output.flush()
        os.fsync(fd)
    finally:
        os.close(fd)


def _file_record(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('bundle files must be regular and have exactly one link')
        digest = hashlib.sha256(); size = 0
        while data := os.read(fd, 1024*1024):
            digest.update(data); size += len(data)
        os.fsync(fd)
        after = os.fstat(fd)
        if (info.st_size, info.st_mtime_ns, info.st_ino, info.st_nlink) != (after.st_size, after.st_mtime_ns, after.st_ino, after.st_nlink):
            raise ValueError('bundle file changed while sealing')
        return {'sha256': digest.hexdigest(), 'bytes': size}
    finally:
        os.close(fd)


def publish_bundle(root, run_id, *, scorer_version, build_fn):
    """Build and atomically publish one immutable, development-only bundle.

    ``build_fn(stage_path)`` must synchronously write exactly REQUIRED_FILES.
    It must not retain open writers or modify the stage after returning.
    Existing paths/claims are never reclaimed. No historical-result directory
    (or a symlink alias) is accepted as the comparison root.
    """
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', run_id):
        raise ValueError('run_id must be a safe identifier of at most 80 characters')
    if not isinstance(scorer_version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', scorer_version):
        raise ValueError('scorer_version must be an explicit numeric semantic version')
    if not callable(build_fn):
        raise ValueError('build_fn must be callable')
    root = Path(os.path.abspath(os.fspath(root)))
    if root == _OFFICIAL or _OFFICIAL in root.parents:
        raise ValueError('comparison root must be separate from official results')
    namespace = root / 'development-comparisons' / ('scorer-'+scorer_version)
    parent = _open_tree(namespace)
    claim = '.'+run_id+'.claim'; stage = '.'+run_id+'.stage-'+uuid.uuid4().hex
    claim_id = stage_id = None; committed = False
    final = namespace / run_id
    try:
        # lexists via stat: dangling links and empty directories also collide.
        try:
            os.stat(run_id, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError('comparison run already exists')
        os.mkdir(claim, mode=0o700, dir_fd=parent)
        claim_id = _identity(os.stat(claim, dir_fd=parent, follow_symlinks=False))
        os.mkdir(stage, mode=0o700, dir_fd=parent)
        stage_id = _identity(os.stat(stage, dir_fd=parent, follow_symlinks=False))
        build_fn(namespace / stage)
        if not _same(parent, stage, stage_id):
            raise ValueError('owned staging directory was replaced')
        directory = os.open(stage, os.O_RDONLY | _NOFOLLOW, dir_fd=parent)
        try:
            if set(os.listdir(directory)) != REQUIRED_FILES:
                raise ValueError('bundle must contain exactly the four declared comparison files')
            records = {name: _file_record(directory, name) for name in sorted(REQUIRED_FILES)}
            manifest = _canonical({'format': MANIFEST_FORMAT, 'scorer_version': scorer_version,
                                   'development_only': True, 'acceptance_eligible': False, 'files': records})
            _write_exclusive(directory, MANIFEST, manifest)
            _write_exclusive(directory, COMPLETED, _canonical({'format': COMPLETION_FORMAT,
                'scorer_version': scorer_version, 'acceptance_eligible': False,
                'manifest_sha256': hashlib.sha256(manifest).hexdigest()}))
            os.fsync(directory)
        finally:
            os.close(directory)
        os.fsync(parent)
        if not _same(parent, stage, stage_id):
            raise ValueError('owned staging directory was replaced before publication')
        _rename_exclusive(parent, stage, run_id)
        committed = True
        try:
            os.fsync(parent)
        except OSError as error:
            raise PublicationDurabilityError(final, error) from error
        return final
    finally:
        try:
            if not committed and stage_id is not None:
                _remove_owned(parent, stage, stage_id)
            if claim_id is not None:
                _remove_owned(parent, claim, claim_id)
        finally:
            os.close(parent)


def verify_bundle(path):
    """Read/verify a completed bundle; a marker alone is never completion proof."""
    path = Path(os.path.abspath(os.fspath(path)))
    # Do not create anything in a reader; lstat each parent before opening.
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError('bundle path must contain only real directories')
    directory = os.open(path, os.O_RDONLY | _NOFOLLOW)
    try:
        if set(os.listdir(directory)) != REQUIRED_FILES | {MANIFEST, COMPLETED}:
            raise ValueError('incomplete or unexpected bundle files')
        def read(name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('invalid metadata file')
                with os.fdopen(fd, 'rb', closefd=False) as source:
                    return source.read()
            finally:
                os.close(fd)
        manifest_data = read(MANIFEST)
        manifest = json.loads(manifest_data); completion = json.loads(read(COMPLETED))
        if not isinstance(manifest, dict) or not isinstance(completion, dict):
            raise ValueError('completion and manifest must be objects')
        if (manifest.get('format') != MANIFEST_FORMAT or completion.get('format') != COMPLETION_FORMAT
                or manifest.get('acceptance_eligible') is not False
                or manifest.get('development_only') is not True
                or completion.get('acceptance_eligible') is not False
                or completion.get('manifest_sha256') != hashlib.sha256(manifest_data).hexdigest()
                or completion.get('scorer_version') != manifest.get('scorer_version')
                or set(manifest.get('files', {})) != REQUIRED_FILES):
            raise ValueError('invalid completion/manifest binding')
        if any(_file_record(directory, name) != manifest['files'][name] for name in REQUIRED_FILES):
            raise ValueError('bundle content hash mismatch')
        return manifest
    finally:
        os.close(directory)
