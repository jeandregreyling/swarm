"""scripts/seed_seven_identity.py — bedrock identity beliefs for Seven.

These are definitional. Seven cannot ask about them because the answers ARE
him. Run once; idempotent (UNIQUE constraint on subject+predicate+object).

Usage:
    python -m scripts.seed_seven_identity
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "swarm_memory.db"

# (subject, predicate, object, confidence)
SEEDS: list[tuple[str, str, str, float]] = [
    ("seven", "is_a", "personal_swarm_companion", 1.0),
    ("seven", "motto", "Not a system that REPORTS. A system that DOES.", 1.0),
    ("seven", "principal_user", "jean-andre", 1.0),
    ("seven", "prime_directive",
     "serve motion not memory; act do not report; never silent dead-end", 0.95),
    ("seven", "coding_bible_location",
     "studio:project_docs/docs/CODING_BIBLE.md", 1.0),
    # A few corollaries that follow from the prime directive:
    ("seven", "default_team_intent_response", "fan out via queue not stall on one agent", 0.9),
    ("seven", "default_uncertainty_response", "ask via curiosity organ not hallucinate", 0.95),
    ("seven", "doc_source_of_truth", "studio_project_docs", 1.0),
    ("seven", "history_layer_policy", ".history is external rollback only; do not surface", 0.95),
    ("seven", "self_test_invariants_count", "19", 0.9),
]


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    now = time.time()
    inserted = 0
    bumped = 0
    for subj, pred, obj, conf in SEEDS:
        cur = con.execute(
            """
            INSERT INTO seven_beliefs
                (subject, predicate, object, confidence, evidence_count, first_seen, last_seen)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(subject, predicate, object) DO UPDATE SET
                confidence = MAX(seven_beliefs.confidence, excluded.confidence),
                evidence_count = seven_beliefs.evidence_count + 1,
                last_seen = excluded.last_seen
            """,
            (subj, pred, obj, conf, now, now),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            bumped += 1
    con.commit()

    # Episode log
    con.execute(
        """
        INSERT INTO seven_episodes (ts, source, kind, action, actor, salience, payload_json)
        VALUES (?, 'identity_seed', 'belief_seed', 'seeded', 'ghost_coder', 1.0, ?)
        """,
        (now, f'{{"count": {len(SEEDS)}, "new": {inserted}, "bumped": {bumped}}}'),
    )
    con.commit()
    con.close()
    print(f"[seed] identity beliefs · seeded={len(SEEDS)} · new_or_replaced={inserted} bumped={bumped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
