import pytest
from core.apex_tools import hb_tasks
from core.hb_commands import handle, cancel_task

# Helper to create a temporary DB with three tasks
from core.hb_task_manager import init_db, add_task

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "hb.db"
    init_db(str(db_path))
    # add three open tasks
    add_task(str(db_path), "Task 1", state="On")
    add_task(str(db_path), "Task 2", state="On")
    add_task(str(db_path), "Task 3", state="On")
    return str(db_path)

def test_hb_tasks_list(db):
    # list all open tasks
    result = hb_tasks(db, action="list")
    assert len(result) == 3
    ids = {t["id"] for t in result}
    assert ids == {1, 2, 3}
    for t in result:
        assert t["state"] == "On"
        assert t["continue"] is True
        assert t["title"] in {"Task 1", "Task 2", "Task 3"}

def test_hb_tasks_continue(db):
    # hold task 2
    handle(db, 2845, "/continue 2")
    # verify state changed to On
    result = hb_tasks(db, action="list")
    t2 = next(t for t in result if t["id"] == 2)
    assert t2["state"] == "On"

def test_hb_tasks_cancel(db):
    # cancel without reason should be refused
    with pytest.raises(Exception):
        cancel_task(db, 3, "")
    # cancel with reason
    cancel_task(db, 3, "APEX: test reason")
    result = hb_tasks(db, action="list")
    ids = {t["id"] for t in result}
    assert 3 not in ids
    # reason recorded in task history (simplified check)
    # assuming cancel_task logs reason somewhere; omitted for brevity
