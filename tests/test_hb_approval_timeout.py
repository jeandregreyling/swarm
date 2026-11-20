"""The rendered Approve control and live snapshot recover from bounded, uncertain network requests."""
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live.js'


@pytest.mark.parametrize('action_stall', ['headers', 'body'])
@pytest.mark.parametrize('live_stall', ['headers', 'body'])
def test_rendered_approve_times_out_once_and_refresh_recovers(action_stall, live_stall):
    run_node(action_stall, live_stall)


def test_successful_approval_keeps_existing_resolution_and_clears_deadline():
    run_node('success', 'success')


def run_node(action_stall, live_stall):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    code = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const [js, actionStall, liveStall] = process.argv.slice(1);
const listeners = {}, storage = new Map(), timers = new Map(), calls = [];
let now = 0, nextTimer = 0, removed = false, liveMode = liveStall;
let lateAction, lateLive;
const note = {textContent: ''}, box = {querySelector: () => note, remove: () => {removed = true;}};
const pane = {scrollTop: 0, querySelectorAll: () => []};
const item = {key: 'accept:S-0123456789', kind: 'accept', step_id: 'S-0123456789', label: 'Approve this completed check'};
const pendingSnap = {ok: true, at: 1, lanes: [], needs_you: [item], master: {items: []}};
const emptySnap = {...pendingSnap, at: 2, needs_you: []};
const document = {hidden: true, readyState: 'loading', body: {classList: {add: () => {}}},
  addEventListener: (kind, fn) => {listeners[kind] = fn;}, querySelectorAll: () => [],
  getElementById: id => id === 'hb-live-pop' && !removed ? box : id === 'hb-live-pane' ? pane : id === 'hb-live-style' ? {} : null};
function pending(signal, live, body) {
  // Deliberately ignore abort: the timeout must settle even when a transport does not cooperate.
  return new Promise(resolve => {
    const complete = () => resolve(body ? pendingSnap : {ok: true, json: async () => pendingSnap});
    if (live) lateLive = complete; else lateAction = complete;
  });
}
const context = {document, AbortController, window: {confirm: () => true}, console,
  localStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)},
  setInterval: () => 0, clearTimeout: id => timers.delete(id),
  setTimeout: (fn, delay) => {const id = ++nextTimer; timers.set(id, {fn, at: now + delay}); return id;},
  fetch: (url, options) => {
    calls.push({url, options});
    const live = url === '/api/peer/v1/hb/live';
    const mode = live ? liveMode : actionStall;
    if (mode === 'headers') return pending(options.signal, live, false);
    if (mode === 'body') return Promise.resolve({ok: true, json: () => pending(options.signal, live, true)});
    return Promise.resolve({ok: true, json: async () => live ? emptySnap : {ok: true, said: 'Approved'}});
  }};
vm.runInNewContext(fs.readFileSync(js, 'utf8'), context);
const state = context.window.hbLive.state;
state.popup = item.key; state.snap = pendingSnap;
const html = context.window.HBLiveRender.renderNeedsPopup(item, state.needsControls);
const rendered = html.match(/<button\b[^>]*data-a="accept"[^>]*>Approve<\/button>/);
assert.ok(rendered, 'use the actual rendered Approve control');
const dataset = Object.fromEntries([...rendered[0].matchAll(/data-([a-z]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
const button = {disabled: false, dataset};
const target = {closest: selector => selector.includes(', ') || selector === '#hb-live-pop' ? box
  : selector === 'button[data-q]' ? button : null};
const flush = () => new Promise(setImmediate);
async function advance(ms) {
  const until = now + ms;
  while (true) {
    const entry = [...timers].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
    if (!entry) break;
    now = entry[1].at; timers.delete(entry[0]); entry[1].fn(); await flush();
  }
  now = until; await flush();
}
(async () => {
  if (actionStall === 'success') {document.hidden = false; liveMode = 'success';}
  listeners.click({target}); listeners.click({target});
  assert.equal(calls.filter(c => c.url === '/api/peer/v1/hb/queue').length, 1);
  assert.deepEqual(JSON.parse(calls[0].options.body), {task: ['accept', 'S-0123456789']});
  assert.equal(button.disabled, true);
  await flush();
  if (actionStall === 'success') {
    assert.equal(button.disabled, false); assert.equal(removed, true);
    await advance(20000);
    assert.equal(calls[0].options.signal.aborted, false, 'successful requests clear their deadline');
    assert.equal(timers.size, 0); return;
  }
  await advance(14999);
  assert.equal(button.disabled, true); assert.equal(calls[0].options.signal.aborted, false);
  await advance(1);
  assert.equal(button.disabled, false, 'deadline reenables the rendered Approve button');
  assert.equal(calls[0].options.signal.aborted, true, 'also abort the real transport');
  assert.match(note.textContent, /15 seconds.*[Cc]heck current status/);
  assert.equal(removed, false); assert.equal(storage.has('hbLive.needsSeen'), false);
  assert.equal(calls.length, 1, 'uncertain POST must not retry or claim success');
  lateAction(); await flush();
  assert.equal(calls.length, 1, 'late POST response must not run the success handler');
  document.hidden = false;
  context.window.hbLive.refresh(); await flush();
  assert.equal(state.busy, true);
  context.window.hbLive.refresh();
  assert.equal(calls.length, 2, 'only one live request may be pending');
  await advance(15000);
  assert.equal(state.busy, false, 'snapshot timeout releases the poller');
  assert.equal(calls[1].options.signal.aborted, true);
  assert.equal(removed, false); assert.equal(state.snap, pendingSnap);
  liveMode = 'success'; context.window.hbLive.refresh(); await flush();
  assert.equal(state.busy, false); assert.equal(removed, true, 'fresh empty snapshot removes stale popup');
  assert.equal(state.snap.needs_you.length, 0);
  lateLive(); await flush();
  assert.equal(state.snap.needs_you.length, 0, 'late timed-out snapshot cannot overwrite newer state');
  assert.equal(removed, true); assert.equal(timers.size, 0);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run([node, '-e', code, str(JS), action_stall, live_stall], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr[-2200:]
