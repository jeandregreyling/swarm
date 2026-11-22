# Test for plan chunk visibility before step start.
#
# This test imports the hb_chunks module, creates a dummy step spec with chunks,
# and verifies that the plan view (via hb_chunks.plan) returns the expected
# chunk structure. It also checks that the live snapshot contains the chunks
# before the step is executed.

import pytest
from core import hb_chunks

# Dummy step spec mimicking a real step with chunks
step_spec = {
    "id": "S-FAKE",
    "chunks": {
        "total": 3,
        "done": 0,
        "doing": 0,
        "next": 1,
        "list": ["chunk1", "chunk2", "chunk3"],
    },
}


def test_plan_import_and_structure():
    """Ensure hb_chunks.plan returns the correct structure for a step."""
    plan = hb_chunks.plan(step_spec)
    assert plan["total"] == 3
    assert plan["done"] == 0
    assert plan["doing"] == 0
    assert plan["next"] == 1
    assert plan["list"] == ["chunk1", "chunk2", "chunk3"]


def test_live_snapshot_includes_chunks():
    """Verify that the live snapshot contains the step's chunks before start."""
    from core import hb_live
    snapshot = hb_live.build_snapshot()
    step_item = next((i for i in snapshot["items"] if i["id"] == "S-FAKE"), None)
    assert step_item is not None
    assert step_item["chunks"] == step_spec["chunks"]
