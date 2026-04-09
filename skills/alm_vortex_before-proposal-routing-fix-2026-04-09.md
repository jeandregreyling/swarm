# SKILL: alm_vortex
# Before Proposal Routing Fix — 2026-04-09

## Purpose
Documents the ALM (Application Lifecycle Management) workflow, environment separation, and proposal routing logic as it existed before the 2026-04-09 proposal routing fix.

## Key Features (Pre-Fix)
- **Strict Environment Separation:**
  - DEV (Mondays, 5051), UAT (Wednesdays, 5053), PROD (Fridays, 5050) each run on fixed ports with clear banners and UI separation.
  - Glowing banners for DEV/UAT at the very top; PROD is clean with only compact navigation.
- **Persistent Documentation & Guardrails:**
  - Startup scripts and code document required PORT/STAGE env vars and port-to-environment mapping.
  - Only the correct environment banner appears; no "unknown environment" in PROD.
- **UI/UX:**
  - Banners and navigation buttons are at the top, never blocking controls.
  - In PROD, DEV/UAT buttons are compact and unobtrusive.
- **Proposal Routing (Pre-Fix):**
  - Proposal status transitions and promote endpoints are robust, auto-selecting the next valid stage.
  - All changes are auditable; UI reflects current environment at all times.
  - Manual service controls and dropdowns are fully accessible.
- **ALM Workflow:**
  - DEV → UAT → PROD flow is enforced and visible.
  - All environments are up and accessible; switching is seamless.

## Known Issues (Pre-Fix)
- Proposal routing logic may have edge cases or bugs (to be addressed in the 2026-04-09 fix).
- UI in PROD is functional but could be further refined for aesthetics.

## Audit/Traceability
- This skill snapshot documents the state of the ALM and proposal routing system immediately before the 2026-04-09 routing fix for future reference and rollback.

---
