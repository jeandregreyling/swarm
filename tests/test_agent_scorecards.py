import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_agent_scorecards_seed_and_select_best_agent(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "scorecards.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    assert agent_scorecards.seed_default_scorecards() >= 1
    assert agent_scorecards.best_agent_for_capability("sap") == "eight"
    assert agent_scorecards.best_agent_for_capability("payroll") == "eight"
    assert agent_scorecards.best_agent_for_capability("coding") == "ten"

    block = agent_scorecards.scorecard_context_block(
        capabilities=["coding", "sap_payroll"],
        limit=4,
    )

    assert "=== Agent capability scorecards ===" in block
    assert "coding: ten" in block
    assert "sap_payroll: eight" in block


def test_agent_scorecards_record_result_creates_learning_signal(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "scorecard-learning.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    result = agent_scorecards.record_capability_result(
        "llama",
        "coding",
        success=True,
        quality_delta=0.2,
        source="test",
        notes="Handled a local coding task well.",
    )

    assert result["agent"] == "llama"
    assert result["capability"] == "coding"
    assert result["score"] > 0.55
    assert result["evidence_count"] == 1
    assert agent_scorecards.best_agent_for_capability("coding", candidates=["llama"]) == "llama"


def test_fridays_dispatch_uses_capability_scorecards(tmp_path, monkeypatch):
    import fridays.orchestrator as fridays_orchestrator

    db_path = tmp_path / "dispatch-scorecards.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    coding_route = fridays_orchestrator._naive_route({
        "title": "Implement integration improvement",
        "description": "Code the next Studio routing fix.",
        "agent": "gemma",
    })
    sap_route = fridays_orchestrator._naive_route({
        "title": "Research SAP payroll Australia",
        "description": "Find authoritative payroll updates.",
        "agent": "gemma",
    })

    assert coding_route == "ten"
    assert sap_route == "eight"


def test_task_outcome_records_watched_research_learning_signal(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "task-outcome-research.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    updates = agent_scorecards.record_task_outcome(
        "interest_research_update",
        args='topic="SAP payroll Australia" agent=eight depth=quick',
        success=True,
        output=(
            "Research session 7 found 1 qualified new evidence item(s) "
            "for 'SAP payroll Australia'; email sent."
        ),
    )

    assert {item["capability"] for item in updates} == {"research", "sap_payroll"}
    sap = agent_scorecards.list_scorecards(capability="sap_payroll", agents=["eight"], limit=1)[0]
    research = agent_scorecards.list_scorecards(capability="research", agents=["eight"], limit=1)[0]
    assert sap["evidence_count"] == 2
    assert sap["source"] == "tasker:interest_research_update"
    assert research["evidence_count"] == 1


def test_task_outcome_ignores_watched_research_without_qualified_email(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "task-outcome-empty-research.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    updates = agent_scorecards.record_task_outcome(
        "interest_research_update",
        args='topic="SAP payroll Australia" agent=eight',
        success=True,
        output=(
            "Research session 8 found 1 new evidence item(s) for "
            "'SAP payroll Australia', but none met quality/novelty thresholds; no email sent."
        ),
    )

    assert updates == []


def test_task_outcome_records_relay_recovery_learning_signal(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "task-outcome-recovery.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    updates = agent_scorecards.record_task_outcome(
        "relay_recovery_sweep",
        args="limit=1 run_agents=1 agents=librarian,duck force=1",
        success=True,
        output="Reviewed 1 relay recoveries: recovery-active (0.1s)",
    )

    assert [(item["agent"], item["capability"]) for item in updates] == [
        ("librarian", "recovery"),
        ("duck", "recovery"),
    ]
    duck = agent_scorecards.list_scorecards(capability="recovery", agents=["duck"], limit=1)[0]
    librarian = agent_scorecards.list_scorecards(capability="recovery", agents=["librarian"], limit=1)[0]
    assert duck["evidence_count"] == 2
    assert librarian["evidence_count"] == 2


