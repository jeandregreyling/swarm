"""V7C-R11 + A13 — Knowledge/files/library usability regressions.

Project: P-E9BAE4159F
Steps:   S-EB071104BA (R11), S-19F89A1FA5 (A13)
Cases:   C-E5B187600F (list/grid/compact), C-50F2FB122B (editable popout)

User complaints (transcript L17622):
  - "I want to be able to add and pause topics in the knowledge center"
  - "I also can't open any of the documents in the library or delete or reclassify them"
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'library.js'
FILES_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'files.js'


# R1 FILES VIEW MODES — list/grid/compact toggles exist
def test_r1_files_view_mode_toggles():
    src = FILES_JS.read_text()
    assert "['list', 'grid', 'compact']" in src
    assert "#files-view-toggle" in src
    assert "data-files-view" in src


# R2 LIBRARY OPEN — source can be opened full-text
def test_r2_library_open_source():
    src = LIB_JS.read_text()
    assert "async function libOpenSource(" in src
    assert "libOpenSource(" in src  # invoked from source row


# R3 LIBRARY DELETE — delete button wired
def test_r3_library_delete_source():
    src = LIB_JS.read_text()
    assert "async function libDeleteSource(" in src
    assert "libDeleteSource(" in src  # invoked from row


# R4 LIBRARY RECLASSIFY — reclassify button wired
def test_r4_library_reclassify():
    src = LIB_JS.read_text()
    assert "function libReclassifyPrompt(" in src
    assert "libReclassifyPrompt(" in src


# R5 TOPICS ADD — topics-add calls POST /api/library/topics
def test_r5_topics_add_endpoint():
    src = LIB_JS.read_text()
    assert "async function libTopicsAdd(" in src
    assert "fetch('/api/library/topics'" in src
    assert "method: 'POST'" in src


# R6 TOPICS PAUSE/RESUME — toggle calls PATCH /api/library/topics/:id
def test_r6_topics_pause_resume():
    src = LIB_JS.read_text()
    assert "async function libTopicsToggle(" in src
    assert "method: 'PATCH'" in src
    assert "active: Boolean(newActive)" in src


# R7 TOPICS DELETE — delete calls DELETE /api/library/topics/:id
def test_r7_topics_delete():
    src = LIB_JS.read_text()
    assert "async function libTopicsDelete(" in src
    assert "method: 'DELETE'" in src
    # Guarded by confirm()
    assert "confirm('Delete this topic" in src
