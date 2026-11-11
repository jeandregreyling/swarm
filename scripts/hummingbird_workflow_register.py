#!/usr/bin/env python3
"""Record the owner's HB workflow acceptance backlog without claiming completion."""
from pathlib import Path
import sys
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'frontend'), str(ROOT/'utils')]

STEPS = [
    ('Verify the existing Codex connection in main chat',
     'Send a fresh operator tag in HB. Require an actual Codex provider answer, an authenticated HB tool receipt, saved reply readback and inbox acknowledgment. Login authentication alone is not provider connectivity.'),
    ('Verify an autonomous APEX source change and rollback',
     'Use the existing owner standing write grant. Create a bounded proof file through main chat, read it back, inspect actor/model/request and before/after receipts, then exercise rollback. Keep code work isolated from concurrent edits.'),
    ('Make ALM work executable and visible in main chat',
     'Backlog reads now use real ALM projects and steps. Finish scoped create/update/claim tools, outcome-linked step changes, failure visibility and cross-process isolated worktrees. Do not mark tasks done merely because a model answered.'),
    ('Verify local routing and explicitly invited online review',
     'Keep local model selection in the harness. Test an owner tag and APEX ask_instructor handoff with real provider evidence. Online agents must not be recruited by an untagged broadcast. Other registered online providers still need their own attached runtime checks.'),
    ('Verify tools, skills, Authorisations and recovery in HB',
     'Walk through the existing terminal, ALM Studio, Authorisations, skill discovery, time machine and themes with JD. The new terminal adapter exposes bounded diagnostics under existing grants; full skill execution and elevated actions still need integration checks.'),
    ('Mirror every accessible file in every public Hub repository',
     'Owner explicitly selected all public files, not a curated subset. Enumerate models, datasets and Spaces and pin each observed revision; record inaccessible/gated items and failures. Historical revisions and other Hub storage families require separate coverage review. The remembered 150 GB total is unverified. Never report the goal complete from catalogue discovery alone.'),
    ('Index verified Hugging Face text for local retrieval',
     'Index verified cards/manifests into the real Knowledge Centre and stream textual Parquet examples into resumable local FTS. Confirm queries return row/revision citations. Binary weights, arbitrary formats and model training are separate; downloading does not train APEX.'),
    ('Measure storage, active swap and comparable response times',
     'Observed on 7 Nov: about 62 GiB RAM, no active swap visible in /proc/swaps; NVMe about 547 GiB free; mounted SATA /mnt/archive about 1.5 TiB free. A second roughly 2 TB SATA partition is unmounted; do not format or mount it automatically. Verify provisioned swap on host, then compare like tasks using recorded latency, swap and fault counters.'),
    ('Repair VS Code and investigate yesterday’s changes',
     'Capture real EMFILE/inotify/extension/update and broken-pipe errors, inspect watch scope and resource limits, then repair from evidence. Do not attribute yesterday’s changes to Vibe or another model without audit evidence. Keep HB usable during this work.'),
]


def register():
    from core.knowledge import projects
    from core import agent_identity
    with agent_identity.execution('codex-instructor', requested_by='ghost', conversation_id=2833) as actor:
        project = projects.create_project('HB main interface and local learning', owner='apex',
            idempotency_key='hb-workflow-20261107', tags=['hummingbird','owner-request','acceptance'],
            description='Owner-authorized workflow repair. Staged tests are evidence about code, not proof of live acceptance. Main chat is the working interface; all remaining acceptance checks stay visible here.')
        if not project:
            raise RuntimeError('HB did not create or retrieve the workflow project')
        existing = {row['title']: row['step_id'] for row in projects.list_steps(project)}
        added = []
        for title, description in STEPS:
            if title in existing:
                continue
            step = projects.add_step(project, title, description=description, owner='apex')
            if not step:
                raise RuntimeError('HB did not save acceptance step: '+title)
            added.append(step)
        agent_identity.event(actor, uuid.uuid4().hex, 'workflow_register', 'succeeded',
            result={'project_id':project,'added_steps':added,'acceptance':'pending live main-chat checks'})
    return {'project_id':project,'added_steps':added,'acceptance':'pending live main-chat checks'}


if __name__ == '__main__':
    import json
    print(json.dumps(register(), indent=2))
