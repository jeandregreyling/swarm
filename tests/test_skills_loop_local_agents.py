from agents import skills_loop as sl


def _user(text):
    return [{'role': 'user', 'content': text}]


def test_prose_no_write_does_not_make_turn_read_only():
    relayed = 'Mistral: checkpointing. No write occurs without an active Vortex ID.'
    assert sl._is_explicitly_read_only_task(_user(relayed)) is False


def test_explicit_do_not_edit_is_still_read_only():
    assert sl._is_explicitly_read_only_task(_user('Please do not edit any files.')) is True


def test_only_latest_user_turn_counts():
    msgs = _user('Do not edit anything.') + [{'role': 'assistant', 'content': 'ok'}]
    msgs += _user('Now create the proposal.')
    assert sl._is_explicitly_read_only_task(msgs) is False


def test_bracket_skill_inside_is_executed_as_skill():
    cmds = sl._extract_skill_cmds('[skill:alm_create_proposal "Database Connection Error"]')
    assert cmds == [('alm_create_proposal', '"Database Connection Error"')]


def test_bracket_skill_with_trailing_args_is_executed_as_skill():
    cmds = sl._extract_skill_cmds('[skill:fs_readonly] lines fridays/task_runner.py 1 40')
    assert cmds == [('fs_readonly', 'lines fridays/task_runner.py 1 40')]


def test_echoed_skill_result_is_not_a_command():
    for text in ('[skill:fs_readonly] OK', '[skill:fs_patch_lines] FAILED\nNot authorized'):
        assert sl._extract_skill_cmds(text) == []


def test_plain_skill_line_still_parses():
    cmds = sl._extract_skill_cmds('SKILL fs_readonly lines fridays/task_runner.py 1 40')
    assert cmds == [('fs_readonly', 'lines fridays/task_runner.py 1 40')]


def test_fenced_skill_has_no_trailing_fence_in_args():
    text = '1. Read it.\n```bash\nSKILL fs_readonly lines fridays/task_runner.py 1 60\n```\nDone.'
    assert sl._extract_skill_cmds(text) == [
        ('fs_readonly', 'lines fridays/task_runner.py 1 60'),
    ]


def test_handoff_block_teaches_chain_of_command_and_real_skills():
    from frontend.services.chat_history import _build_chat_handoff_block

    block = _build_chat_handoff_block('gemma', {'latest_sender': 'user'})
    assert 'placeholder' in block
    assert 'CHAIN OF COMMAND' in block
    assert 'SKILL fs_patch_lines <path> <start> <end>' in block
    assert 'approval is open' in block


def test_nudge_example_is_neutral_not_a_magic_number():
    assert 'chat.py 900' not in sl._SKILL_NUDGE
    assert 'SKILL fs_readonly lines docs/sample.md 1 20' in sl._SKILL_NUDGE


def test_literal_agentname_placeholder_is_stripped_in_any_mode():
    from frontend.services.chat_relay import _strip_placeholder_relay

    text = 'AgentName: Please investigate.\nReal finding here.\nAgentName: another'
    assert _strip_placeholder_relay(text) == 'Real finding here.'
    assert _strip_placeholder_relay('Qwen: can you check?') == 'Qwen: can you check?'


def test_fs_readonly_does_not_absorb_echoed_prompt_text():
    text = (
        'SKILL fs_readonly lines fridays/task_runner.py 1 60\n'
        '=== RELAY DISABLED - HARD RULE ===\n'
        'Auto Relay is OFF.'
    )
    assert sl._extract_skill_cmds(text) == [
        ('fs_readonly', 'lines fridays/task_runner.py 1 60'),
    ]


def _run(replies, monkeypatch, ok=True):
    calls = iter(replies)
    monkeypatch.setattr(sl, '_execute_skill_cmds',
                        lambda cmds, *a, **k: '[skill:%s] %s\nProposal ID: 7' % (cmds[0][0], 'OK' if ok else 'FAILED'))
    return sl.run_skill_loop(
        agent_name='qwen', call_fn=lambda m: (next(calls), 1),
        messages=_user('make a proposal'), emit_fn=lambda *_: None,
        max_passes=1, nudge_if_no_skills=False,
    )[0]


def test_trailing_skill_line_is_executed(monkeypatch):
    out = _run(['SKILL alm_create_proposal "T" "D"', 'SKILL alm_create_proposal "T" "D"'], monkeypatch)
    assert 'Proposal ID: 7' in out and '[verification]' not in out


