from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_BP = ROOT / "frontend" / "blueprints" / "chat.py"


def test_sequential_mode_disables_multi_agent_fanout_for_local_backlog_guard():
    src = CHAT_BP.read_text(encoding="utf-8")
    assert "_multi_agent_fanout = bool(parallel_mode) and len(runnable_agents) > 1" in src
    assert "Sequential mode is the safe default for local workers." in src
