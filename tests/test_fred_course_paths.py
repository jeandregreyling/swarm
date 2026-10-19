"""Every file path named in the Fred course must exist, so the map cannot drift into guesses."""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSE = os.path.join(ROOT, 'docs', 'fred_course')
_TOKEN = re.compile(r'`([A-Za-z0-9_./-]+)`')
_FILE_EXT = ('.py', '.js', '.css', '.html', '.md', '.json')


def _missing_paths(text):
    missing, checked = [], 0
    for line in text.splitlines():
        tokens = _TOKEN.findall(line)
        dirs = [t for t in tokens if t.endswith('/')]
        for token in tokens:
            if token.endswith('/'):
                checked += 1
                if not os.path.isdir(os.path.join(ROOT, token)):
                    missing.append(token)
            elif '/' in token:
                checked += 1
                if not os.path.exists(os.path.join(ROOT, token)):
                    missing.append(token)
            elif token.endswith(_FILE_EXT):
                checked += 1
                # A bare file name must sit inside a directory named on the same line.
                found = any(
                    glob.glob(os.path.join(ROOT, d, '**', token), recursive=True) for d in dirs
                )
                if not found:
                    missing.append(f'{token} (not under {dirs or "any directory on its line"})')
    return missing, checked


def test_every_path_in_the_finding_things_module_exists():
    text = open(os.path.join(COURSE, '08-finding-things.md'), encoding='utf-8').read()
    missing, checked = _missing_paths(text)
    assert checked > 30
    assert not missing, f'paths in the course that do not exist: {missing}'


def test_a_made_up_path_is_caught():
    missing, _ = _missing_paths('- `frontend/blueprints/` has `chat.py` and `nonexistent_page.py`')
    assert missing and 'nonexistent_page.py' in missing[0]


def test_course_modules_have_loader_headers():
    for name in sorted(os.listdir(COURSE)):
        first = open(os.path.join(COURSE, name), encoding='utf-8').readline()
        assert re.match(r'FRED-COURSE-[A-Z0-9-]+\s+—', first), name
