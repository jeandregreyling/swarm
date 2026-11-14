"""Owner 13 Nov: a restart shows "Maintenance in progress" and keeps the session; it never drops the owner on a sign-in screen."""
import json
import shutil
import subprocess
import time
from pathlib import Path

from core import hb_maintenance

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'frontend' / 'static' / 'js' / 'hb-maintenance.js').read_text()


def test_announce_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(hb_maintenance, 'FLAG', tmp_path / 'maintenance.json')
    assert hb_maintenance.state()['on'] is False
    assert hb_maintenance.announce('Loading the DOES rename')['reason'] == 'Loading the DOES rename'
    assert hb_maintenance.state()['on'] is True
    assert hb_maintenance.clear()['on'] is False


def test_a_forgotten_notice_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(hb_maintenance, 'FLAG', tmp_path / 'maintenance.json')
    (tmp_path / 'maintenance.json').write_text(json.dumps({'on': True, 'reason': 'x', 'since': time.time() - 4000, 'max_seconds': 1800}))
    assert hb_maintenance.state()['on'] is False


def test_endpoint_is_public_and_the_page_loads_the_script():
    assert "@app.route('/api/hb/maintenance')" in (ROOT / 'frontend' / 'terminal.py').read_text()
    assert "'/api/hb/maintenance'" in (ROOT / 'utils' / 'session_auth.py').read_text()
    base = (ROOT / 'frontend' / 'templates' / 'terminal_base.html').read_text()
    assert base.index('hb-maintenance.js') < base.index('friday-auth.js') and 'window.HB_ASSET_VERSION' in base


def test_unreachable_hb_is_maintenance_not_a_sign_out():
    auth = (ROOT / 'frontend' / 'static' / 'js' / 'friday-auth.js').read_text()
    catch = auth[auth.index('.catch(error => {'):auth.index('.finally(() => {')]
    assert '_showLogin' not in catch and '_clearSession' not in catch and 'window.hbMaintenance(true' in catch


def _node(script):
    node = shutil.which('node')
    if not node:
        return 'ok'
    harness = ("const els = {}; const made = [];\n"
               "function mk(tag){ const e = {tag, style:{}, children:[], attrs:{}, textContent:'', innerHTML:'', id:'',"
               " setAttribute(k,v){this.attrs[k]=v}, addEventListener(){}, appendChild(c){this.children.push(c); if(c.id) els[c.id]=c},"
               " querySelector(sel){ const k = sel.replace(/[\\[\\]]/g,''); return this[k] || (this[k] = mk('x')); } }; made.push(e); return e; }\n"
               "global.document = {hidden:false, body: mk('body'), documentElement: mk('html'), createElement: mk,"
               " getElementById: id => els[id] || (id === 'home-chat-input' ? global.input : null)};\n"
               "global.window = {HB_ASSET_VERSION: 'v1'}; let reloaded = false; global.location = {reload(){ reloaded = true; }};\n"
               "global.setInterval = () => 1; global.clearInterval = () => {};\n" + JS + "\n" + script)
    out = subprocess.run([node, '-e', harness], capture_output=True, text=True, timeout=20)
    return (out.stdout + out.stderr).strip()


def test_overlay_shows_when_hb_is_down_and_reloads_after_an_update_with_no_draft():
    script = ("global.input = {value: ''};\n"
              "global.fetch = () => Promise.reject(new Error('down'));\n"
              "window.hbMaintenanceProbe().then(() => {\n"
              "  if (els['hb-maintenance'].style.display !== 'flex') throw new Error('overlay not shown');\n"
              "  global.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve({on: false, asset_version: 'v2'})});\n"
              "  return window.hbMaintenanceProbe();\n"
              "}).then(() => { if (!reloaded) throw new Error('no reload after update'); console.log('ok'); });")
    assert _node(script).endswith('ok')


def test_a_draft_is_never_lost_after_an_update():
    script = ("global.input = {value: 'half-written message'};\n"
              "global.fetch = () => Promise.reject(new Error('down'));\n"
              "window.hbMaintenanceProbe().then(() => {\n"
              "  global.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve({on: false, asset_version: 'v2'})});\n"
              "  return window.hbMaintenanceProbe();\n"
              "}).then(() => { if (reloaded) throw new Error('reloaded over a draft'); if (!els['hb-maint-updated']) throw new Error('no reload bar');"
              " if (els['hb-maintenance'].style.display !== 'none') throw new Error('overlay hides the draft'); console.log('ok'); });")
    assert _node(script).endswith('ok')