def test_unverified_proposal_claim_is_flagged(monkeypatch):
    out = _run(['I created the proposal, ID 12345.'], monkeypatch)
    assert out.startswith('[verification]')


def test_relay_disabled_block_does_not_make_turn_read_only():
    from utils.chat_prompt_profiles import relay_policy_prefix
    msg = relay_policy_prefix(False) + 'Please create an alm_create_proposal for the README.'
    assert sl._is_explicitly_read_only_task(_user(msg)) is False
    assert sl._is_explicitly_read_only_task(_user(relay_policy_prefix(False) + 'Do not edit anything.')) is True


def test_handoff_block_does_not_trip_read_only_check():
    from frontend.services.chat_history import _build_chat_handoff_block
    block = _build_chat_handoff_block('gemma', {})
    assert sl._READ_ONLY_TASK_RE.search(block) is None


def test_duplicate_proposal_in_same_thread_is_skipped():
    sl._RECENT_PROPOSALS.clear()
    assert sl._is_duplicate_proposal('llama', 99, '"Same title" "d1"') is False
    assert sl._is_duplicate_proposal('llama', 99, '"Same title" "d2"') is True
    assert sl._is_duplicate_proposal('llama', 100, '"Same title" "d1"') is False


def test_look_and_explain_request_is_look_only():
    assert sl._asks_only_to_look(_user('List docs with SKILL fs_readonly ls docs and tell me what you see.')) is True


def test_injected_context_does_not_make_a_look_request_an_action():
    text = '=== CARRY-OVER ===\nplease create and update things\n=== END CARRY-OVER ===\n=== New user message ===\nWhat do you see in docs?'
    assert sl._asks_only_to_look(_user(text)) is True


def test_change_or_proposal_request_is_not_look_only():
    assert sl._asks_only_to_look(_user('Read README.md then raise a proposal.')) is False
    assert sl._asks_only_to_look(_user('Fix the typo on line 3.')) is False


def test_describing_proposals_is_not_a_false_claim():
    calls = iter(['To suggest a change, create a proposal and report the ID. Ghost reviews proposals.'])
    out, _ = sl.run_skill_loop('fred', lambda m: (next(calls), 1), _user('What is a proposal?'), lambda t: None)
    assert '[verification]' not in out


def test_claiming_a_proposal_without_a_skill_is_flagged():
    calls = iter(['I created a proposal, it is INTERNAL-FRED-9999.'])
    out, _ = sl.run_skill_loop('fred', lambda m: (next(calls), 1), _user('Hello'), lambda t: None)
    assert out.startswith('[verification]')


def test_all_asks_reminder_quotes_operator_message_without_injected_blocks():
    from agents.skills_loop import _all_asks_reminder

    msgs = [{'role': 'user', 'content': '=== RELAY ===\nrules\n=== END RELAY ===\n=== New user message ===\n1) say your role 2) list docs'}]
    out = _all_asks_reminder(msgs)
    assert '1) say your role 2) list docs' in out
    assert 'rules' not in out
    assert 'EVERY part' in out
    assert _all_asks_reminder([]) == ''


def test_verification_ignores_proposal_ids_read_from_skill_results():
    import inspect
    from agents import skills_loop

    src = inspect.getsource(skills_loop.run_skill_loop)
    assert 'pid not in joined' in src


def test_read_only_phrase_in_injected_memory_does_not_strip_skills():
    from agents.skills_loop import _is_explicitly_read_only_task

    ctx = 'Remembered rule: never patch a database as text.\n=== New user message ===\nRun SKILL shell uptime'
    assert not _is_explicitly_read_only_task([{'role': 'user', 'content': ctx}])
    assert _is_explicitly_read_only_task([{'role': 'user', 'content': 'Do not edit anything, just look.'}])


def test_level0_shell_allowed_on_read_only_turn():
    from agents.skills_loop import _is_level0_shell

    ro = {'fs_readonly'}
    assert _is_level0_shell('shell', 'python3 scripts/db_query.py "select 1"', ro)
    assert not _is_level0_shell('shell', 'sudo systemctl restart ollama', ro)
    assert not _is_level0_shell('shell', 'uptime', set())
    assert not _is_level0_shell('fs_write', 'x', ro)


