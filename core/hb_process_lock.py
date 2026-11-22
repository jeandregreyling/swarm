"""Cross-process gates for APEX turns and source-write transactions."""
from pathlib import Path
import fcntl
import hashlib
import os
import re
import time
import tempfile


class ProcessLock:
    def __init__(self,purpose,root=None,timeout=30):
        from core.recovery_supervisor import ROOT
        if not re.fullmatch(r'[a-z-]+',purpose):raise ValueError('Invalid lock purpose')
        project=Path(root or ROOT).resolve()
        base=Path(os.environ.get('HUMMINGBIRD_LOCK_DIR',str(Path.home()/'.local/share/hummingbird/locks')))
        base.mkdir(mode=0o700,parents=True,exist_ok=True)
        if base.is_symlink():raise PermissionError('Lock directory cannot be a symlink')
        self.path=base/(purpose+'-'+hashlib.sha256(str(project).encode()).hexdigest()[:20]+'.lock')
        self.fd=None;self.timeout=timeout

    def acquire(self,timeout=None,on_wait=None):
        self.fd=os.open(self.path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        deadline=time.monotonic()+(self.timeout if timeout is None else timeout)
        waiting=False
        while True:
            try:
                fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                if not waiting and on_wait:
                    waiting=True;on_wait(1)
                if time.monotonic()>=deadline:
                    self.release();return False
                time.sleep(0.05)

    def release(self):
        if self.fd is not None:
            fcntl.flock(self.fd,fcntl.LOCK_UN)
            os.close(self.fd);self.fd=None

    def __enter__(self):
        if not self.acquire():raise RuntimeError('HB execution gate is busy; no execution started')
        return self

    def __exit__(self,*_):self.release()


class ForegroundWaiter:
    """Cross-process announcement, held until the interactive turn is finished.

    A locked, atomically published file represents one waiting/active turn.
    Kernel locks disappear on crash; stale files are cleaned by pending().
    """
    def __init__(self, turn):
        self.directory = turn.path.parent
        self.prefix = turn.path.name + '.foreground-'
        self.path = None
        self.fd = None

    def __enter__(self):
        fd, temp = tempfile.mkstemp(prefix='.pending-', dir=self.directory)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            path = self.directory / (self.prefix + os.path.basename(temp))
            os.replace(temp, path)
        except BaseException:
            os.close(fd)
            try: os.unlink(temp)
            except FileNotFoundError: pass
            raise
        self.fd, self.path = fd, path
        return self

    def __exit__(self, *_):
        try:
            if self.path is not None:
                try: os.unlink(self.path)
                except FileNotFoundError: pass
        finally:
            if self.fd is not None: os.close(self.fd)
            self.fd = self.path = None

    @staticmethod
    def pending(turn):
        prefix = turn.path.name + '.foreground-'
        for path in turn.path.parent.glob(prefix + '*'):
            try:
                fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            except FileNotFoundError:
                continue
            except OSError:
                return True  # Unknown state: never steal an interactive slot.
            try:
                try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: return True
                try: path.unlink()  # stale marker after process death
                except FileNotFoundError: pass
            finally:
                os.close(fd)
        return False


def yield_to_foreground(turn, on_wait=None):
    """Yield between tool rounds; resume with the original in-memory context."""
    if not ForegroundWaiter.pending(turn):
        return False
    turn.release()
    if on_wait: on_wait()
    while ForegroundWaiter.pending(turn):
        time.sleep(.05)
    if not turn.acquire():
        raise RuntimeError('APEX could not reacquire its turn after yielding to interactive chat')
    return True
