"""Practice 76 (audit 15 Nov): the archive moved onto the NVMe on 11 Nov; the memory backup refused to run from then on."""
import inspect
import os
import core.hb_archive as a
import core.vortex_backup as backup
import core.vortex_ledger as ledger


def test_practice_76_archive_is_trusted_by_mount_or_by_the_owners_marker(tmp_path):
    real = tmp_path / 'srv-archive'
    real.mkdir()
    link = tmp_path / 'mnt-archive'
    os.symlink(real, link)
    assert a.trusted(link) is False                       # a plain folder behind a link: not trusted (a missing disk looks like this)
    (real / a.MARKER).write_text('archive on the NVMe by JD, 11 Nov 2026')
    assert a.trusted(link) is True and a.trusted(real) is True
    assert a.trusted(tmp_path / 'nothing-here') is False
    assert a.trusted('/proc') is True                     # a real mount is trusted as before


def test_practice_76_backup_and_ledger_use_the_one_rule():
    assert 'hb_archive.trusted(archive)' in inspect.getsource(backup.backup_root)
    assert "hb_archive.trusted('/mnt/archive')" in inspect.getsource(ledger)
    assert 'is_mount()' not in inspect.getsource(backup.backup_root)
