"""Practice 219 (calm swarm 1/5): a busy HB is not "Maintenance in progress"."""
import importlib.util
import shutil
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SAVED = {name: sys.modules.get(name) for name in ('database', 'services')}
try:   # stubs only while login_bp loads - other tests import the real modules
    if _SAVED['database'] is None:
        stub = types.ModuleType('database'); stub.get_connection = lambda: None; sys.modules['database'] = stub
    if _SAVED['services'] is None:
        stub = types.ModuleType('services'); stub.get_current_user = lambda: None
        stub.require_auth = stub.require_owner = lambda fn: fn; sys.modules['services'] = stub
    _SPEC = importlib.util.spec_from_file_location('swarm_login_bp_p219', ROOT / 'frontend' / 'blueprints' / 'login_bp.py')
    LOGIN = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(LOGIN)
finally:
    for _name, _module in _SAVED.items():
        if _module is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _module


def test_busy_database_does_not_fail_the_session_check(tmp_path, monkeypatch):
    path = tmp_path / 's.db'
    other = sqlite3.connect(path)
    other.execute('CREATE TABLE user_sessions(session_token TEXT, expires_at TEXT, is_active INTEGER)')
    other.execute("INSERT INTO user_sessions VALUES ('tok', '2000-01-01 00:00:00', 1)")
    other.commit()
    other.execute('UPDATE user_sessions SET is_active=1')          # another request holds the write lock
    monkeypatch.setattr(LOGIN, 'get_current_user', lambda: {'username': 'ghost', 'role': 'owner'})
    monkeypatch.setattr(LOGIN, 'get_connection', lambda: sqlite3.connect(path, timeout=0.1))
    app = Flask('p219'); app.register_blueprint(LOGIN.login_bp)
    client = app.test_client(); client.set_cookie('friday_session', 'tok')
    answer = client.get('/api/auth/me')
    assert answer.status_code == 200 and answer.get_json()['user']['username'] == 'ghost'
    other.rollback()


def _node():
    node = shutil.which('node')
    if node is None:
        pytest.skip('JavaScript runtime is unavailable')
    return node


AUTH_HARNESS = """
const assert = require('node:assert/strict');
const events = {};
let overlay = false, maintenance = null, probes = 0, mode = 'ok';
const user = {username:'ghost', role:'owner'};
const window = {addEventListener(n, fn) { events[n] = fn; }, hbMaintenance(on) { maintenance = on; }, hbMaintenanceProbe() { probes++; }};
const document = {hidden:false, addEventListener(n, fn) { events[n] = fn; },
  getElementById(id) { if (id === 'friday-auth-overlay') return overlay ? {} : null; if (id === 'login-msg') return {textContent:''}; return {remove() {}}; }};
const localStorage = {getItem:()=>null, setItem(){}, removeItem(){}};
const setInterval = () => 1;
const fetch = async url => {
  if (mode === 'down') throw new TypeError('fetch failed');
  if (mode === 'http500') return {ok:false, status:500, json:async()=>({ok:false})};
  return {ok:true, json:async()=>url.endsWith('setup-status') ? {ok:true,owner_has_password:true} : {ok:true,user}};
};
"""
AUTH_CHECKS = """
  function _showLogin() { overlay = true; }
  function _showSetup() { throw new Error('setup'); }
  function _hideAuthOverlay() { overlay = false; }
  function _renderUserBadge() {}
  function _setMsg() {}
})();
(async () => {
  await window.fridayAuthCheck();
  assert.equal(window.__fridayUser.role, 'owner');
  maintenance = null;
  mode = 'http500';
  await window.fridayAuthCheck();
  assert.equal(window.__fridayUser.role, 'owner', 'HB answered: the session stays');
  assert.equal(maintenance, null, 'HB answered: no Maintenance screen');
  assert.equal(overlay, false, 'HB answered: no sign-in screen');
  mode = 'down';
  await window.fridayAuthCheck();
  assert.equal(probes, 1, 'unreachable: the maintenance probe asks HB first');
  assert.equal(maintenance, null, 'one failed session check does not show Maintenance by itself');
  console.log('ok');
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


def test_session_check_error_from_a_busy_hb_keeps_the_page():
    source = (ROOT / 'frontend/static/js/friday-auth.js').read_text()
    bootstrap = source.split('  // ── Overlay management', 1)[0]
    out = subprocess.run([_node(), '-e', AUTH_HARNESS + bootstrap + AUTH_CHECKS], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0 and out.stdout.strip().endswith('ok'), out.stdout + out.stderr


MAINT_HARNESS = """
const els = {};
function mk(tag){ const e = {tag, style:{}, children:[], attrs:{}, textContent:'', innerHTML:'', id:'',
  setAttribute(k,v){this.attrs[k]=v}, addEventListener(){}, appendChild(c){this.children.push(c); if(c.id) els[c.id]=c},
  querySelector(sel){ const k = sel.replace(/[\\[\\]]/g,''); return this[k] || (this[k] = mk('x')); } }; return e; }
global.document = {hidden:false, body: mk('body'), documentElement: mk('html'), createElement: mk, getElementById: id => els[id] || null};
global.window = {HB_ASSET_VERSION: 'v1'}; global.location = {reload(){}};
global.setInterval = (fn, ms) => { if (ms === 5000) global.tick5 = fn; return 1; };
global.clearInterval = () => {};
global.setTimeout = (fn, ms) => { global.retry = fn; return 1; };
global.fetch = () => Promise.reject(new Error('busy'));
"""
MAINT_CHECKS = """
const flush = () => new Promise(r => setImmediate(r));
const showing = () => !!els['hb-maintenance'] && els['hb-maintenance'].style.display === 'flex';
(async () => {
  global.tick5(); await flush(); await flush();
  if (showing()) throw new Error('one missed answer showed Maintenance');
  if (typeof global.retry !== 'function') throw new Error('no second try scheduled');
  await global.retry(); await flush();
  if (!showing()) throw new Error('two missed answers must show Maintenance');
  console.log('ok');
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


def test_background_check_gives_hb_a_second_try_before_maintenance():
    js = (ROOT / 'frontend/static/js/hb-maintenance.js').read_text()
    out = subprocess.run([_node(), '-e', MAINT_HARNESS + js + MAINT_CHECKS], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0 and out.stdout.strip().endswith('ok'), out.stdout + out.stderr