def test_bare_db_query_line_becomes_shell_skill():
    from agents.skills_loop import _extract_skill_cmds

    text = '```shell\npython3 scripts/db_query.py "select 1"\n```'
    assert _extract_skill_cmds(text) == [('shell', 'python3 scripts/db_query.py "select 1"')]


def test_proposal_id_from_operator_message_is_not_flagged():
    from agents.skills_loop import run_skill_loop

    msgs = [{'role': 'user', 'content': 'Which project is INTERNAL-FRED-2118 linked to?'}]
    answer, _ = run_skill_loop(
        agent_name='fred',
        call_fn=lambda m: ('INTERNAL-FRED-2118 is linked to P-00221285D1.', 5),
        messages=msgs,
        emit_fn=lambda *_: None,
        max_passes=1,
    )
    assert '[verification]' not in answer


def test_read_only_turn_allows_memory_and_knowledge_lookups():
    from agents.skills_loop import _is_level0_shell
    assert _is_level0_shell('memory_search', 'x', {'fs_readonly'})
    assert _is_level0_shell('swarm_knowledge_search', 'x', {'fs_readonly'})
    assert _is_level0_shell('swarm_knowledge_read', 'x', {'fs_readonly'})
    assert _is_level0_shell('search_landscape', 'x', {'fs_readonly'})
    assert not _is_level0_shell('fs_write', 'x', {'fs_readonly'})
    assert not _is_level0_shell('system_index', 'x', {'fs_readonly'})


def test_studio_step_update_guards(monkeypatch):
    from fridays import skills
    import core.knowledge.projects as pr
    monkeypatch.setattr(pr, 'get_step', lambda sid: {'step_id': sid, 'owner': 'fred', 'status': 'blocked'} if sid == 'S-1' else None)
    calls = []
    monkeypatch.setattr(pr, 'update_step_status', lambda sid, st, **kw: calls.append((sid, st)) or True)
    assert not skills._skill_studio_step_update('S-1 skipped short', 'fred')[0]
    assert not skills._skill_studio_step_update('S-1 bogus a real reason here', 'fred')[0]
    assert not skills._skill_studio_step_update('S-1 skipped a real reason here', 'gemma')[0]
    assert not skills._skill_studio_step_update('S-9 skipped a real reason here', 'fred')[0]
    assert not calls
    assert skills._skill_studio_step_update('S-1 skipped a real reason here', 'fred')[0]
    assert calls == [('S-1', 'skipped')]


def _run_fenced(text):
    from agents.skills_loop import _extract_skill_cmds
    return _extract_skill_cmds(text)


def test_fenced_fs_write_plain_block():
    from fridays.skills import _clean_fs_write_content
    cmds = _run_fenced("SKILL fs_write sandpits/fred/x.md\n```\n# Title\n\nFred works.\nSeven helps.\n```\nDone, thanks.")
    assert len(cmds) == 1 and cmds[0][0] == 'fs_write'
    assert cmds[0][1].split('\n', 1)[0] == 'sandpits/fred/x.md'
    from fridays.skills import split_head_and_blocks
    head, blocks = split_head_and_blocks(cmds[0][1], 1)
    assert head == 'sandpits/fred/x.md'
    assert _clean_fs_write_content(blocks[0][1]).splitlines() == ['# Title', '', 'Fred works.', 'Seven helps.']


def test_fenced_fs_write_nested_markdown_fence():
    text = "SKILL fs_write docs/a.md\n```\nIntro\n```python\nprint(1)\n```\nOutro\n```\nok"
    cmds = _run_fenced(text)
    assert len(cmds) == 1
    assert 'print(1)' in cmds[0][1] and 'Outro' in cmds[0][1]


def test_fenced_patch_skills_keep_the_blocks_raw():
    cmds = _run_fenced("SKILL fs_patch a/b.py\n```old\nx = 1\n```\n```new\nx = 2\n```")
    assert cmds == [('fs_patch', 'a/b.py\n```old\nx = 1\n```\n```new\nx = 2\n```')]
    cmds = _run_fenced("SKILL fs_patch_lines a/b.py 3 4\n```\nline a\nline b\n```")
    assert cmds == [('fs_patch_lines', 'a/b.py 3 4\n```\nline a\nline b\n```')]


