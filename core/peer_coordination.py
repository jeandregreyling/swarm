"""HB-owned supervision of fixed peer workers; no model-selected commands."""
from contextlib import closing
import fcntl
import logging
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

from core import agent_identity
from utils.db._connection import get_connection

LOG = logging.getLogger(__name__)
AGENTS = ('codex-instructor', 'apex', 'gemini-advisor', 'claude-code')
ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'completed', 'failed', 'needs_review'}


def worker_alive(agent):
    path = agent_identity.STATE / agent / 'hb-worker.lock'
    try:
        with path.open('r') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
    except FileNotFoundError:
        pass
    return False


def reconcile(conn, agent):
    """Import terminal legacy worker outcomes without executing or acknowledging them."""
    path = agent_identity.STATE / agent / 'hb-worker.sqlite'
    if not path.is_file() or path.is_symlink():
        return
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as worker:
        if not worker.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone():
            return
        rows = worker.execute("SELECT request_id,state,error FROM jobs WHERE state IN ('completed','failed','needs_review')").fetchall()
    for request_id, state, error in rows:
        if not conn.execute('SELECT 1 FROM peer_messages WHERE id=? AND recipient=?', (request_id, agent)).fetchone():
            continue
        conn.execute('''INSERT INTO hb_peer_work VALUES(?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET principal=excluded.principal,state=excluded.state,stage=excluded.stage,updated_at=excluded.updated_at WHERE hb_peer_work.state<>'cancelled' AND (hb_peer_work.state<>excluded.state OR hb_peer_work.stage<>excluded.stage)''',
                     (request_id, agent, state, str(error or 'Worker saved and verified its reply')[:200], time.time()))


def retire_pending(conn, cutoff, reason):
    """Cut over old unfinished work without treating it as delivered or executing it."""
    for agent in AGENTS:
        reconcile(conn, agent)
    conn.execute('''INSERT OR REPLACE INTO hb_peer_work
        SELECT m.id,m.recipient,'needs_review',?,? FROM peer_messages m
        LEFT JOIN hb_peer_work w ON w.request_id=m.id
        WHERE m.id<=? AND m.recipient IN ('apex','codex-instructor') AND m.delivered_at IS NULL
        AND COALESCE(w.state,'queued') NOT IN ('completed','failed','needs_review','cancelled')''',
                 (reason, time.time(), cutoff))


