import sqlite3
import pytest
from core.hb_dream import _observe, idle_seconds


def test_unknown_and_persistence(tmp_path):
    path=tmp_path / 'activity.sqlite'
    conn=sqlite3.connect(path)
    assert idle_seconds(conn,now=100) is None
    assert _observe(conn,100,'owner:1')
    conn.commit()
    conn.close()
    conn=sqlite3.connect(path)
    assert idle_seconds(conn,now=3700)==3600
    assert not _observe(conn,100,'owner:1')
    assert not _observe(conn,50,'older')
    assert idle_seconds(conn,now=3700)==3600
    conn.close()


def test_hour_boundary_and_future_clock(tmp_path):
    with sqlite3.connect(tmp_path / 'clock.sqlite') as conn:
        _observe(conn,100,'owner:1')
        assert idle_seconds(conn,now=3699)==3599
        assert idle_seconds(conn,now=3700)==3600
        _observe(conn,4000,'future')
        assert idle_seconds(conn,now=3700)==0


@pytest.mark.parametrize('stamp',[True,False,float('nan'),float('inf'),-1])
def test_invalid_timestamp(tmp_path,stamp):
    with sqlite3.connect(tmp_path / 'invalid.sqlite') as conn:
        with pytest.raises(ValueError):
            _observe(conn,stamp,'invalid')
