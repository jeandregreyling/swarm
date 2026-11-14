"""Where HB's archive lives (audit 15 Nov 2026).

Until 11 Nov the archive was its own disk mounted at /mnt/archive, and the Vortex ledger and the daily memory backup refused to
write unless /mnt/archive was a mount - so a missing disk could never make them fill the system disk by accident.
On 11 Nov JD moved the archive onto the NVMe (/srv/archive; /mnt/archive is now a link to it). The old check then refused every
backup: none has been made since. The rule is now:
    the archive is trusted when it is a mounted volume, OR its real folder carries the owner's marker file (MARKER),
    which says in so many words that this folder IS the archive on purpose.
A missing disk still fails the check (no mount and no marker), so the original protection stays."""
from pathlib import Path

MARKER = '.hb-archive-here'


def trusted(path='/mnt/archive'):
    """True when `path` is a mounted volume, or resolves to a real folder (not /) that holds the owner's marker file."""
    path = Path(path)
    try:
        if path.is_mount():
            return True
        real = path.resolve()
        return real.is_dir() and real != Path('/') and (real / MARKER).is_file()
    except OSError:
        return False
