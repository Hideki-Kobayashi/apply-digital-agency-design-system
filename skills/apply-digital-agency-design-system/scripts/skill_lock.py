"""Provide one cross-platform exclusive file lock for Skill mutations."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


@contextlib.contextmanager
def exclusive_file_lock(lock_file: Path) -> Iterator[None]:
    """Block until one process owns the byte-range or advisory file lock."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a+b") as lock:
        if os.name == "nt":
            # Windows byte-range locks need an existing byte to lock.
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
