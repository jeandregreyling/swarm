"""V7C-R13 — Studio projects/proposals/test-lab/git ergonomics.

Project: P-E9BAE4159F
Step:    S-FFAB2DFAAE

Locks:
  - Studio default tab is 'projects' (V7C-A01 companion)
  - All 5 tabs exist: pending, in_progress, all (History), projects, git, testlab
  - Governance button present alongside tabs
  - Git panel has visible resizer (#git-files-resizer) — resizable splits
  - Test Lab is prominently styled (info colour) and carries project/step pickers
  - Proposal description/notes textareas support resize:vertical
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPL    = (ROOT / 'frontend' / 'templates' / 'terminal_base.html').read_text()
STUDIO = (ROOT / 'frontend' / 'static' / 'js' / 'views' / 'studio.js').read_text()


def test_r13_r1_default_tab_projects():
    # A01 lock repeated — default must be projects (now via localStorage path).
    assert (
        "localStorage.getItem('studio_last_tab') || 'projects'" in STUDIO
        or "window._studioTab = window._studioTab || 'projects'" in STUDIO
    )
    assert "window._studioTab = 'projects'" in STUDIO


def test_r13_r2_all_five_tabs_present():
    for tab in ('pending', 'in_progress', 'all', 'projects', 'git', 'testlab'):
        assert f'id="studio-tab-{tab}"' in TPL, f'missing tab {tab}'


def test_r13_r3_governance_button():
    assert 'id="studio-btn-governance"' in TPL
    assert "openGovernancePanel()" in TPL


def test_r13_r4_git_resizable_split():
    assert 'id="git-files-resizer"' in TPL
    assert "cursor:col-resize" in TPL
    assert "onmousedown" in TPL[TPL.index('git-files-resizer'):TPL.index('git-files-resizer')+1200]


def test_r13_r5_test_lab_prominent():
    idx = TPL.index('id="studio-tab-testlab"')
    snippet = TPL[idx:idx + 800]
    # Info colour + extra emphasis styling.
    assert '🧪 Test Lab' in snippet
    assert 'var(--info)' in snippet


def test_r13_r6_test_lab_project_step_pickers():
    assert 'id="testlab-project-id"' in TPL
    assert 'id="testlab-step-id"' in TPL
    assert 'testLabOnProjectChange' in TPL


def test_r13_r7_resizable_text_inputs():
    # Proposal editor textareas must be resize:vertical (R13 ergonomics).
    assert 'resize:vertical' in STUDIO
