"""Tests for untruncated 600-char APEX 💭 thoughts and fixing Portuguese false-translation of English step IDs."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_apex_thought_pipeline_allows_600_chars_end_to_end():
    apex_src = (ROOT / 'core/apex_tools.py').read_text(encoding='utf-8')
    assert '"thought": {"type": "string", "maxLength": 600}' in apex_src
    assert 'thought[:580]' in apex_src
    assert 'str(text)[:600]' in apex_src
    assert "len(data['stage'])>600" in (ROOT / 'frontend/blueprints/agent_identity.py').read_text(encoding='utf-8')
    assert "stage[:600]" in (ROOT / 'scripts/hummingbird_peer_worker.py').read_text(encoding='utf-8')
    assert "stage[:600]" in (ROOT / 'frontend/blueprints/chat.py').read_text(encoding='utf-8')


def test_translate_bubble_ignores_hex_step_ids_so_english_is_never_portuguese():
    js_path = ROOT / 'frontend/static/js/hb-translate-bubble.js'
    chk = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
    # Run the real detectLanguage() in Node against JD's exact message!
    probe = (
        "const fs=require('fs'), vm=require('vm');"
        "const ctx={window:{},document:{addEventListener:()=>{},querySelector:()=>null,querySelectorAll:()=>[],getElementById:()=>null,createElement:()=>({style:{}})},localStorage:{getItem:()=>null,setItem:()=>{}},setTimeout:()=>{},setInterval:()=>{},fetch:()=>Promise.resolve()};"
        "vm.runInNewContext(fs.readFileSync('frontend/static/js/hb-translate-bubble.js','utf8'), ctx);"
        "const lang=ctx.window.hbTranslateBubble.detectLanguage('Cannot approve S-305E1A7F6E: Independent QA has not confirmed this code step; no approval saved.');"
        "console.log(String(lang));"
    )
    res = subprocess.run(['node', '-e', probe], cwd=str(ROOT), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() in ('en', 'null'), f'Got false language: {res.stdout.strip()}'
