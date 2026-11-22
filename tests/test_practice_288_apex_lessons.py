"""Practice 288 (JD 22 Nov: "I would also assume you have sent working notes and receipts to HB of all the changes you've made so APEX knows how
you did what"): APEX's card carries four new standing lessons from today's work, and points him to Claude Code's working notes in the KC."""
from core.hb_learning import apex_lessons


def test_todays_lessons_ride_on_every_apex_card():
    text = apex_lessons()
    for words in ('Work ONLY the chunk on your card', "matched 0 locations", "Never hand JD search hits or a tool's error", "knowledge_search 'Claude Code working notes'"):
        assert words in text, words
