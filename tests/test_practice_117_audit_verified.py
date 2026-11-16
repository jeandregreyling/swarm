"""Practice 117 (monitoring 16 Nov 2026, 22:27): on components.css the reviewer called 23 lines "hard-coded colour", among them
"filter: blur(0.2px)", "opacity: 0.18" and a line already using var(--accent). Findings HB can check are now checked, and one kind never
floods a step."""
from core import hb_file_audit as a


def f(line, kind, code):
    return {'line': line, 'kind': kind, 'problem': 'something about this line', 'fix': 'x', 'code': code}


def test_practice_117_colour_and_icon_findings_must_be_on_the_line():
    assert a.verified(f(19, 'hard-coded-colour', 'color: #000;'))
    assert a.verified(f(202, 'hard-coded-colour', 'radial-gradient(60% 40% at 20% 30%, rgba(138,26,43,0.40), transparent 60%),'))
    for code in ('filter: blur(0.2px);', 'opacity: 0.18;', '0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent),', '--accent: #6aa9ff;'):
        assert not a.verified(f(1, 'hard-coded-colour', code)), code
    assert a.verified(f(3, 'old-icon', "label: '🌺 Thanks'")) and not a.verified(f(3, 'old-icon', "label: 'Thanks'"))
    assert a.verified(f(9, 'cannot-work', 'document.getElementById("nope")'))


def test_practice_117_one_kind_never_floods_a_step():
    many = [f(n, 'hard-coded-colour', f'color: #{n:03d};') for n in range(100, 112)]
    kept = a.keep(many + [f(5, 'hard-coded-colour', 'opacity: 0.2;')])
    assert len(kept) == a.PER_KIND + 1 and kept[-1]['problem'] == 'and 7 more like it in this file'
    assert a.keep([f(1, 'hard-coded-colour', 'opacity: 0.2;')]) == []
