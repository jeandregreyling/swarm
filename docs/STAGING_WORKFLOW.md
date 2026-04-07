# Multi-Stage Deployment Workflow

## Stages
- **Stage 3 (DEV):** Agent sandboxes, development, port 5051
- **Stage 2 (UAT/Pre-prod):** Pre-production, mirrors production, port 5053
- **Stage 1 (Production):** Live system

## Promotion Flow
1. Proposal created and worked on in Stage 3 (DEV)
2. After approval, promoted to Stage 2 (UAT/Pre-prod) for further testing
3. Final approval promotes to Stage 1 (Production)

## Agent Sandbox Linkage
- Each agent's sandbox is mapped to Stage 3 (DEV) by default
- Promotion between stages is tracked in the proposal workflow

## Audit Trail
- All actions, approvals, and promotions are logged and linked to the originating thread/proposal
