"""Practice 41 (owner 15 Nov): the Potato Farm / tile sweep has ONE checklist with every carried item and its requirement."""
from pathlib import Path

ITEMS = ['S-7D73416326', 'S-68FDE2C6DE', 'S-84F367B310', 'S-76237F9E88', 'S-F7C134D9C6', 'S-E9821587D0', 'S-BAAE9C22D8', 'S-B98A4EFF2C', 'S-35997D7448', 'S-1B90B67986', 'S-94439A14C3', 'S-F3AC8A3D5C', 'S-A98FBEC858', 'S-A1D1B58ED8', 'S-871BF7E9F1', 'S-POTATO-00-INVENTORY', 'S-POTATO-01-CONTRACTS', 'S-POTATO-02-SERVER-SYNC', 'S-POTATO-03-CHAT-SHARING', 'S-POTATO-04-KC-SHARING', 'S-POTATO-05-AGENT-CAPACITY', 'S-POTATO-06-DESKTOP-CLIENT', 'S-POTATO-07-ANDROID-CLIENT', 'S-POTATO-08-APPCENTER', 'S-POTATO-09-E2E-PROOF']


def test_practice_41_potato_farm_checklist_lists_every_item():
    text = (Path(__file__).resolve().parents[1] / 'docs/spec-potato-farm-spec-checklist.md').read_text()
    for sid in ITEMS:
        assert sid in text
    assert text.count('- [ ] ') == 25 and text.count('Requirement: ') == 25