def test_file_skills_end_to_end(tmp_path, monkeypatch):
    from agents.skills_loop import _extract_skill_cmds
    from fridays import skills
    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)

    def run(text):
        cmd = _extract_skill_cmds(text)[0]
        return skills._HANDLERS[cmd[0]](cmd[1], 'fred')

    f = tmp_path / 'sandpits' / 'n.md'
    assert run("SKILL fs_write sandpits/n.md\n```\n# T\n\nalpha\nbeta\n```")[0]
    assert f.read_text() == '# T\n\nalpha\nbeta'
    ok, msg = run("SKILL fs_append sandpits/n.md\n```\ngamma\n```")
    assert ok and 'backup' in msg and f.read_text() == '# T\n\nalpha\nbeta\ngamma\n'
    assert run("SKILL fs_insert_after sandpits/n.md\n```\nalpha\n```\n```\nalpha2\n```")[0]
    assert f.read_text() == '# T\n\nalpha\nalpha2\nbeta\ngamma\n'
    assert run("SKILL fs_patch sandpits/n.md\n```old\nbeta\n```\n```new\nBETA\n```")[0]
    assert not run("SKILL fs_patch_lines sandpits/n.md 1 1\n```\n# Title\n```")[0]  # not read yet: refused
    assert run("SKILL fs_readonly lines sandpits/n.md 1 6")[0]
    assert run("SKILL fs_patch_lines sandpits/n.md 1 1\n```\n# Title\n```")[0]
    assert f.read_text().splitlines() == ['# Title', '', 'alpha', 'alpha2', 'BETA', 'gamma']
    assert not run("SKILL fs_insert_after sandpits/n.md\n```\nmissing\n```\n```\nx\n```")[0]
    backups = sorted((tmp_path / 'runtime' / 'backups' / 'fs').iterdir())
    assert len(backups) == 4
    ok, diff = skills._skill_fs_diff(f'runtime/backups/fs/{backups[0].name} sandpits/n.md', 'fred')
    assert ok and '+gamma' in diff


def test_swarm_knowledge_read_returns_full_entry_and_pages(monkeypatch):
    from fridays import skills

    big = 'x' * 3500
    class Row(dict):
        pass
    class Conn:
        def execute(self, *_a, **_k):
            class C:
                def fetchone(_s):
                    return Row(key='K', category='lesson', content=big)
            return C()
        def close(self):
            pass
    monkeypatch.setattr('utils.db._connection.get_connection', lambda: Conn())
    ok, out = skills._skill_swarm_knowledge_read('K', 'fred')
    assert ok and 'of 3500' in out and 'swarm_knowledge_read K 3000' in out
    ok, out = skills._skill_swarm_knowledge_read('K 3000', 'fred')
    assert ok and 'chars 3000-3500' in out and 'more:' not in out
    ok, _ = skills._skill_swarm_knowledge_read('', 'fred')
    assert not ok


def test_fence_with_text_on_the_opening_line_is_accepted():
    from fridays.skills import read_fenced_blocks

    assert read_fenced_blocks(['```one line```'], 0, 1)[0] == [('', 'one line')]
    assert read_fenced_blocks(['```first line', 'second', '```'], 0, 1)[0] == [('', 'first line\nsecond')]
    assert read_fenced_blocks(['```done```'], 0, 1)[0] == [('', 'done')]
    assert read_fenced_blocks(['```python', 'x = 1', '```'], 0, 1)[0] == [('python', 'x = 1')]
    assert read_fenced_blocks(['```never closed'], 0, 1)[0] == []


def test_mid_loop_nudge_can_be_switched_off_for_prose_finishers(monkeypatch):
    monkeypatch.setattr(sl, '_execute_skill_cmds', lambda cmds, *a, **k: '[skill:fs_readonly] OK\nfile text')

    def run(nudges):
        prompts = []
        replies = iter(['SKILL fs_readonly read sandpits/fred/x.md', 'The file says: file text.', 'SKILL fs_readonly grep x y', 'done'])

        def call(msgs):
            prompts.append(msgs[-1]['content'])
            return next(replies, 'done'), 1

        out, _ = sl.run_skill_loop('fred', call, _user('fix the typo in sandpits/fred/x.md'), lambda t: None,
                                   mid_loop_nudges=nudges)
        return out, prompts

    out, prompts = run(0)
    assert not any(p == sl._SKILL_NUDGE for p in prompts)
    assert 'file text' in out
    _, prompts = run(2)
    assert any(p == sl._SKILL_NUDGE for p in prompts)


