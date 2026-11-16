"""Practice 35 (owner 14 Nov): "Attached apex request did not complete: ValueError: APEX tool studio_capacity_handoff failed ... 403" -
a turn that runs out of rounds ends as unfinished instead of crashing the request."""
from pathlib import Path
import core.apex_tools as t


def test_practice_35_refused_handoff_ends_the_turn_as_unfinished():
    src = Path(t.__file__).read_text()
    i = src.index('studio_handler("studio_capacity_handoff"')
    block = src[i - 40:i + 900]
    assert 'except Exception as exc' in block and 'The task remains unfinished; HB continues it next turn.' in block
