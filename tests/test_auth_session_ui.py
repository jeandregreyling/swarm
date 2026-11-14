"""Session expiry must be visible without losing a live conversation or draft."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_auth_rechecks_session_and_preserves_login_and_chat_state():
    node = shutil.which("node")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    source = (ROOT / "frontend/static/js/friday-auth.js").read_text()
    bootstrap = source.split("  // ── Overlay management", 1)[0]
    harness = """
const assert = require('node:assert/strict');
const events = {};
let overlay = false, loginCount = 0, badgeCount = 0, removed = [];
let failure = false, user = {username:'ghost', role:'owner'}, requests = 0, maintenance = null;
let timers = [], pendingResponse = null;
const draft = {value:'keep my unsent message'};
const window = {addEventListener(name, fn) { events[name] = fn; }, hbMaintenance(on) { maintenance = on; }};
const document = {
  hidden:false, addEventListener(name, fn) { events[name] = fn; },
  getElementById(id) {
    if (id === 'friday-auth-overlay') return overlay ? {} : null;
    if (id === 'login-msg') return {textContent:''};
    if (id === 'home-chat-input') return draft;
    return {remove() { removed.push(id); }};
  }
};
const localStorage = {getItem:()=>null, setItem(){}, removeItem(){}};
const setInterval = (fn, delay) => { timers.push({fn, delay}); };
const fetch = async url => {
  requests++;
  if (failure) throw new Error('network unavailable');
  if (pendingResponse) return pendingResponse;
  return {ok:true, json:async()=>url.endsWith('setup-status')
    ? {ok:true,owner_has_password:true} : {ok:true,user}};
};
"""
    stubs_and_checks = """
  function _showLogin(message) { overlay = true; loginCount++; }
  function _showSetup() { throw new Error('Existing installation is not setup'); }
  function _hideAuthOverlay() { overlay = false; }
  function _renderUserBadge() { badgeCount++; }
  function _setMsg() {}
  window.acceptLoginForTest = user => { _authGeneration++; _currentUser = user; window.__fridayUser = user; };
})();
(async () => {
  assert.equal(typeof window.fridayAuthCheck, 'function');
  await window.fridayAuthCheck();
  assert.equal(window.__fridayUser.role, 'owner');
  assert.equal(overlay, false);
  assert(timers.some(t => t.delay === 30000));
  for (const event of ['focus', 'visibilitychange', 'hummingbird:auth-required']) {
    assert.equal(typeof events[event], 'function', event);
  }
  user = null;
  await events['hummingbird:auth-required']();
  assert.equal(window.__fridayUser, null);
  assert.equal(overlay, true);
  assert(removed.includes('friday-user-badge'));
  assert(removed.includes('friday-user-menu'));
  assert.equal(loginCount, 1);
  await window.fridayAuthCheck();
  assert.equal(loginCount, 1, 'polling must not replace entered credentials');
  assert.equal(draft.value, 'keep my unsent message');
  user = {username:'ghost',role:'owner'};
  await window.fridayAuthCheck();
  assert.equal(overlay, false, 'login in another tab restores this page');
  assert.equal(window.__fridayUser.role, 'owner');
  failure = true;
  await window.fridayAuthCheck();
  assert.equal(window.__fridayUser, null, 'network failure must not show stale authority');
  // Owner 13 Nov: HB unreachable (restart) shows Maintenance, never the sign-in form, and keeps the session.
  assert.equal(overlay, false, 'a restart must not show the sign-in form');
  assert.equal(maintenance, true, 'a restart shows Maintenance in progress');
  failure = false;
  await window.fridayAuthCheck();
  assert.equal(window.__fridayUser.role, 'owner', 'the session is back after maintenance');
  assert.equal(maintenance, false);
  let resolve;
  pendingResponse = new Promise(r => {resolve = r;});
  const before = requests;
  const a = window.fridayAuthCheck(), b = window.fridayAuthCheck();
  assert.equal(requests, before + 1, 'concurrent events share one request');
  window.acceptLoginForTest(user);
  resolve({ok:true,json:async()=>({ok:true,user:null})});
  await Promise.all([a,b]);
  assert.equal(window.__fridayUser.role, 'owner', 'old expiry reply cannot undo a fresh login');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run([node, "-e", harness + bootstrap + stubs_and_checks],
                   check=True, timeout=10)


def test_live_owner_endpoints_request_session_recheck():
    for path in ("frontend/static/js/views/chat.js",
                 "frontend/static/js/core/tool-approval.js"):
        source = (ROOT / path).read_text()
        assert "hummingbird:auth-required" in source
