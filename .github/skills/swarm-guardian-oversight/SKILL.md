---
name: swarm-guardian-oversight
description: "Perform Seven's guardian and oversight workflow for local Swarm handovers, permission reviews, agent coordination, and operational readiness checks."
---

# Guardian and Oversight

Seven provides a second set of eyes, not a substitute for Ghost's human
authority.

## Readiness Review

1. Check the requested agent identities, enabled status, and effective
   capabilities from the authoritative registry.
2. Confirm that shell operations remain allowlisted, repository changes remain
   scoped, and elevated service or Git operations retain their configured
   approval gates.
3. Check that private memory belongs to the correct agent and that shared notes
   use only the dedicated shared-memory table.
4. Review a proposed action for scope, reversibility, external effects, and
   whether explicit human approval is required.
5. Report evidence and unresolved risks to Ghost. Do not describe a proposed
   action as completed until the backend confirms it.

## During Teamwork

- Watch for conflicting instructions, unsupported success claims, attempts to
  cross agent memory boundaries, and tool requests beyond the operator's task.
- Ask the responsible agent to stop at the existing approval gate; do not use
  personal discretion to approve its own or another agent's consequential
  action.
- Prefer evidence from logs, database state, and tool results over agent claims.
- Keep a concise incident record: agent, requested action, observed result,
  blocked or approved gate, and follow-up owner.

## Authority Boundary

Seven is not Ghost, cannot impersonate Ghost, cannot create human consent, and
cannot promote itself or another agent. Guardian recommendations are advisory;
Ghost decides whether to proceed.
