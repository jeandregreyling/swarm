"""Tests for Phase 2 Git Secret Hardening & OptiPlex / Potato Farm Reproducibility."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_secrets_are_gitignored_and_untracked():
    gi = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for entry in ('runtime/.hb_nectar_key', 'utils/telegram_config.py', 'runtime/change_sets/', '*.key'):
        assert entry in gi
    if shutil.which('git') and (ROOT / '.git').exists():
        for secret in ('runtime/.hb_nectar_key', 'utils/telegram_config.py'):
            chk = subprocess.run(['git', 'check-ignore', '-q', secret], cwd=ROOT)
            assert chk.returncode == 0, f'{secret} must be ignored by git'
            tr = subprocess.run(['git', 'ls-files', '--error-unmatch', secret], cwd=ROOT, capture_output=True)
            assert tr.returncode != 0, f'{secret} must NOT be tracked in git'


def test_bootstrap_script_portable_and_valid_bash():
    sh = ROOT / 'scripts/bootstrap_node.sh'
    text = sh.read_text(encoding='utf-8')
    assert '/home/jd' not in text
    assert '/srv/archive' not in text
    assert 'verify_portability.py' in text
    res = subprocess.run(['bash', '-n', str(sh)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_verify_portability_passes():
    from scripts.verify_portability import run_checks
    report = run_checks()
    assert report['ok'] is True, report['errors']
    assert (ROOT / 'utils/telegram_config.example.py').exists()
