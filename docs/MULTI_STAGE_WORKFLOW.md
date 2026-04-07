# Multi-Stage Proposal & Deployment Workflow

## Overview
This system uses three fully isolated environments for safe, auditable agent work and deployment:

- **Stage 3 (DEV/Sandbox):**
  - Port: 5051
  - Agent sandboxes, development, and proposal authoring
  - Proposals stored in `sandpits_stage3/proposals/`
- **Stage 2 (UAT/Pre-prod):**
  - Port: 5053
  - Mirrors production for user acceptance testing
  - Proposals stored in `sandpits_stage2/proposals/`
- **Stage 1 (Production):**
  - Port: 5050
  - Live system, only approved and tested changes
  - Proposals stored in `sandpits_stage1/proposals/`

## Promotion Flow
1. **Propose & Develop:**
   - Agents work in Stage 3 (DEV), proposals are created and reviewed here.
2. **Promote to UAT:**
   - Once approved, proposals are promoted (copied) to Stage 2 (UAT) for further testing.
3. **Promote to Production:**
   - After UAT signoff, proposals are promoted to Stage 1 (Production) for final deployment.

## Technical Details
- Each stage runs its own Flask server, database, and proposal directory.
- Promotion copies the proposal file to the next stage’s directory, ensuring true isolation.
- The Studio UI displays the current stage and allows promotion with a single click.
- All actions are logged and visible to stakeholders.

## Stakeholder Communication
- The environment (DEV/UAT/PROD) is always visible in the UI and proposal cards.
- All promotions and approvals are tracked and auditable.
- Stakeholders are notified at each stage transition.

## Directory Structure
- `sandpits_stage3/` — DEV proposals and sandboxes
- `sandpits_stage2/` — UAT proposals and sandboxes
- `sandpits_stage1/` — Production proposals and sandboxes

## Example Workflow
1. User requests a feature in chat/ALM.
2. Agent creates a proposal in DEV (Stage 3).
3. Proposal is reviewed and promoted to UAT (Stage 2).
4. After UAT testing, proposal is promoted to Production (Stage 1).
5. Change is deployed, and all steps are logged.
