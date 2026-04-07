# Environments Reference

## Stage 1: Production
- Port: 5050
- Live system, all changes must be approved and promoted through Stage 2 (UAT) first.

## Stage 2: UAT / Pre-prod
- Port: 5053
- Mirrors production, used for final testing before production.

## Stage 3: DEV
- Port: 5051
- Agent sandboxes, development and proposal work.

## Promotion Flow
- Stage 3 (DEV) → Stage 2 (UAT) → Stage 1 (Production)
- Each promotion step is tracked, logged, and requires explicit approval.

## Stakeholder Communication
- All proposals, threads, and ALM/Studio workflows must reference the current environment.
- Stakeholders are notified at each stage transition.