def test_placeholder_arguments_are_not_executed():
    assert sl._extract_skill_cmds('SKILL fs_readonly read <full/path/to/file>   (files)') == []
    assert sl._extract_skill_cmds('SKILL memory_search <query>   (your own saved memory)') == []
    assert sl._extract_skill_cmds('SKILL shell python3 scripts/db_query.py "select 1 where a<b and c>d"')
    # Real arguments that merely look like tags must still run.
    assert sl._extract_skill_cmds('SKILL search_landscape <body>') == [('search_landscape', '<body>')]
    assert sl._extract_skill_cmds('SKILL fs_readonly grep frontend/templates/terminal_base.html <title>')
    assert sl._extract_skill_cmds('SKILL fs_readonly read <full/path/to/file>') == []
    assert sl._extract_skill_cmds('SKILL swarm_knowledge_search <topic>   (Knowledge Center: decisions)') == []


def test_backtick_wrapped_skill_gets_a_specific_nudge(monkeypatch):
    seen = []
    replies = iter(['```SKILL fs_readonly read sandpits/fred/x.md```\nResult: fake', 'SKILL fs_readonly read sandpits/fred/x.md', 'The file says hi.'])
    monkeypatch.setattr(sl, '_execute_skill_cmds', lambda cmds, *a, **k: '[skill:fs_readonly] OK\nhi')

    def call(msgs):
        seen.append(msgs[-1]['content'])
        return next(replies, 'done'), 1

    out, _ = sl.run_skill_loop('fred', call, _user('read sandpits/fred/x.md with the skill'), lambda t: None,
                               nudge_if_no_skills=True, mid_loop_nudges=0)
    assert sl._FENCED_SKILL_NUDGE in seen
    assert sl._SKILL_NUDGE not in seen
    assert 'fake' not in out


def test_alm_close_proposals_closes_backlog_with_undo_snapshot(tmp_path, monkeypatch):
    import json
    import sqlite3
    from fridays import skills

    db = sqlite3.connect(tmp_path / 't.db')
    db.executescript(
        "CREATE TABLE work_proposals (proposal_id TEXT, status TEXT, queue_id INTEGER, notes TEXT, updated_at TEXT);"
        "CREATE TABLE queue (id INTEGER, status TEXT);"
        "INSERT INTO work_proposals VALUES ('P1','pending',1,NULL,NULL),('P2','approved',2,NULL,NULL),"
        "('P3','in_progress',3,NULL,NULL),('P4','done',4,NULL,NULL),('P5','closed',5,NULL,NULL);"
        "INSERT INTO queue VALUES (1,'queued'),(2,'queued'),(3,'completed'),(4,'queued'),(5,'queued');"
    )
    db.commit()

    class NoClose:
        def __init__(self, c):
            self.c = c
        def execute(self, *a, **k):
            return self.c.execute(*a, **k)
        def commit(self):
            self.c.commit()
        def close(self):
            pass

    monkeypatch.setattr('utils.db._connection.get_connection', lambda: NoClose(db))
    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)

    ok, msg = skills._skill_alm_close_proposals('P1', 'fred')
    assert not ok and 'Usage' in msg

    ok, msg = skills._skill_alm_close_proposals('all clean slate', 'fred')
    assert ok and 'Closed 3 proposals' in msg
    states = dict(db.execute('SELECT proposal_id, status FROM work_proposals').fetchall())
    assert states == {'P1': 'closed', 'P2': 'closed', 'P3': 'closed', 'P4': 'done', 'P5': 'closed'}
    assert dict(db.execute('SELECT id, status FROM queue').fetchall()) == {
        1: 'abandoned', 2: 'abandoned', 3: 'completed', 4: 'queued', 5: 'queued'}
    snap = next((tmp_path / 'runtime' / 'backups' / 'proposals').glob('closed-*.json'))
    assert {p['proposal_id'] for p in json.loads(snap.read_text())['proposals']} == {'P1', 'P2', 'P3'}

    ok, msg = skills._skill_alm_close_proposals('all again', 'fred')
    assert ok and 'Nothing to close' in msg


def test_appended_ticket_snapshot_does_not_make_the_turn_read_only():
    prompt = (
        '=== Shared conversation thread (latest) ===\nNo previous messages.\n\n'
        '=== New user message ===\nPlease close all the proposals now.'
        '\n\n=== Live Ticket Snapshot ===\nQueue: 10\n- INTERNAL-X-1 | gemma | approved/queued | Probe: do not use the old path\n'
    )
    assert sl._is_explicitly_read_only_task(_user(prompt)) is False
    assert sl._latest_operator_text(_user(prompt)) == 'Please close all the proposals now.'
    assert sl._is_explicitly_read_only_task(_user('Do not use any tools.\n\n=== Live Ticket Snapshot ===\nx')) is True


