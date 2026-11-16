"""Practice 40 (owner 15 Nov): the Media Center DAW review has ONE list with every review item, its requirement and its check."""
from pathlib import Path

ITEMS = ['S-CF7CEFF966', 'S-AEB5C3BA63', 'S-8FAF92FC8A', 'S-FA3A549338', 'S-74C766866B', 'S-A93F5BC258', 'S-418CED353E', 'S-77A1E417B9', 'S-8C96C97BBC', 'S-26443908EA', 'S-4F03C422B3']


def test_practice_40_daw_review_is_one_list_with_a_check_per_item():
    text = (Path(__file__).resolve().parents[1] / 'docs/spec-media-center-daw-review.md').read_text()
    for sid in ITEMS:
        assert sid in text
    assert text.count('Requirement: ') == 11 and text.count('Check: ') == 11 and text.count('Done when: ') == 11
