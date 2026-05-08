"""One-shot demo: morph thread -> ticket -> proposal -> project, then walk the chain."""
from core.records.promote import promote, promotion_chain
from core.records.links import neighbours
import json

t = ("thread", "2230")
print(f"start: {t[0]} {t[1]}")
tk = promote(*t, "ticket",
             overrides={"title": "Demo morph", "description": "Auto-promoted thread → ticket"},
             actor="demo")
print(f"  → ticket   {tk[1]}")
pr = promote(*tk, "proposal", actor="demo")
print(f"  → proposal {pr[1]}")
p = promote(*pr, "project", actor="demo")
print(f"  → project  {p[1]}")
print()
print("promotion chain (walked from proposal):")
for k, i in promotion_chain(*pr):
    print(f"  {k:>10}  {i}")
print()
print(f"neighbours on the new ticket {tk[1]} (truncated):")
print(json.dumps(neighbours(*tk), indent=2)[:800])
print()
print(f"NEW_TICKET={tk[1]}")
print(f"NEW_PROPOSAL={pr[1]}")
print(f"NEW_PROJECT={p[1]}")
