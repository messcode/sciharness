"""Local execution provenance, strict paths, and crash-safe checkpoints."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath


class LoopError(Exception):
    pass


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    """Reject traversal and every symlink component, even links inside root."""
    if not isinstance(relative, str) or "\\" in relative:
        raise LoopError("expected a relative POSIX path")
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
        raise LoopError("unsafe path: {!r}".format(relative))
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise LoopError("symlinks are not allowed: {}".format(current))
    return current


def files(root: Path, max_bytes: int, max_files: int) -> dict:
    """Manifest only ordinary files; never open FIFOs/devices or follow links."""
    result = {}
    total = 0
    for directory, names, filenames in os.walk(root, followlinks=False):
        for name in names + filenames:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise LoopError("non-regular artifact: {}".format(path))
            if stat.S_ISREG(mode):
                total += path.stat().st_size
                if total > max_bytes or len(result) >= max_files:
                    raise LoopError("artifact budget exceeded")
                result[path.relative_to(root).as_posix()] = file_hash(path)
    return dict(sorted(result.items()))


def copy_new(source: Path, target: Path) -> None:
    """Durable no-clobber copy; an interrupted copy never becomes final evidence."""
    data = source.read_bytes()
    if target.exists():
        if target.read_bytes() != data:
            raise LoopError("refusing to overwrite modified promoted output: " + str(target))
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=".sci-loop-copy-", dir=target.parent)
    temporary = Path(temporary_name)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        # Hard-link creation is atomic and refuses to clobber a competing write.
        os.link(temporary, target)
    except FileExistsError:
        if target.read_bytes() != data:
            raise LoopError("refusing to overwrite modified promoted output: " + str(target))
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value) -> None:
    safe_path(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    safe_path(path.parent, temporary.name)
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    # Also make the rename durable across a machine restart on POSIX.
    if hasattr(os, "O_DIRECTORY"):
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise LoopError("cannot read checkpoint {}: {}".format(path, exc)) from exc


def run_path(base: Path, run_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise LoopError("invalid execution ID")
    return safe_path(base, "runs/" + run_id)


@contextlib.contextmanager
def lock(base: Path):
    """OS-released advisory lock; a crashed process cannot leave a stale lock."""
    try:
        import fcntl
    except ImportError as exc:
        raise LoopError("this MVP requires POSIX file locking") from exc
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)  # Selected inputs and transcripts may contain private data.
    path = safe_path(base, "lock")
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LoopError("another sci-loop command is writing this project") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
