"""Hummingbird Liquid-Glass Tasks & Status drawers: Escape closes the open drawer and frosted glass CSS applies."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'


def test_hummingbird_drawer_has_liquid_glass_styling_and_closes_on_escape():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    src = JS.read_text(encoding='utf-8')
    assert 'backdrop-filter:blur(18px)' in src
    assert 'rgba(16,232,164' in src and 'rgba(255,184,77' in src and 'rgba(244,114,182' in src
    harness = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const [js] = process.argv.slice(1);
const listeners = {}, storage = new Map([['hbLive.drawer', 'tasks']]);
const drawer = {hidden: false, innerHTML: '', style: {}, setAttribute: () => {}, querySelector: () => null, querySelectorAll: () => []};
const pane = {innerHTML: '', scrollTop: 0, querySelector: () => null, querySelectorAll: () => []};
const document = {
  hidden: true, readyState: 'loading',
  body: {classList: {add: () => {}}, appendChild: () => {}},
  head: {appendChild: () => {}},
  createElement: () => ({id: '', textContent: '', style: {}, setAttribute: () => {}}),
  addEventListener: (k, fn) => {listeners[k] = fn;},
  querySelectorAll: () => [],
  getElementById: (id) => id === 'hb-live-drawer' ? drawer : id === 'hb-live-pane' ? pane : id === 'hb-live-style' ? {} : null,
};
const context = {
  document, AbortController, window: {confirm: () => true},
  localStorage: {getItem: (k) => storage.get(k) || null, setItem: (k, v) => storage.set(k, v)},
  fetch: () => Promise.resolve({ok: true, json: async () => ({ok: true})}),
  setInterval: () => {}, setTimeout: () => {}, clearTimeout: () => {}, console,
};
vm.runInNewContext(fs.readFileSync(js, 'utf8'), context);
assert.equal(typeof listeners.keydown, 'function', 'Escape keydown listener must be registered');
listeners.keydown({key: 'Enter'});
assert.equal(storage.get('hbLive.drawer'), 'tasks', 'Non-Escape keys must not close drawer');
listeners.keydown({key: 'Escape'});
assert.equal(storage.get('hbLive.drawer'), '0', 'Escape must close an open Tasks/Status drawer');
"""
    out = subprocess.run([node, '-e', harness, str(JS)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-1200:]
