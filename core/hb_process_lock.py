"""Cross-process gates for APEX turns and source-write transactions."""
from pathlib import Path
import fcntl
import hashlib
import os
import re
import time


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
