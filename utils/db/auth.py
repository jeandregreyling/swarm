"""
db.auth — User profiles, skill permissions, trusted senders / domains,
           notification senders, email lists.
"""
from ._connection import get_connection, logger


# ── User profiles ─────────────────────────────────────────────────────────────

def list_user_profiles(include_inactive=False):
    conn = get_connection()
    try:
        sql = (
            "SELECT username, display_name, user_type, linked_agent, is_active, can_proxy, "
            "created_by, created_at, updated_at "
            "FROM user_profiles"
        )
        params = []
        if not include_inactive:
            sql += " WHERE is_active=1"
        sql += " ORDER BY CASE WHEN username='ghost' THEN 0 ELSE 1 END, username ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_profile(username):
    uname = (username or '').strip().lower()
    if not uname:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT username, display_name, user_type, linked_agent, is_active, can_proxy,
                      created_by, created_at, updated_at
               FROM user_profiles WHERE username=?""",
            (uname,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_user_profile(username, display_name='', user_type='human', linked_agent='',
                        is_active=1, can_proxy=0, created_by='ghost'):
    uname = (username or '').strip().lower()
    if not uname:
        raise ValueError('username required')
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM user_profiles WHERE username=?",
            (uname,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE user_profiles
                   SET display_name=?, user_type=?, linked_agent=?, is_active=?, can_proxy=?,
                       updated_at=datetime('now')
                   WHERE username=?""",
                (
                    (display_name or uname).strip(),
                    (user_type or 'human').strip().lower(),
                    (linked_agent or '').strip().lower(),
                    1 if is_active else 0,
                    1 if can_proxy else 0,
                    uname,
                )
            )
        else:
            conn.execute(
                """INSERT INTO user_profiles
                   (username, display_name, user_type, linked_agent, is_active, can_proxy, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uname,
                    (display_name or uname).strip(),
                    (user_type or 'human').strip().lower(),
                    (linked_agent or '').strip().lower(),
                    1 if is_active else 0,
                    1 if can_proxy else 0,
                    (created_by or 'ghost').strip().lower(),
                )
            )
        conn.commit()
    finally:
        conn.close()
    return get_user_profile(uname)


# ── Skill permissions ─────────────────────────────────────────────────────────

def list_user_skill_permissions(username):
    uname = (username or '').strip().lower()
    if not uname:
        return []
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT username, skill_name, allowed, created_by, created_at, updated_at
               FROM user_skill_permissions
               WHERE username=?
               ORDER BY skill_name ASC""",
            (uname,)
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item['allowed'] = bool(item.get('allowed'))
            out.append(item)
        return out
    finally:
        conn.close()


def set_user_skill_permission(username, skill_name, allowed=True, created_by='ghost'):
    uname = (username or '').strip().lower()
    sk = (skill_name or '').strip().lower()
    if not uname:
        raise ValueError('username required')
    if not sk:
        raise ValueError('skill_name required')
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO user_skill_permissions
               (username, skill_name, allowed, created_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(username, skill_name)
               DO UPDATE SET allowed=excluded.allowed,
                             created_by=excluded.created_by,
                             updated_at=datetime('now')""",
            (uname, sk, 1 if allowed else 0, (created_by or 'ghost').strip().lower())
        )
        conn.commit()
    finally:
        conn.close()


def remove_user_skill_permission(username, skill_name):
    uname = (username or '').strip().lower()
    sk = (skill_name or '').strip().lower()
    if not uname or not sk:
        return
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM user_skill_permissions WHERE username=? AND skill_name=?",
            (uname, sk)
        )
        conn.commit()
    finally:
        conn.close()


def can_user_invoke_skill(username, skill_name, default_allow=True):
    uname = (username or '').strip().lower()
    sk = (skill_name or '').strip().lower()
    if not sk:
        return False
    if not uname:
        return bool(default_allow)

    profile = get_user_profile(uname)
    if not profile or not profile.get('is_active'):
        return False

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT allowed FROM user_skill_permissions WHERE username=? AND skill_name=?",
            (uname, sk)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return bool(default_allow)
    return bool(row['allowed'])


# ── Trusted senders / domains / notification senders ──────────────────────────

def add_trusted_sender(email, added_by='ghost', note=''):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO trusted_senders (email,added_by,notes) VALUES (?,?,?)",
        (email.lower(), added_by, note)
    )
    conn.commit()
    conn.close()


def remove_trusted_sender(email):
    conn = get_connection()
    conn.execute("DELETE FROM trusted_senders WHERE LOWER(email)=?", (email.lower(),))
    conn.commit()
    conn.close()


def add_trusted_domain(domain, added_by='ghost', note='', channel='email'):
    """Trust all senders from a domain (e.g. example.com)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO trusted_domains (domain, channel, added_by, notes) VALUES (?,?,?,?)",
        (domain.lower().lstrip('@'), channel, added_by, note)
    )
    conn.commit()
    conn.close()


def get_trusted_domains():
    """Return set of trusted domains."""
    conn = get_connection()
    rows = conn.execute("SELECT domain FROM trusted_domains").fetchall()
    conn.close()
    return {row[0] for row in rows}


def add_notification_sender(email, added_by='ghost', note=''):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO notification_senders (email, added_by, notes) VALUES (?,?,?)",
        (email.lower(), added_by, note)
    )
    conn.commit()
    conn.close()


def remove_notification_sender(email):
    conn = get_connection()
    conn.execute("DELETE FROM notification_senders WHERE LOWER(email)=?", (email.lower(),))
    conn.commit()
    conn.close()


def get_all_email_lists():
    conn = get_connection()
    trusted = set(row[0] for row in conn.execute("SELECT LOWER(email) FROM trusted_senders").fetchall())
    mods    = set(row[0] for row in conn.execute("SELECT LOWER(email) FROM moderators").fetchall())
    notifs  = set(row[0] for row in conn.execute("SELECT LOWER(email) FROM notification_senders").fetchall())
    conn.close()
    return trusted, mods, notifs
