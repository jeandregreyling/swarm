"""Practice 244: a missing test file is named as missing, with the next action."""
import subprocess

import pytest

from core import apex_test_runner as r


def test_missing_test_file_says_create_it(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'tests').mkdir()
    with pytest.raises(PermissionError) as e:
        r._tracked_tests(tmp_path, ['tests/test_nothing_here.py'])
    assert 'does not exist yet' in str(e.value) and 'propose_write_file' in str(e.value) and 'run_tests again' in str(e.value)


def test_a_bad_name_still_gets_the_old_refusal(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'tests').mkdir()
    with pytest.raises(PermissionError) as e:
        r._tracked_tests(tmp_path, ['src/thing.py'])
    assert 'Not a tracked or non-ignored' in str(e.value)
