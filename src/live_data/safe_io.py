"""Atomic file replacement that tolerates Windows/OneDrive sharing locks.

On Windows an `os.replace` onto a file that OneDrive (or an antivirus) is
syncing fails with PermissionError [WinError 5].  Retry briefly, then fall back
to copying the finished temporary file over the target.  If even that fails the
original error is raised, so no write is silently lost.
"""
import os, shutil, time
from pathlib import Path


def safe_replace(tmp, target, attempts=6, wait=0.5):
    tmp, target = Path(tmp), Path(target)
    error = None
    for i in range(attempts):
        try:
            os.replace(tmp, target);return target
        except PermissionError as exc:
            error = exc
            try:
                if target.exists():os.chmod(target, 0o666)
            except OSError:pass
            time.sleep(wait * (i + 1))
    try:
        shutil.copyfile(tmp, target)
        try:tmp.unlink()
        except OSError:pass
        return target
    except OSError:
        raise error