def test_alm_purge_proposals_only_deletes_closed_and_backs_up_full_rows(tmp_path, monkeypatch):
    import json
    import sqlite3
    from fridays import skills

    db = sqlite3.connect(tmp_path / 't.db')
    db.executescript(
        "CREATE TABLE work_proposals (proposal_id TEXT, status TEXT, queue_id INTEGER, title TEXT);"
        "CREATE TABLE queue (id INTEGER, status TEXT);"
        "CREATE TABLE proposal_projects (proposal_id TEXT, project_id TEXT);"
        "CREATE TABLE proposal_attachments (proposal_id TEXT, name TEXT);"
        "CREATE TABLE work_proposal_notes (id INTEGER, proposal_id TEXT, content TEXT);"
        "INSERT INTO work_proposals VALUES ('C1','closed',1,'old one'),('R1','rejected',2,'bad'),"
        "('A1','approved',3,'live'),('D1','done',4,'history');"
        "INSERT INTO queue VALUES (1,'abandoned'),(2,'abandoned'),(3,'queued'),(4,'completed');"
        "INSERT INTO proposal_projects VALUES ('C1','PRJ'),('A1','PRJ');"
        "INSERT INTO work_proposal_notes VALUES (1,'C1','note'),(2,'A1','keep');"
    )
    db.commit()

    class Keep:
        def __init__(self, c):
            self.c = c
        def execute(self, *a, **k):
            return self.c.execute(*a, **k)
        def commit(self):
            self.c.commit()
        def close(self):
            pass

    monkeypatch.setattr('utils.db._connection.get_connection', lambda: Keep(db))
    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)

    assert not skills._skill_alm_purge_proposals('closed', 'fred')[0]
    ok, msg = skills._skill_alm_purge_proposals('A1 try to purge a live one', 'fred')
    assert ok and 'Nothing to purge' in msg
    assert db.execute("SELECT COUNT(*) FROM work_proposals WHERE proposal_id='A1'").fetchone()[0] == 1

    ok, msg = skills._skill_alm_purge_proposals('closed invalid backlog', 'fred')
    assert ok and 'Purged 2 proposals' in msg
    assert [r[0] for r in db.execute('SELECT proposal_id FROM work_proposals ORDER BY 1')] == ['A1', 'D1']
    assert [r[0] for r in db.execute('SELECT id FROM queue ORDER BY 1')] == [3, 4]
    assert db.execute('SELECT proposal_id FROM proposal_projects').fetchall() == [('A1',)]
    assert db.execute('SELECT proposal_id FROM work_proposal_notes').fetchall() == [('A1',)]
    snap = next((tmp_path / 'runtime' / 'backups' / 'proposals').glob('purged-*.json'))
    saved = json.loads(snap.read_text())
    assert {r['proposal_id'] for r in saved['work_proposals']} == {'C1', 'R1'}
    assert saved['work_proposals'][0]['title'] in ('old one', 'bad')
    assert saved['proposal_projects'] == [{'proposal_id': 'C1', 'project_id': 'PRJ'}]


def test_fs_readonly_grep_searches_a_folder_and_hints_ls_on_bad_paths(tmp_path, monkeypatch):
    from fridays import skills

    (tmp_path / 'css').mkdir()
    (tmp_path / 'css' / 'a.css').write_text('#shortcuts-panel { position: fixed; }\n')
    (tmp_path / 'css' / 'b.css').write_text('.other { color: red; }\n')
    (tmp_path / 'css' / 'c.css.bak').write_text('shortcuts old\n')
    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'x.py').write_text('shortcuts\n')
    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)
    monkeypatch.setattr(skills, '_fs_safe_path', lambda rel: (tmp_path / rel).resolve() if (tmp_path / rel).exists() else None)

    ok, out = skills._skill_fs_readonly('grep css shortcuts', 'fred')
    assert ok and 'css/a.css:1:' in out and 'b.css' not in out and '.bak' not in out and 'pycache' not in out
    ok, out = skills._skill_fs_readonly('grep . shortcuts', 'fred')
    assert ok and '__pycache__' not in out
    ok, out = skills._skill_fs_readonly('grep css nothingthere', 'fred')
    assert ok and 'No matches' in out
    ok, out = skills._skill_fs_readonly('grep css/missing.css x', 'fred')
    assert not ok and 'ls <folder>' in out
    ok, out = skills._skill_fs_readonly('read docs/Freddy/Page.md', 'fred')
    assert not ok and 'search_landscape' in out


