"""Preferred languages per user account (owner request, 15 Nov 2026).

The translate bubble in main chat (static/js/hb-translate-bubble.js) reads this list: an agent
reply written in a language that is not on the list is translated into every language on it.

    GET /api/user/languages   -> {'ok': True, 'username': ..., 'languages': ['en', ...], 'available': [...]}
    PUT /api/user/languages   <- {'languages': ['en', 'fr', 'ja']}
"""
import json
import re

from flask import Blueprint, jsonify, request

from database import get_connection
from services import get_current_user

user_languages_bp = Blueprint('user_languages', __name__)

# code -> name the translation model is told to write in
LANGUAGES = {
    'en': 'English', 'zh': 'Chinese (Simplified)', 'zh-tw': 'Chinese (Traditional)', 'ja': 'Japanese', 'ko': 'Korean',
    'th': 'Thai', 'vi': 'Vietnamese', 'id': 'Indonesian', 'hi': 'Hindi', 'ar': 'Arabic', 'tr': 'Turkish',
    'fr': 'French', 'de': 'German', 'es': 'Spanish', 'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch',
    'af': 'Afrikaans', 'ru': 'Russian', 'uk': 'Ukrainian', 'pl': 'Polish',
}
# Any other language can be typed in by name; it is stored as 'x:<Name>'.
CUSTOM = re.compile(r"^[^\W\d_][\w '()\-]{1,29}$", re.UNICODE)
DEFAULT = ['en']
MAX_LANGUAGES = 5


def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_language_prefs ("
        "username TEXT PRIMARY KEY, languages TEXT NOT NULL DEFAULT '[\"en\"]', "
        "updated_at TEXT DEFAULT (datetime('now')))")


def clean(languages):
    """Known codes or typed-in names, in the order given, no repeats. None when nothing valid is left."""
    if not isinstance(languages, list):
        return None
    out = []
    for item in languages:
        raw = str(item).strip()
        code = raw.lower()
        if code not in LANGUAGES:
            name = raw[2:].strip() if code.startswith('x:') else raw
            known = [c for c, n in LANGUAGES.items() if n.lower() == name.lower()]
            if known:
                code = known[0]
            elif CUSTOM.match(name):
                code = 'x:' + name
            else:
                continue
        if code.lower() not in [c.lower() for c in out]:
            out.append(code)
    return out[:MAX_LANGUAGES] or None


def get_languages(username):
    conn = get_connection()
    try:
        _ensure(conn)
        row = conn.execute("SELECT languages FROM user_language_prefs WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()
    if not row:
        return list(DEFAULT)
    try:
        return clean(json.loads(row[0])) or list(DEFAULT)
    except (TypeError, ValueError):
        return list(DEFAULT)


def set_languages(username, languages):
    conn = get_connection()
    try:
        _ensure(conn)
        conn.execute(
            "INSERT INTO user_language_prefs(username, languages, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(username) DO UPDATE SET languages=excluded.languages, updated_at=excluded.updated_at",
            (username, json.dumps(languages)))
        conn.commit()
    finally:
        conn.close()


def _available():
    return [{'code': code, 'name': name} for code, name in LANGUAGES.items()]


@user_languages_bp.route('/api/user/languages')
def api_user_languages():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False, 'error': 'not signed in', 'languages': list(DEFAULT), 'available': _available()}), 401
    return jsonify({'ok': True, 'username': user['username'], 'display_name': user.get('display_name') or user['username'],
                    'languages': get_languages(user['username']), 'available': _available()})


@user_languages_bp.route('/api/user/languages', methods=['PUT', 'POST'])
def api_user_languages_save():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False, 'error': 'not signed in'}), 401
    languages = clean((request.get_json(silent=True) or {}).get('languages'))
    if not languages:
        return jsonify({'ok': False, 'error': 'choose at least one known language'}), 400
    set_languages(user['username'], languages)
    return jsonify({'ok': True, 'username': user['username'], 'languages': languages})
