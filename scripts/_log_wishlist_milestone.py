#!/usr/bin/env python3
"""Log the WISHLIST capture as a milestone note."""
import os
import sys
# S-7C7ED96F5B — resolve repo root relative to this file (override via SWARM_ROOT)
_SWARM_ROOT = os.environ.get(
    "SWARM_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)
from scripts.studio_milestone import log_milestone

story = """\
WISHLIST capture — recorded so the thoughts don't escape. NOT TO BE BUILT YET.

User context (verbatim cues):
- "financial analytics" must be **investment-banking oriented**, not personal/consumer finance.
- "Business" should be an **operational centre for setting up an online business** — an actual run-the-company toolkit, not a CRM. Accounting + Payroll is the spine; everything else (People, Policies, Stock, Vendors, Products/Sales) hangs off it.
- "Crypto" deserves a slot but the user prefers the framing "online trading" / "gamble your life away into a pyramid scheme". It's real, people use it, build the placeholder.
- **Cyber Security must be an explicit Diamond-tier governance pillar** — the goal is "this system is unhackable". Treat it on par with Vortex, not as an afterthought.

Pillars logged as steps under [WISHLIST] epic S-45064ED6C5:
  1. Cyber Security as Diamond Layer (S-4697ECA1EC) — threat model, hardening, IDS, dep-scanning, secret rotation, sandbox boundaries, explicit governance role.
  2. Financial Analytics — IB-oriented (S-98CF85A8C4) — equity/FI/derivatives, M&A pipeline, portfolio risk, deal flow, league tables, data-room pattern.
  3. Business Operational Centre (S-D618CF4B7A) — the we-can-do-anything scaffold for running an actual online business.
  4. Business: Accounting + Payroll (S-25AFB74A4D) — foundational; double-entry, invoices, tax, payroll flows from ledger.
  5. Business: Manage People (S-642D6439DE) — employee files, contracts, leave, performance, onboarding/offboarding; ties into Payroll.
  6. Business: Policies + Legal & Compliance (S-B6D5701E4F) — versioned policy library, sign-offs, regulatory checklists per jurisdiction.
  7. Business: Stock + Vendor Management (S-5393AEF947) — inventory, POs, vendor contracts, stock reconciliation, supplier scoring.
  8. Business: Products + Sales Portal (S-2B6BC7A021) — catalogue, pricing, orders, customer accounts, online checkout; integrates with Accounting + Stock.
  9. Online Trading / Crypto (S-03A241D177) — market data, order routing, P&L, risk.

Sequencing note: the user said "we have enough at the moment, just log it". These do NOT enter the active build queue. Next active packets continue: PACKET-10B (Curiosity organ), then whatever the user picks next.

Cyber Security note: the user described this as "next 6 months work planned out as well". When it does come up, treat it as a true Diamond-layer governance pillar — sits alongside Vortex (recoverability), Backups (durability), Self-test (correctness). The triad becomes a tetrad: Security (confidentiality + integrity + auth boundary).
"""

print(log_milestone(
    packet="WISHLIST",
    title="Future pillars captured — Business / Financial / Trading / Cyber Security",
    story=story,
    status=None,
))
