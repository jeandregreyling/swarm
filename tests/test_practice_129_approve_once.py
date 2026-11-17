"""Practice 129 (owner 17 Nov 2026): Practice 128 got two "Done" messages - HB's auto-approve and JD's Approve both read the step as
not done before either was saved. The approval that loses the race now says "already accepted" and posts and records nothing."""
from core import hb_commands as hc
from test_peer_turns import flow  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401


class Stale:
    """The connection of the second approver: its first look at the step still sees it unfinished."""
    def __init__(self, conn):
        self.conn, self.first = conn, True

    def execute(self, sql, *a):
        if self.first and sql.startswith('SELECT status, title FROM project_steps'):
            self.first = False
            return self.conn.execute("SELECT 'review', title FROM project_steps WHERE step_id=?", *a)
        return self.conn.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def test_practice_129_a_step_is_approved_once(plan):
    conn, _, _ = plan
    hc.accept_step(conn, 'S-00000000A2', 'HB auto-approve (owner policy)', 'Approved automatically.')
    before = conn.execute("SELECT residual_risk FROM project_steps WHERE step_id='S-00000000A2'").fetchone()[0]
    events = conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='owner_accepted'").fetchone()[0]
    assert hc.accept_step(Stale(conn), 'S-00000000A2', 'ghost') == 'S-00000000A2 is already accepted.'
    assert conn.execute("SELECT residual_risk FROM project_steps WHERE step_id='S-00000000A2'").fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='owner_accepted'").fetchone()[0] == events
