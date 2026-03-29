# Decision 003: Create Time Wizard Fridays Dashboard Tile

**Status**: PROPOSED  
**Decision ID**: 003  
**Proposed**: 2026-03-29T00:25:00Z  
**Agent**: Twelve (Time Wizard)  
**Git Commit Hash**: [PENDING]  

## Issue
Time Wizard infrastructure is operational (API endpoints working, decisions logged), but users cannot see the decision history in Fridays UI. Decision data is hidden behind API calls—no visual interface to query or understand decision graph.

**Current state**: 
- `/api/decisions` endpoint returns data
- `/api/timeline` endpoint returns chronological list
- `/api/decisions/<id>` returns full decision details

**Missing**: Fridays dashboard tile to visualize this data

## Root Cause
Time Wizard was implemented for backend infrastructure first (API, database, logging). Frontend visualization was deferred (DECISION-002 marked as ⏳ PENDING). Users must manually curl endpoints to see decisions—not user-friendly.

## Proposed Solution

### Component 1: Time Wizard Tile in Fridays Dashboard
Add new tile to `frontend/templates/terminal_ui_v2.html`:
- **Tile Name**: "⏳ Time Wizard"
- **Location**: Fridays dashboard (8th tile, after Docs)
- **Size**: Full-width accordion/timeline view
- **Color**: Purple/indigo (#6B7280 styling)

### Component 2: Timeline Display
```
Decision Timeline:
├─ 2026-03-29 DECISION-002 (EXECUTED) ✅ Audit & Update Documentation
│  └─ Impact: HIGH | Status: PASS (10/10 tests) | Commit: 280db36
├─ 2026-03-29 DECISION-001 (EXECUTED) ✅ Fix /api/agents
│  └─ Impact: CRITICAL | Status: PASS (ALL TESTS) | Commit: 0ecba42
```

### Component 3: Decision Detail Panel
Click any decision to expand:
- Issue summary
- Proposed solution (first 200 chars)
- Test results (pass/fail status)
- Commit hash with link
- Decision file location

### Component 4: Search/Filter
- Filter by status (PROPOSED, TESTING, EXECUTED, ARCHIVED)
- Filter by impact (CRITICAL, HIGH, MEDIUM, LOW)
- Search by decision ID or title

### Implementation Scope
**Files to modify**:
1. `frontend/templates/terminal_ui_v2.html`
   - Add `<div id="time-wizard-tile">` (lines ~1800)
   - Add `loadTimeWizard()` function (lines ~1600)
   - Add `expandDecision(id)` function with modal
   - Add styling for timeline UI (lines ~150 in `<style>`)
   - Wire tile click handler

2. No backend changes required (API already exists)

**Estimated changes**:
- HTML: ~150 lines (tile structure + modal)
- JavaScript: ~200 lines (API calls, DOM manipulation)
- CSS: ~80 lines (timeline styling, colors, hover states)
- **Total**: ~430 lines

## Expected Outcome
After completion:
- ✅ "⏳ Time Wizard" tile appears in Fridays dashboard
- ✅ Displays reverse-chronological timeline of all decisions
- ✅ Users can click decisions to see details
- ✅ Filter and search options work
- ✅ Shows status (PROPOSED, EXECUTING, EXECUTED)
- ✅ Shows test results (PASS/FAIL)
- ✅ Links to commit hashes
- ✅ No API failures or errors

## Testing Plan

### T1: Tile Rendering
- [ ] Page loads without errors (console clean)
- [ ] "⏳ Time Wizard" tile appears in dashboard
- [ ] Tile has correct styling and colors
- [ ] All controls visible (search, filters)

### T2: API Integration
- [ ] loadTimeWizard() calls /api/timeline successfully
- [ ] Response parsed correctly
- [ ] All decisions appear in timeline
- [ ] Timeline is reverse-chronological (newest first)

### T3: Timeline Display
- [ ] All decisions show ID, status, impact, date
- [ ] Icons/badges correct (✅ for EXECUTED, ⏳ for PENDING)
- [ ] Timestamps are readable format
- [ ] Hover states show tooltips

### T4: Decision Detail Expansion
- [ ] Click decision expands/collapses correctly
- [ ] Modal shows Issue, Solution, Tests, Impact
- [ ] Commit hash is clickable (or shows as text)
- [ ] Modal closes cleanly

### T5: Filter/Search
- [ ] Filter by status works (EXECUTED shows 2, etc.)
- [ ] Filter by impact works (CRITICAL shows 1, etc.)
- [ ] Search by ID/title finds decisions
- [ ] Clear filters button works

### T6: Error Handling
- [ ] Network error shows user message
- [ ] Empty decision list shows "No decisions" message
- [ ] Missing decision data doesn't crash UI
- [ ] 404 on /api/timeline gracefully handled

### T7: Responsive Design
- [ ] Tile looks good on desktop (1920x1080)
- [ ] Tile looks good on tablet (800x600)
- [ ] No horizontal scrolling needed
- [ ] Text readable on all sizes

### T8: Integration with Other Tiles
- [ ] Other tiles still render (no breaking changes)
- [ ] Refresh button affects Time Wizard correctly
- [ ] No memory leaks (multiple loads)
- [ ] No conflicts with other tile JavaScript

### T9: Data Accuracy
- [ ] Displayed decisions match /api/timeline response
- [ ] Decision details match /api/decisions/<id> response
- [ ] Test results match stored logs (PASS/FAIL)
- [ ] Commit hashes are correct

### T10: Edge Cases
- [ ] Works when API returns empty array
- [ ] Works with 1 decision
- [ ] Works with 100 decisions (performance ok)
- [ ] Works if decision has missing fields

## Risk Assessment

### Risk Level: **MEDIUM**
(New feature, but contained to UI only—no backend changes)

### Risks Identified
1. **API dependency**: If /api/timeline breaks, tile fails
   - **Mitigation**: Endpoint already tested (T2 validates)
   - **Rollback**: Can hide tile with CSS display:none

2. **DOM conflicts**: New tile might conflict with existing JS
   - **Mitigation**: Use unique IDs (time-wizard-tile, expandDecision)
   - **Rollback**: Remove HTML/JS, restore from git

3. **Performance**: Large number of decisions loads slow
   - **Mitigation**: Limit initial display to 20, pagination available
   - **Rollback**: Revert to previous version if too slow

4. **Styling breaks layout**: New CSS breaks responsive design
   - **Mitigation**: Test on multiple sizes (T7)
   - **Rollback**: Revert CSS changes only

5. **User confusion**: Timeline/UI unclear to users
   - **Mitigation**: Add help text and tooltips
   - **Rollback**: Hide tile until CX improved

### Rollback Plan
If implementation fails:
```bash
git revert <commit-hash>
# Or selectively:
git checkout HEAD -- frontend/templates/terminal_ui_v2.html
```

## Code Changes
Files affected:
- `frontend/templates/terminal_ui_v2.html` (+430 lines)
  - Lines ~150: CSS for timeline styling
  - Lines ~1600: loadTimeWizard() function
  - Lines ~1700: expandDecision() function  
  - Lines ~1800: Time Wizard tile HTML structure
  - Lines ~500: Add to tile event handlers

No backend changes required.

## Decision Chain Dependencies
- Depends on: DECISION-001 (API implementation), DECISION-002 (documented procedures)
- Blocks: None (enhancement only)
- Enables: User visibility into decision history
- Enables: Team awareness of what decisions have been made

## Implementation Notes

### Design Principles
1. **Non-invasive**: Only adds a new tile, doesn't modify existing tiles
2. **Fallback-safe**: If API unavailable, shows graceful error
3. **Consistent styling**: Uses existing theme engine (line ~200 in HTML)
4. **Accessible**: Keyboard navigation supported, ARIA labels added

### Technology Use
- **Language**: Vanilla JavaScript (no new dependencies)
- **Styling**: Inline CSS (matches existing tile pattern)
- **API Integration**: Fetch API (like other tiles)
- **DOM manipulation**: querySelector/innerHTML (existing patterns)

### File Organization
All code stays in one file (`terminal_ui_v2.html`):
- Matches existing architecture
- No new files to maintain
- All related code in one place for easy debugging

## Success Criteria

**After this decision is EXECUTED and COMMITTED, this should be true:**

1. ✅ Fridays dashboard has "⏳ Time Wizard" tile (visible immediately)
2. ✅ Tile shows reverse-chronological timeline of all decisions
3. ✅ Users can click decisions to see details
4. ✅ Filter/search options work correctly
5. ✅ All 10 test cases pass (T1-T10)
6. ✅ No console errors or warnings
7. ✅ Other dashboard tiles still work
8. ✅ No performance degradation
9. ✅ Commit message references DECISION-003
10. ✅ Full traceability in test logs

## Timeline Estimate
- **Design + Planning**: 15 min (this proposal)
- **Implementation**: 30 min (write HTML/JS/CSS)
- **Testing**: 20 min (T1-T10 manual tests)
- **Refinement**: 15 min (fix issues found in testing)
- **Documentation**: 10 min (update logs, commit)
- **Total**: ~90 minutes

## Open Questions

Before implementation, confirm:
1. Should Time Wizard tile be first or last in dashboard? (Proposed: position 8, last)
2. Should timeline show ARCHIVED decisions? (Proposed: yes, all decisions)
3. Should search be real-time (as you type) or submit button? (Proposed: real-time)
4. Maximum decisions to display before pagination? (Proposed: 20 per page)
5. Should modal open in new window or in-page overlay? (Proposed: in-page overlay)

