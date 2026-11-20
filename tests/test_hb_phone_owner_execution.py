"""Trusted phone controls resume scoped tasks, preserving holds and parser safety."""
import json
import pytest
from core import hb_channels as c, hb_tasks, hb_task_manager, hb_commands, hb_chat_controls
from test_hb_plan_workflow import plan, P  # noqa: F401
from test_peer_turns import flow  # noqa: F401
from test_practice_193_channels import conn  # noqa: F401


def test_invalid_phone_command_uses_parser_without_index_error(conn):
    assert isinstance(c.inbound(conn,'telegram','telegram:999','JD','/continue'),str)


def test_cancel_requires_existing_confirmation_and_has_no_immediate_side_effect(conn,monkeypatch):
    calls=[]
    hb_tasks.ensure_schema(conn)
    monkeypatch.setattr(hb_commands,'_open_tasks',lambda *a:[])
    monkeypatch.setattr(hb_commands,'run',lambda *a,**k:calls.append(a[2]) or 'executed')
    out=c.inbound(conn,'telegram','telegram:999','JD','/cancel T-0123456789AB')
    assert 'Reply /yes or /no' in out and calls==[]
    assert 'Running /cancel' in c.inbound(conn,'telegram','telegram:999','JD','/yes')
    assert calls==['cancel']


def test_command_callbacks_run_after_commit(conn):
    def command(db,chat,verb,args,actor,after):
        db.execute("INSERT INTO hb_channel_cursor VALUES ('callback-test','ok')")
        after.append(lambda:pytest.fail('DB transaction held') if db.in_transaction else None)
        return 'okay'
    assert c.inbound(conn,'telegram','telegram:999','JD','/help',commands=command)=='okay'


def prepared_task(plan,monkeypatch):
    db,principals,tasks=plan
    monkeypatch.setattr(c,'_chat',lambda _:1)
    c.ensure(db)
    db.execute("INSERT INTO hb_channel_identities VALUES ('telegram:999','owner','JD','test',1)")
    tid=tasks['S-00000000A1'];task=hb_tasks.get(db,tid)
    from core.hb_dream_method import set_done
    set_done(db,task,['The bounded step passes tests/test_hb_learning.py'], 'JD')
    hb_task_manager.register(db,task,next_action='Inspect the prepared step and run the saved complete check.')
    hb_chat_controls.set_continuation(db,task,{'mode':'on','message_id':task['root_message_id'],'version':task['version'],'revision':0,'command_id':'phone-test-enable-0123456789'},'JD')
    monkeypatch.setattr('core.apex_permissions.autonomous_writes_allowed',lambda who:True)
    db.commit()
    return db,tid


def test_repeat_resume_reuses_task_and_deduplicates_live_requests(plan,monkeypatch):
    db,tid=prepared_task(plan,monkeypatch)
    before=db.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]
    assert 'now On' in c.inbound(db,'telegram','telegram:999','JD','Continue '+tid)
    requests=db.execute('SELECT COUNT(*) FROM hb_task_requests WHERE task_id=?',(tid,)).fetchone()[0]
    c.inbound(db,'telegram','telegram:999','JD','Continue '+tid)
    assert db.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==before
    assert db.execute('SELECT COUNT(*) FROM hb_task_requests WHERE task_id=?',(tid,)).fetchone()[0]==requests
    assert requests>=1


def test_prose_does_not_clear_explicit_hold(plan,monkeypatch):
    db,tid=prepared_task(plan,monkeypatch)
    hb_commands.run(db,1,'pause',[tid],'JD')
    before=db.execute('SELECT COUNT(*) FROM hb_task_requests WHERE task_id=?',(tid,)).fetchone()[0]
    out=c.inbound(db,'telegram','telegram:999','JD','Continue '+tid)
    assert 'hold is preserved' in out
    assert hb_chat_controls.continuation(db,hb_tasks.get(db,tid))['mode']=='off'
    assert db.execute('SELECT COUNT(*) FROM hb_task_requests WHERE task_id=?',(tid,)).fetchone()[0]==before


def test_missing_standing_grant_does_not_manufacture_authority(plan,monkeypatch):
    db,tid=prepared_task(plan,monkeypatch)
    monkeypatch.setattr('core.apex_permissions.autonomous_writes_allowed',lambda who:False)
    assert 'no active recorded execution grant' in c.inbound(db,'telegram','telegram:999','JD','Continue '+tid)


def test_completed_task_is_reported_without_reexecution(plan,monkeypatch):
    db,tid=prepared_task(plan,monkeypatch)
    db.execute("UPDATE hb_tasks SET state='completed' WHERE task_id=?",(tid,))
    assert 'already completed' in c.inbound(db,'telegram','telegram:999','JD','Continue '+tid)


def test_enrolled_user_work_text_stays_in_answer_lane(conn,monkeypatch):
    monkeypatch.setattr(c,'_owner_operating_request',lambda *a:pytest.fail('non-owner controlled work'))
    assert 'APEX is on it' in c.inbound(conn,'telegram','telegram:111','friend','Continue T-0123456789AB')


def test_unknown_id_and_mixed_new_work_cannot_create_task(plan,monkeypatch):
    db,tid=prepared_task(plan,monkeypatch)
    before=db.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]
    assert 'No matching' in c.inbound(db,'telegram','telegram:999','JD','Continue T-FFFFFFFFFFFF')
    assert 'APEX is on it' in c.inbound(db,'telegram','telegram:999','JD','Fix core/unrelated.py and continue '+tid)
    assert db.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==before
