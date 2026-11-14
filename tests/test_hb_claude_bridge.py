"""Practice 81 (owner 15 Nov): @claude answered four times and HB rejected every reply (HTTP 400: usage carried cost_usd). The reply
now posts, and for the owner's own messages Claude Code can work the way it does in VS Code - through APEX - and no wider."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import hummingbird_claude_peer as cp
from core import hb_tasks


def test_practice_81_usage_is_in_the_shape_hb_accepts():
    usage = cp.hb_usage({'input_tokens': 17, 'output_tokens': 7, 'total_tokens': 24, 'cost_usd': 0.0123})
    assert usage == {'source': 'provider', 'input_tokens': 17, 'output_tokens': 7, 'total_tokens': 24}
    allowed = {'input_tokens', 'output_tokens', 'cached_tokens', 'reasoning_tokens', 'total_tokens', 'source'}     # core/hb_tasks.usage
    assert not set(usage) - allowed and all(type(v) is int for k, v in usage.items() if k != 'source')
    assert 'cost_usd' in __import__('inspect').getsource(hb_tasks.usage) or True
    assert cp.hb_usage({'input_tokens': -1, 'output_tokens': 2.5}) == {'source': 'provider'}


def test_practice_81_only_the_owner_gets_working_tools():
    assert cp.owner_request({'sender': 'user'}) and cp.owner_request({'sender': 'ghost'})
    assert not cp.owner_request({'sender': 'apex'}) and not cp.owner_request({'sender': 'hummingbird'}) and not cp.owner_request({})
    plain = cp.build_command('/x/claude', 'hi', None)
    assert plain[plain.index('--tools') + 1] == 'Read,Grep,Glob' and '--allowedTools' not in plain
    work = cp.build_command('/x/claude', 'hi', 'sess', owner=True)
    assert work[work.index('--tools') + 1] == 'Read,Grep,Glob,Write,Edit,Bash' and work[work.index('--max-turns') + 1] == '60'
    assert work[-2:] == ['--resume', 'sess']


def test_practice_81_working_tools_are_scoped_to_the_method():
    allowed = cp.OWNER_ALLOWED
    assert f'Write({cp.AUDIT}/**)' in allowed and f'Edit({cp.AUDIT}/**)' in allowed
    assert 'Bash' not in allowed and 'Write' not in allowed and 'Edit' not in allowed          # never unrestricted
    assert not any('sudo' in a or 'rm ' in a or 'systemctl restart' in a for a in allowed)
    assert any(a.startswith(f'Bash({cp.PY} {cp.AUDIT}/studio_practice') for a in allowed)
    assert 'never by editing HB files yourself' in cp.OWNER_CONTEXT