def test_search_landscape_falls_back_to_all_the_words(tmp_path, monkeypatch):
    import json
    from fridays import skills

    root = tmp_path / 'swarm_docs'
    root.mkdir()
    (root / 'SYSTEM_LANDSCAPE.json').write_text(json.dumps({
        'ui_elements': [{'id': 'chat-topbar-title', 'file': 'a.js'}, {'id': 'taskbar-btn', 'file': 'b.html'}]}))
    monkeypatch.setattr(skills.os.path, 'abspath', lambda p: str(tmp_path / 'fridays' / 'skills.py'))
    ok, out = skills._skill_search_landscape('chat bar', 'fred')
    assert ok and 'chat-topbar-title' in out and 'taskbar-btn' not in out
    ok, out = skills._skill_search_landscape('nothing like this', 'fred')
    assert ok and 'No landscape matches' in out and 'one code word' in out


def test_write_skills_show_the_real_lines_they_changed(tmp_path, monkeypatch):
    from fridays import skills

    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)
    monkeypatch.setattr(skills, '_fs_safe_path', lambda rel: (tmp_path / rel).resolve())
    monkeypatch.setattr(skills, '_fs_write_refusal', lambda *a, **k: None)
    monkeypatch.setattr(skills, '_fs_backup', lambda *a, **k: '')
    page = tmp_path / 'p.html'
    page.write_text('<style>\n  --accent: #2f6bff;\n</style>\n<body>\n<div></div>\n')

    assert skills._skill_fs_readonly('lines p.html 1 5', 'fred')[0]
    ok, msg = skills._skill_fs_patch_lines('p.html 2 2\n```\n<!-- wrong place -->\n```', 'fred')
    assert ok and '"  --accent: #2f6bff;"' in msg and '2 >>> <!-- wrong place -->' in msg

    page.write_text('<style>\n  --accent: #2f6bff;\n</style>\n<body>\n<div></div>\n')
    ok, msg = skills._skill_fs_insert_after('p.html\n```\n<body>\n```\n```\n<!-- right place -->\n```', 'fred')
    assert ok and '5 >>> <!-- right place -->' in msg and '4     <body>' in msg
    assert page.read_text().splitlines()[4] == '<!-- right place -->'

    ok, msg = skills._skill_fs_append('p.html\n```\nlast line\n```', 'fred')
    assert ok and '>>> last line' in msg


def test_line_patch_needs_the_lines_to_have_been_read(tmp_path, monkeypatch):
    from fridays import skills

    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)
    monkeypatch.setattr(skills, '_fs_safe_path', lambda rel: (tmp_path / rel).resolve())
    monkeypatch.setattr(skills, '_fs_write_refusal', lambda *a, **k: None)
    monkeypatch.setattr(skills, '_fs_backup', lambda *a, **k: '')
    skills._SEEN_LINES.clear()
    page = tmp_path / 'p.html'
    page.write_text('\n'.join(f'line {n}' for n in range(1, 61)) + '\n')

    ok, msg = skills._skill_fs_patch_lines('p.html 52 52\n```\nX\n```', 'apex')
    assert not ok and 'have not read lines 52-52' in msg and 'fs_insert_after' in msg
    assert 'line 52' in page.read_text()

    skills._skill_fs_readonly('lines p.html 1 50', 'apex')
    assert not skills._skill_fs_patch_lines('p.html 52 52\n```\nX\n```', 'apex')[0]
    assert not skills._skill_fs_patch_lines('p.html 52 52\n```\nX\n```', 'other')[0]
    skills._skill_fs_readonly('grep p.html 52 1', 'apex')
    ok, msg = skills._skill_fs_patch_lines('p.html 52 52\n```\nX\n```', 'apex')
    assert ok and 'It replaced these original lines: "line 52"' in msg


def test_single_space_line_numbers_are_stripped_only_when_they_count_up():
    from fridays.skills import _strip_fs_readonly_line_numbers as strip

    assert strip('21 <body>\n22 <!-- c -->') == '<body>\n<!-- c -->'
    assert strip('10 apples\n12 pears') == '10 apples\n12 pears'
    assert strip('3 only one line') == '3 only one line'
