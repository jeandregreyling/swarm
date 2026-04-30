import sys

sys.path.insert(0, '/home/seven/swarm')

from agents.skill_intent import message_likely_needs_skills


def test_plain_song_prompt_does_not_need_skill_nudge():
    assert message_likely_needs_skills('Llama, write a song about Fridays Studio') is False


def test_media_prompt_without_file_action_does_not_need_skill_nudge():
    assert message_likely_needs_skills('Produce an image prompt for a bright synth board') is False


def test_project_or_file_work_needs_skill_nudge():
    assert message_likely_needs_skills('Fix thread 2321 timeout and add it to the Studio project') is True
    assert message_likely_needs_skills('Read the file and patch the endpoint') is True
