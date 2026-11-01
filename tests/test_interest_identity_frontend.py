"""Execute the real interest UI JavaScript without contacting production APIs."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_interest_identity_reads_and_writes_use_same_human():
    runtime = shutil.which('node')
    if not runtime:
        vscode_node = Path('/usr/share/code/code')
        if vscode_node.is_file():
            runtime = str(vscode_node)
        else:
            pytest.fail('JavaScript runtime required: Node or VS Code bundled Node')

    harness = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const root = process.argv[1];
const auth = fs.readFileSync(root + '/frontend/static/js/friday-auth.js', 'utf8');
const knowledge = fs.readFileSync(root + '/frontend/static/js/views/knowledge.js', 'utf8');
const home = fs.readFileSync(root + '/frontend/static/js/views/home-chat.js', 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function context(user, {authStatus = 200, failAuth = false, invalidJson = false} = {}) {
  const requests = [], errors = [], toasts = [], listeners = {};
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
      value: 'Python, Gardening', textContent: '', innerHTML: '',
      style: {}, disabled: false, querySelectorAll: () => [],
      remove() {}, addEventListener() {}, appendChild() {}
    });
    return nodes.get(id);
  }
  const document = {
    getElementById: id => {
      if (['kn-interests-strip', 'friday-user-badge'].includes(id)) return null;
      return node(id);
    },
    addEventListener() {}, querySelectorAll: () => [], querySelector: () => null,
    body: {appendChild() {}, classList: {add() {}, remove() {}}}
  };
  const c = {
    document, console: {error: (...args) => errors.push(args), log() {}, warn() {}},
    localStorage: {getItem: () => JSON.stringify({acting_user: 'wrong-person', proxy_as: 'seven'}),
                   setItem() {}, removeItem() {}},
    addEventListener: (event, handler) => { listeners[event] = handler; },
    setTimeout() {}, setInterval() {},
    showToast: (...args) => toasts.push(args), URLSearchParams,
    fetch: async (url, options) => {
      requests.push({url, options});
      if (url === '/api/auth/me') {
        if (failAuth) throw new Error('Network unavailable');
        return {ok: authStatus === 200, status: authStatus, json: async () => {
          if (invalidJson) throw new Error('Invalid JSON');
          return {user};
        }};
      }
      if (url === '/api/interests/seed') return {ok: true, json: async () => ({ok: true, count: 2})};
      if (url.startsWith('/api/interests?')) return {ok: true, json: async () => ({
        interests: [{topic: 'Python', sources: ['saved'], suggestion: 'Discuss Python'}],
        research_topics: []
      })};
      throw new Error('Unexpected request: ' + url);
    }
  };
  c.window = c;
  vm.createContext(c);
  vm.runInContext(auth, c);
  vm.runInContext(knowledge, c);
  // Test-only access to private functions; execute the whole production file.
  const closing = home.lastIndexOf('})();');
  assert.ok(closing > 0);
  vm.runInContext(home.slice(0, closing) +
    'window.interestTest = {fetch: _hcFetchInterests, save: _hcSaveOnboarding, topics: _hcSelectedTopics};' +
    home.slice(closing), c);
  return {c, requests, errors, toasts, node, listeners};
}

(async () => {
  for (const username of ['ghost', 'alice', 'user+name&other=seven']) {
    const {c, requests} = context({username});
    c.knowledgeRefreshInterestStrip();
    c.interestTest.fetch();
    await flush(); await flush();
    const reads = requests.filter(r => r.url.startsWith('/api/interests?'));
    assert.equal(reads.length, 2);
    for (const request of reads) {
      assert.equal(new URL(request.url, 'http://local').searchParams.get('username'), username);
    }
    await c.knowledgeSeedInterests();
    c.interestTest.topics.add('Python');
    c.interestTest.save();
    await flush(); await flush();
    const writes = requests.filter(r => r.url === '/api/interests/seed');
    assert.equal(writes.length, 2);
    for (const request of writes) {
      assert.equal(JSON.parse(request.options.body).username, username);
    }
    for (const request of requests.filter(r => r.url.startsWith('/api/interests?'))) {
      assert.equal(new URL(request.url, 'http://local').searchParams.get('username'), username);
    }
  }
  for (const user of [null, {username: ''}, {username: '   '}]) {
    const {c} = context(user);
    assert.equal(await c.fridayInterestUsername(), 'ghost');
  }
  {
    const {c} = context({username: '  alice  '});
    assert.equal(await c.fridayInterestUsername(), 'alice');
  }
  {
    const {c, listeners} = context({username: 'alice'});
    listeners.DOMContentLoaded();
    await flush(); await flush();
    assert.equal(c.fridayGetCurrentUser().username, 'alice');
    c.fetch = async () => { throw new Error('In-memory identity should not refetch auth'); };
    assert.equal(await c.fridayInterestUsername(), 'alice');
  }
  {
    const {c, requests} = context({username: 'alice'});
    const fetch = c.fetch;
    let release;
    const ready = new Promise(resolve => { release = resolve; });
    c.fetch = (url, options) => url === '/api/auth/me'
      ? ready.then(() => fetch(url, options)) : fetch(url, options);
    c.interestTest.fetch();
    await flush();
    assert.equal(requests.length, 0);
    release();
    await flush(); await flush();
    assert.equal(new URL(requests.at(-1).url, 'http://local').searchParams.get('username'), 'alice');
  }
  {
    const {c, requests, toasts} = context({username: 'alice'});
    const fetch = c.fetch;
    let refreshAttempts = 0;
    c.fetch = (url, options) => {
      if (url.startsWith('/api/interests?')) {
        refreshAttempts++;
        return Promise.reject(new Error('Refresh unavailable'));
      }
      return fetch(url, options);
    };
    c.interestTest.topics.add('Python');
    c.interestTest.save();
    await flush(); await flush();
    const writes = requests.filter(r => r.url === '/api/interests/seed');
    assert.equal(writes.length, 1);
    assert.equal(JSON.parse(writes[0].options.body).username, 'alice');
    assert.equal(refreshAttempts, 1);
    assert.ok(toasts.some(t => t[0] === 'Unable to refresh your interests' && t[1] === 'error'));
  }
  for (const options of [{authStatus: 500}, {failAuth: true}, {invalidJson: true}]) {
    const {c, requests, errors, toasts, node} = context(null, options);
    await assert.rejects(() => c.fridayInterestUsername());
    c.knowledgeRefreshInterestStrip();
    c.interestTest.fetch();
    await flush(); await flush();
    await c.knowledgeSeedInterests();
    c.interestTest.topics.add('Python');
    c.interestTest.save();
    await flush(); await flush();
    assert.equal(requests.filter(r => r.url.startsWith('/api/interests')).length, 0);
    assert.match(node('kn-interests-list').textContent, /^Unable to load interests:/);
    assert.match(node('kn-seed-status').textContent, /^Error:/);
    assert.ok(errors.length > 0);
    assert.ok(toasts.some(t => t[1] === 'error'));
    assert.equal(node('home-onboarding-save').disabled, false);
    assert.equal(node('home-onboarding-save').textContent, 'Save my interests');
  }
  console.log(JSON.stringify({passed: true}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [runtime, '-e', harness, str(ROOT)],
        env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['passed'] is True