def status(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_workers'").fetchone():
        return []
    return [dict(zip(('agent','state','detail','updated_at'), row)) for row in conn.execute(
        'SELECT principal,state,detail,updated_at FROM hb_peer_workers ORDER BY principal')]


class Supervisor:
    def __init__(self, *, launch=None, alive=worker_alive, clock=time.monotonic):
        self.launch = launch or self._launch
        self.alive = alive
        self.clock = clock
        self.attempts = {}

    def _launch(self, agent):
        folder = agent_identity.directory(agent)
        if agent == 'gemini-advisor':
            boundary = folder/'hb-pickup-boundary.json'
            if boundary.is_symlink() or not boundary.is_file():
                raise OSError('Gemini pickup boundary is not configured')
            try:
                cutoff = json.loads(boundary.read_text()).get('after_request_id')
            except (ValueError, AttributeError) as exc:
                raise OSError('Invalid Gemini pickup boundary') from exc
            if type(cutoff) is not int or cutoff < 0:
                raise OSError('Invalid Gemini pickup boundary')
            command = [sys.executable, str(ROOT/'scripts/hummingbird_gemini_peer.py'), '--after', str(cutoff)]
        elif agent == 'claude-code':
            command = [sys.executable, str(ROOT/'scripts/hummingbird_claude_peer.py')]
        else:
            command = [sys.executable, str(ROOT/'scripts/hummingbird_peer_worker.py'), '--agent', agent]
        with (folder / 'hb-supervised-worker.log').open('ab') as output:
            return subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, close_fds=True)

    def tick(self, conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS hb_peer_workers(
            principal TEXT PRIMARY KEY,state TEXT,detail TEXT,updated_at REAL)''')
        for agent in AGENTS:
            enabled = conn.execute('SELECT enabled FROM service_principals WHERE id=?', (agent,)).fetchone()
            if not enabled or not enabled[0]:
                continue
            reconcile(conn, agent)
            if self.alive(agent):
                self.attempts.pop(agent, None)
                state, detail = 'running', 'HB peer worker holds its singleton lock'
            else:
                # An interrupted request can include side effects. Never replay it silently.
                conn.execute("UPDATE hb_peer_work SET state='needs_review',stage=?,updated_at=? WHERE principal=? AND state='running'",
                    ('Worker disconnected during a turn; recorded results require review', time.time(), agent))
                previous = self.attempts.get(agent)
                if previous and self.clock() - previous[0] < 30:
                    state, detail = 'starting', 'HB is waiting for worker startup'
                else:
                    count = previous[1] if previous else 0
                    if count >= 3:
                        state, detail = 'unavailable', 'HB peer worker failed to start after three attempts; inspect hb-supervised-worker.log'
                        pending = conn.execute("SELECT w.request_id,m.conversation_id FROM hb_peer_work w JOIN peer_messages m ON m.id=w.request_id WHERE w.principal=? AND w.state='queued'", (agent,)).fetchall()
                        for request_id, conversation_id in pending:
                            conn.execute("UPDATE hb_peer_work SET state='failed',stage=?,updated_at=? WHERE request_id=?", (detail, time.time(), request_id))
                            conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'system',0)",
                                (conversation_id, f'HB could not deliver request {request_id} to {agent}: {detail}. No successful reply was recorded.'))
                    else:
                        try:
                            self.launch(agent)
                            state, detail = 'starting', 'HB started its peer worker; awaiting pickup'
                        except OSError as exc:
                            state, detail = 'starting', 'HB worker launch failed: ' + type(exc).__name__
                        self.attempts[agent] = (self.clock(), count + 1)
            conn.execute('INSERT OR REPLACE INTO hb_peer_workers VALUES (?,?,?,?)',
                         (agent, state, detail, time.time()))


def start():
    if not agent_identity.enabled():
        return
    # All wrapper processes share one supervisor. Existing systemd workers are
    # recognized by their own locks, so a healthy worker is never duplicated.
    lock = (agent_identity.STATE / 'hb-coordinator.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return
    def run():
        supervisor = Supervisor()
        try:
            while True:
                try:
                    from core.hb_executions import stop_held_executors
                    stop_held_executors()
                    from core.peer_bridge import ensure_schema
                    with closing(get_connection()) as conn, conn:
                        ensure_schema(conn)
                        supervisor.tick(conn)
                        from core.hb_task_manager import tick as task_tick
                        from core.hb_workflow import memory_snapshot
                        task_tick(conn,memory=memory_snapshot)
                        conn.commit()  # optional ticks below can only roll back their own work
                        try:  # Plan workflow: one Studio step at a time, scoped by APEX, approved by the owner
                            from core.hb_plan_workflow import tick as workflow_tick
                            with conn:
                                workflow_tick(conn)
                        except Exception:
                            LOG.exception('Plan workflow tick failed')
                        conn.commit()
                        try:  # DREAM: off until the owner enables it; facts-only report, never blocks coordination
                            from core.hb_dream_cycle import tick as dream_tick
                            with conn:
                                dream_tick(conn)
                        except Exception:
                            LOG.exception('DREAM tick failed')
                        conn.commit()
                        try:  # DOES: save and index every chat message and task record in the KC
                            from core.hb_kc_records import tick as kc_tick
                            from core.hb_tasks import sync_studio_steps
                            from core.hb_commands import close_finished_reviews
                            with conn:
                                kc_tick(conn)
                                sync_studio_steps(conn)      # finished HB tasks close their auto Studio step
                                from core.hb_tasks import close_tasks_of_closed_steps
                                close_tasks_of_closed_steps(conn)  # and a Studio step closed elsewhere closes its HB task
                                close_finished_reviews(conn)  # held requests of finished/cancelled tasks are closed, not shown
                        except Exception:
                            LOG.exception('DOES KC indexing failed')
                        conn.commit()
                        try:  # B38: HB manages its own model servers (duplicates, idle, GPU pressure) once a minute
                            from core.hb_hardware import housekeeping_tick
                            housekeeping_tick()
                        except Exception:
                            LOG.exception('Model housekeeping failed')
                        try:  # Owner 14 Nov: online agents checked at startup and every few minutes (core/hb_online.py)
                            from core.hb_online import tick as online_tick
                            with conn:
                                online_tick(conn)
                        except Exception:
                            LOG.exception('Online status check failed')
                        try:  # Owner 14 Nov: HB never repeats itself to JD (database trigger, core/hb_loop_guard.py)
                            from core.hb_loop_guard import install as install_loop_guard
                            with conn:
                                install_loop_guard(conn)
                        except Exception:
                            LOG.exception('Loop guard install failed')
                        try:  # Owner 14 Nov: each onboarded agent's memories mirrored into its KC page
                            from core.hb_agents import kc_tick as agents_kc_tick
                            with conn:
                                agents_kc_tick(conn)
                        except Exception:
                            LOG.exception('Agent KC mirror failed')
                        try:  # Owner 14 Nov: model benchmark requests (/bench) run inside HB so main chat shows them
                            from core.hb_model_bench import tick as bench_tick
                            bench_tick(conn)
                        except Exception:
                            LOG.exception('Benchmark tick failed')
                        try:  # Owner 14 Nov: HB counsel looks into vague steps and proposes options (core/hb_counsel.py)
                            from core.hb_counsel import tick as counsel_tick
                            counsel_tick(conn)
                        except Exception:
                            LOG.exception('Counsel tick failed')
                        try:  # Owner 14 Nov: advisors' Studio proposals are checked by HB (their test), then go to APEX
                            from core.hb_proposals import tick as proposals_tick
                            proposals_tick(conn)
                        except Exception:
                            LOG.exception('Proposal check tick failed')
                        try:  # Owner 14 Nov: corrections recorded as lessons, daily thank-you (core/hb_merits.py)
                            from core.hb_merits import tick as merits_tick
                            with conn:
                                merits_tick(conn)
                        except Exception:
                            LOG.exception('Merits tick failed')
                        try:  # Owner 14 Nov: big downloads show their progress in main chat
                            from core.hb_downloads import tick as downloads_tick
                            with conn:
                                downloads_tick(conn)
                        except Exception:
                            LOG.exception('Downloads tick failed')
                        try:  # Owner 14 Nov: homework on the CPU - spec cards for the coming tasks, one at a time, own thread
                            from core.hb_homework import tick as homework_tick
                            homework_tick(conn)
                        except Exception:
                            LOG.exception('Homework tick failed')
                        try:  # Nanny bot: off until the owner turns it on; its check runs in its own thread
                            from core.hb_nanny_bot import tick as nanny_tick
                            with conn:
                                nanny_tick(conn)
                        except Exception:
                            LOG.exception('Nanny tick failed')
                        from core.hb_runtime_reload import tick as reload_tick
                        reload_tick(conn)
                    from core.hb_tasks import flush_memory
                    flush_memory()
                    from core.hb_local_jobs import supervise
                    supervise()
                    from core.hb_provider_conditions import probe_codex_capacity
                    probe_codex_capacity()
                except Exception:
                    LOG.exception('HB peer coordination failed')
                time.sleep(5)
        finally:
            lock.close()
    threading.Thread(target=run, name='hb-peer-coordinator', daemon=True).start()
