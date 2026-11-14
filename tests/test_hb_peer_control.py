import sqlite3
from pathlib import Path
from contextlib import closing
import pytest
from core import hb_peer_control as control,agent_identity
from test_hb_task_api import assigned,invoke
from test_agent_identity import api,enrolled,connect,headers

# Owner rules since 11-12 Nov stated explicitly (see conftest).
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



def setup(assigned,monkeypatch):
    _,_,path,rid,task=assigned
    monkeypatch.setattr(control,'get_connection',lambda:connect(path))
    monkeypatch.setattr(control,'_gemini_pids',lambda:[12345])
    calls=[];monkeypatch.setattr(control.os,'kill',lambda pid,sig:calls.append((pid,sig)))
    return path,calls


def test_reload_uses_fixed_owned_worker_and_records_authenticated_receipt(assigned,monkeypatch):
    path,calls=setup(assigned,monkeypatch)
    result=invoke(assigned,'gemini_reload',{})
    assert result.status_code==200,result.get_json()
    assert calls==[(12345,control.signal.SIGTERM)]
    assert 'restart_requested' in result.get_json()['output']
    with closing(connect(path)) as c:
        assert c.execute("SELECT 1 FROM hb_task_events WHERE kind='tool_result' AND payload LIKE '%gemini_reload%'").fetchone()


def test_reload_never_interrupts_provider_request(assigned,monkeypatch):
    path,calls=setup(assigned,monkeypatch)
    with closing(connect(path)) as c,c:
        c.execute("INSERT INTO hb_peer_work VALUES(999,'gemini-advisor','running','provider call',0)")
    result=invoke(assigned,'gemini_reload',{})
    assert result.status_code==400 and not calls


def test_reload_rejects_arbitrary_parameters_and_duplicate_workers(assigned,monkeypatch):
    _,calls=setup(assigned,monkeypatch)
    assert invoke(assigned,'gemini_reload',{'pid':1}).status_code==400
    monkeypatch.setattr(control,'_gemini_pids',lambda:[12345,12346])
    # No fake process is actually signalled, even if supervision is inconsistent.
    token=agent_identity.CURRENT.set({'principal':'apex','peer_request_id':assigned[3],'conversation_id':1})
    try:
        with pytest.raises(RuntimeError,match='Multiple Gemini'):control.gemini_reload({})
    finally:agent_identity.CURRENT.reset(token)
    assert not calls


def test_apex_can_select_only_the_host_verified_flash_endpoint(assigned,monkeypatch):
    _,calls=setup(assigned,monkeypatch)
    result=invoke(assigned,'gemini_reload',{'provider_model':'gemini-4-argon'})
    assert result.status_code==200,result.get_json()
    assert calls==[(12345,control.signal.SIGTERM)]
    from scripts.hummingbird_gemini_peer import selected_provider_model
    assert selected_provider_model('configured-primary')=='gemini-4-argon'
    assert invoke(assigned,'gemini_reload',{'provider_model':'unapproved-model'}).status_code==400
    assert invoke(assigned,'gemini_reload',{'provider_model':'gemini-4-argon'}).status_code==400
    assert len(calls)==1
