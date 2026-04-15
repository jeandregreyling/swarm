"""Shared proposal workflow status helpers.

This keeps Studio, Duck, and skill-side ALM logic aligned on one lifecycle:
pending -> approved -> in_progress -> done -> uat -> closed

`executed` remains accepted as a legacy alias so older rows and callers still
read cleanly, but new writes should use `closed`.
"""

STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_IN_PROGRESS = 'in_progress'
STATUS_DONE = 'done'
STATUS_UAT = 'uat'
STATUS_CLOSED = 'closed'
STATUS_REJECTED = 'rejected'
STATUS_EXECUTED_LEGACY = 'executed'

ALL_PROPOSAL_STATUSES = {
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_IN_PROGRESS,
    STATUS_DONE,
    STATUS_UAT,
    STATUS_CLOSED,
    STATUS_REJECTED,
}

ACTIVE_PROPOSAL_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_IN_PROGRESS,
    STATUS_DONE,
    STATUS_UAT,
)

OPEN_PROPOSAL_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_IN_PROGRESS,
)

STATUS_ALIASES = {
    STATUS_EXECUTED_LEGACY: STATUS_CLOSED,
}


def normalize_proposal_status(status):
    value = str(status or '').strip().lower()
    if not value:
        return ''
    return STATUS_ALIASES.get(value, value)
