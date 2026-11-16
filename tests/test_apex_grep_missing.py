"""Practice 42 (owner 15 Nov): System cleanup 2 stopped because grep_repo over the whole repo failed on APEX_TIERED_SETUP.md,
a tracked file that had been deleted from disk. A missing tracked file is skipped; the search goes on."""
from test_apex_read_tools import repository  # noqa: F401


def test_practice_42_grep_skips_a_tracked_file_missing_on_disk(repository):
    (repository.root / "gone.md").write_text("world\n")
    import subprocess
    subprocess.run(["git", "-C", str(repository.root), "add", "gone.md"], check=True)
    (repository.root / "gone.md").unlink()
    out = repository.call("grep_repo", {"query": "world"})
    assert "sample.py:2: world" in out and "gone.md" not in out and "complete:" in out
