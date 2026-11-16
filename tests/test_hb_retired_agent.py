"""Practice 39 (owner 15 Nov): "why is apex failing" - HB's current step waited all night on a review request to the retired git agent."""
import sqlite3
from pathlib import Path
import core.hb_task_manager as m


def test_practice_39_retired_agent_is_read_from_the_register():
    c = sqlite3.connect(':memory:')
    assert m.retired_agent(c, 'anyone') is False                      # no register yet: nobody is retired
    c.execute('CREATE TABLE hb_agents(agent_id TEXT, status TEXT)')
    c.executemany('INSERT INTO hb_agents VALUES (?,?)', [('old-agent', 'retired'), ('apex', 'active')])
    assert m.retired_agent(c, 'old-agent') is True
    assert m.retired_agent(c, 'apex') is False
    assert m.retired_agent(c, 'unknown') is False


def test_practice_39_tick_drops_a_queued_request_to_a_retired_agent():
    src = Path(m.__file__).read_text()
    i = src.index("retired_agent(conn,live[2])")
    block = src[i:i + 700]
    assert "state='cancelled'" in block and 'live=None' in block
    assert src.count('def review_recipient(conn):') == 1              # the duplicated definition is gone