def test_task_runner_auto_records_scorecard_for_meaningful_task(tmp_path, monkeypatch):
    import fridays.task_runner as task_runner
    from core import agent_scorecards

    db_path = tmp_path / "task-runner-auto-scorecard.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)
    monkeypatch.setattr(task_runner, "_log_run", lambda *a, **k: None)

    @task_runner.register("_scorecard_test_task", "test-only scorecard task", "knowledge")
    def _scorecard_test_task(**kwargs):
        return "Research session 9 found 1 qualified new evidence item(s) for 'SAP payroll Australia'; email sent."

    try:
        ok, msg = task_runner.run_task(
            "_scorecard_test_task",
            args='topic="SAP payroll Australia" agent=eight',
        )
    finally:
        task_runner.TASK_REGISTRY.pop("_scorecard_test_task", None)

    assert ok is True
    assert "qualified new evidence" in msg
    seeded = agent_scorecards.list_scorecards(capability="sap_payroll", agents=["eight"], limit=1)[0]
    assert seeded["evidence_count"] == 1
    assert seeded["source"] == "seed"

    # Only known meaningful task names are allowed to teach the scorecard.
    task_runner._record_scorecard_outcome(
        "interest_research_update",
        'topic="SAP payroll Australia" agent=eight',
        True,
        "Research session 9 found 1 qualified new evidence item(s) for 'SAP payroll Australia'; email sent.",
        "knowledge",
    )
    assert agent_scorecards.list_scorecards(capability="sap_payroll", agents=["eight"], limit=1)[0]["evidence_count"] == 2


def test_duck_proposal_outcome_teaches_audit_and_builder_quality(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "duck-proposal-scorecards.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)

    updates = agent_scorecards.record_duck_proposal_outcome(
        proposal_id="P-DUCK-1",
        title="Implement watched topic review",
        agent="mistral",
        phase="qa",
        verdict="fail",
    )

    assert [(item["agent"], item["capability"]) for item in updates] == [
        ("duck", "audit"),
        ("mistral", "coding"),
    ]
    duck = agent_scorecards.list_scorecards(capability="audit", agents=["duck"], limit=1)[0]
    mistral = agent_scorecards.list_scorecards(capability="coding", agents=["mistral"], limit=1)[0]
    assert duck["source"] == "proposal:duck_qa"
    assert duck["evidence_count"] == 2
    assert mistral["source"] == "proposal:duck_qa"
    assert mistral["score"] < 0.55


def test_test_run_outcome_teaches_linked_proposal_agent(tmp_path, monkeypatch):
    from core import agent_scorecards

    db_path = tmp_path / "testlab-scorecards.db"

    def get_conn():
        return _connect(db_path)

    monkeypatch.setattr("utils.db._connection.get_connection", get_conn)
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE work_proposals (
                proposal_id TEXT PRIMARY KEY,
                ticket_number TEXT DEFAULT '',
                title TEXT DEFAULT '',
                agent TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            """INSERT INTO work_proposals
               (proposal_id, ticket_number, title, agent)
               VALUES ('P-TESTLAB-1', '1306', 'Code integration upgrade', 'ten')"""
        )
        conn.commit()

    updates = agent_scorecards.record_test_run_outcome(
        script_id="pytest-focused",
        status="pass",
        change_id="P-TESTLAB-1",
        triggered_by="change:P-TESTLAB-1",
        exit_code=0,
        stdout_tail="12 passed",
    )

    assert [(item["agent"], item["capability"]) for item in updates] == [
        ("ten", "testing"),
        ("ten", "coding"),
    ]
    testing = agent_scorecards.list_scorecards(capability="testing", agents=["ten"], limit=1)[0]
    coding = agent_scorecards.list_scorecards(capability="coding", agents=["ten"], limit=1)[0]
    assert testing["source"] == "testlab:run"
    assert coding["source"] == "testlab:run"
    assert coding["score"] > 0.85
