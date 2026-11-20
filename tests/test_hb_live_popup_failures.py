"""Needs-you actions stay visible until HB confirms the action or resolves the item."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'


@pytest.mark.parametrize('action,outcome', [
    ('task', 'http_error'), ('task', 'body_error'), ('task', 'network_error'),
    ('task', 'success'), ('task', 'changed_popup'), ('task', 'semantic_error'),
    ('command', 'http_error'), ('command', 'network_error'),
    ('command', 'semantic_error'), ('command', 'success'),
])
def test_popup_action_waits_for_hb(action, outcome):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    harness = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const [js, action, outcome] = process.argv.slice(1);
const listeners = {}, storage = new Map([['fridays-home-chat-active-thread', '2845']]);
const note = {textContent: ''};
const pane = {scrollTop: 0, querySelectorAll: () => []};
let removed = false, resolveFetch, rejectFetch;
const calls = [];
const box = {querySelector: () => note, remove: () => {removed = true;}};
const button = {disabled: false, dataset: action === 'task'
  ? {q: 'task', a: 'continue', id: 'T-ABCDEF012345'} : {cmd: '/plan T-ABCDEF012345'}};
const target = {closest: (selector) => {
  if (selector.includes(', ')) return box;
  if (selector === '#hb-live-pop') return box;
  if (selector === 'button[data-q]') return action === 'task' ? button : null;
  if (selector === '[data-cmd]') return action === 'command' ? button : null;
  return null;
}};
const document = {hidden: true, readyState: 'loading', body: {classList: {add: () => {}}},
  addEventListener: (kind, fn) => {listeners[kind] = fn;}, querySelectorAll: () => [],
  getElementById: (id) => id === 'hb-live-pop' && !removed ? box : id === 'hb-live-pane' ? pane : id === 'hb-live-style' ? {} : null};
const context = {document, AbortController, window: {confirm: () => true},
  localStorage: {getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)},
  fetch: (url, options) => {
    if (url === '/api/peer/v1/hb/live') return Promise.resolve({ok: true, json: async () => ({ok: true, needs_you: [], master: {items: []}})});
    calls.push([url, JSON.parse(options.body)]); return new Promise((resolve, reject) => {resolveFetch = resolve; rejectFetch = reject;});},
  setInterval: () => {}, setTimeout: () => {}, clearTimeout: () => {}, console};
vm.runInNewContext(fs.readFileSync(js, 'utf8'), context);
const state = context.window.hbLive.state;
state.popup = 'old';
state.snap = {needs_you: [{key: 'old', kind: 'review'}]};
(async () => {
  listeners.click({target});
  assert.equal(calls.length, 1);
  assert.equal(removed, false, 'click must not hide an unanswered item');
  assert.equal(button.disabled, true);
  listeners.click({target});
  assert.equal(calls.length, 1, 'double click must not resend');
  assert.equal(storage.has('hbLive.needsSeen'), false);
  assert.equal(calls[0][0], action === 'task' ? '/api/peer/v1/hb/queue' : '/api/chat');
  if (action === 'command') {
    assert.equal(calls[0][1].message, '/plan T-ABCDEF012345');
    assert.equal(calls[0][1].conversation_id, 2845);
    assert.equal(calls[0][1].new_thread, false);
  }
  if (outcome === 'changed_popup') state.popup = 'new';
  if (outcome === 'network_error') rejectFetch(new Error('offline'));
  else resolveFetch({ok: outcome !== 'http_error', json: async () =>
    outcome === 'http_error' || outcome === 'body_error' ? {ok: false, error: 'Permission denied'} :
    outcome === 'semantic_error' ? {ok: true, [action === 'task' ? 'said' : 'response']: 'HB could not do that: stale plan'} :
    {ok: true, said: 'Continued', mode: 'control'}});
  await new Promise(setImmediate);
  await new Promise(setImmediate);
  assert.equal(button.disabled, false);
  {
    assert.equal(removed, false, 'failure, unresolved command or newer popup must remain visible');
    assert.equal(storage.has('hbLive.needsSeen'), false);
    if (outcome.endsWith('error')) assert.ok(note.textContent.length, 'show the failure in the popup');
    if (outcome === 'changed_popup') assert.equal(state.popup, 'new');
    if (outcome === 'success') {
      document.hidden = false;
      listeners.visibilitychange();
      await new Promise(setImmediate);
      await new Promise(setImmediate);
      assert.equal(removed, true, 'action closes only after the pending item is resolved in HB');
      assert.equal(state.popup, null);
    }
  }
})().catch((error) => {console.error(error); process.exitCode = 1;});
"""
    out = subprocess.run([node, '-e', harness, str(JS), action, outcome], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-1500:]


def test_popup_has_a_place_for_action_errors():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    code = "const r=require(process.argv[1]);process.stdout.write(r.renderNeedsPopup({key:'pending',label:'Review'},()=>''));"
    out = subprocess.run([node, '-e', code, str(JS)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    assert 'class="hbl-said hbl-dim"' in out.stdout and 'role="status"' in out.stdout
