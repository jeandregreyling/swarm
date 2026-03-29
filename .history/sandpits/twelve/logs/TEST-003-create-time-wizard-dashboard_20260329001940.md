# Test Plan for DECISION-003

**Decision**: Create Time Wizard Fridays Dashboard Tile  
**Test ID**: TEST-003  
**Date**: 2026-03-29 (to be executed before implementation)  

---

## Pre-Implementation Tests (BEFORE coding)

### Verify Preconditions
These must be true BEFORE we write any HTML/JS:

#### PC1: API Endpoints Operational
```bash
Test: curl -s http://127.0.0.1:5050/api/timeline | python3 -m json.tool
Expected: Valid JSON with timeline array
Status: ⏳ TO RUN
```

#### PC2: Service Is Running
```bash
Test: ps aux | grep "frontend/terminal.py" | grep -v grep
Expected: Process found, running normally
Status: ⏳ TO RUN
```

#### PC3: HTML Template Accessible
```bash
Test: test -f /home/seven/swarm/frontend/templates/terminal_ui_v2.html
Expected: File exists and is readable
Status: ⏳ TO RUN
```

#### PC4: No Errors on Page Load
```bash
Test: Open http://127.0.0.1:5050 in browser, check console
Expected: No errors, page loads cleanly
Status: ⏳ TO RUN
```

---

## Post-Implementation Tests (AFTER code is written)

### T1: Tile Rendering ✅ CRITICAL
**Purpose**: Verify tile appears in dashboard without errors

```javascript
// Manual test in browser console:
console.log(document.getElementById('time-wizard-tile') !== null);
// Expected: true

// Check console for errors:
// Should see: 0 errors, 0 warnings related to Time Wizard
```

**Steps**:
1. Refresh Fridays page
2. Look for "⏳ Time Wizard" tile in dashboard
3. Check browser console (F12) for errors
4. Verify tile styling looks correct
5. Verify all buttons visible (search, filter, etc.)

**Pass Criteria**:
- ✅ Tile visible in dashboard
- ✅ No JavaScript errors in console
- ✅ No CSS errors or unstyled elements
- ✅ Title text readable
- ✅ Buttons are clickable

---

### T2: API Integration ✅ CRITICAL
**Purpose**: Verify Time Wizard tile correctly fetches and parses API response

```javascript
// Check network tab:
// Should see: GET /api/timeline returns 200
// Response: valid JSON with decisions array

// Check that timeline was populated:
const tiles = document.querySelectorAll('.decision-row');
console.log(`Found ${tiles.length} decisions in timeline`);
// Expected: 2 (DECISION-001, DECISION-002)
```

**Steps**:
1. Open browser DevTools (F12)
2. Go to Network tab
3. Refresh Fridays page
4. Look for GET /api/timeline request
5. Verify status is 200 (not 404, 500, etc.)
6. Look at Response tab → verify JSON is valid
7. Verify response includes:
   - timeline array
   - decision objects with: decision_id, status, proposed, title

**Pass Criteria**:
- ✅ /api/timeline returns HTTP 200
- ✅ Response is valid JSON
- ✅ All decisions included
- ✅ Timeline parsed and displayed

---

### T3: Timeline Display ✅ CRITICAL
**Purpose**: Verify decisions render in correct order with proper styling

**Visual Inspection**:
1. Open Time Wizard tile
2. Verify timeline shows decisions in reverse-chronological order:
   - DECISION-002 first (newest)
   - DECISION-001 second (older)
3. Each decision should show:
   - ✅ ID (e.g., "001")
   - ✅ Status badge (e.g., "EXECUTED")
   - ✅ Status color (EXECUTED = green)
   - ✅ Title text
   - ✅ Date/time (human readable)
   - ✅ Impact (e.g., "HIGH")

**Pass Criteria**:
- ✅ Reverse chronological order correct
- ✅ All fields present and readable
- ✅ Status badges show correct colors
- ✅ No truncated or wrapped text (unless intended)
- ✅ Spacing is consistent between rows

---

### T4: Decision Detail Expansion ✅ CRITICAL
**Purpose**: Verify clicking decision shows details correctly

**Steps**:
1. Click on DECISION-001 in timeline
2. Verify a modal or expand section appears showing:
   - Full decision ID
   - Status
   - Issue summary
   - Proposed solution (first 200 chars)
   - Expected outcome (first 200 chars)
   - Test results (showing "PASS" or similar)
   - Commit hash (0ecba42)
   - Link to decision file
3. Click on a different decision (DECISION-002)
4. Verify details update correctly
5. Click close button (X) or click outside modal
6. Verify modal closes and timeline is visible again

**Pass Criteria**:
- ✅ Modal/expand appears on click
- ✅ Contains Issue section
- ✅ Contains Proposed Solution section
- ✅ Contains Expected Outcome section
- ✅ Shows test result (PASS)
- ✅ Shows commit hash
- ✅ Modal closes cleanly
- ✅ No errors in console during interaction

---

### T5: Filter/Search ✅ IMPORTANT
**Purpose**: Verify filter and search controls work correctly

#### T5a: Filter by Status
```
Steps:
1. Click "Filter by Status" dropdown
2. Select "EXECUTED"
3. Verify timeline shows only EXECUTED decisions (should be 2)
4. Select "PROPOSED"
5. Verify timeline shows only PROPOSED decisions (should be 0)
6. Click "Clear Filters"
7. Verify all decisions show again
```

**Pass Criteria**:
- ✅ Status filter works
- ✅ Correct number of decisions shown
- ✅ Clear filters restore all decisions

#### T5b: Filter by Impact
```
Steps:
1. Click "Filter by Impact" dropdown
2. Select "CRITICAL"
3. Verify only DECISION-001 shows (impact: CRITICAL)
4. Select "HIGH"
5. Verify only DECISION-002 shows (impact: HIGH)
6. Clear filters
```

**Pass Criteria**:
- ✅ Impact filter works
- ✅ Correct decisions filtered
- ✅ Clear filters work

#### T5c: Search by ID/Title
```
Steps:
1. Type "001" in search box
2. Verify only DECISION-001 shows
3. Clear search, type "documentation"
4. Verify only DECISION-002 shows (title contains "documentation")
5. Clear search, type "xyz"
6. Verify "No decisions found" message appears
```

**Pass Criteria**:
- ✅ Search by ID works
- ✅ Search by title works
- ✅ Case-insensitive search
- ✅ Empty result message shows
- ✅ Clear search works

---

### T6: Error Handling ✅ IMPORTANT
**Purpose**: Verify errors are handled gracefully

#### T6a: Network Error
```
Steps:
1. Open DevTools Network tab
2. Check "Offline" or throttle to "No connection"
3. Refresh Fridays page
4. Verify Time Wizard tile shows error message:
   "Unable to load timeline. Please check your connection."
5. Verify no console errors thrown
6. Go back online
7. Refresh page
8. Verify timeline loads correctly again
```

**Pass Criteria**:
- ✅ User-friendly error message shows
- ✅ No JavaScript exceptions
- ✅ Recovers when connection restored

#### T6b: Empty Decision List
```
This will be tested in future sessions when decisions are archived.
Expected behavior: Show "No decisions to display" message
```

#### T6c: Missing Fields in API Response
```
This is a code review check:
- Verify code handles missing "issue", "solution", etc.
- Verify code doesn't crash if decision missing fields
```

---

### T7: Responsive Design ✅ IMPORTANT
**Purpose**: Verify UI looks good on different screen sizes

**Desktop (1920x1080)**:
```
Steps:
1. Open Chrome DevTools
2. Set to responsive design mode (Ctrl+Shift+M)
3. Set to 1920x1080
4. Verify:
   - Tile spans full width nicely
   - All text readable
   - No horizontal scrolling needed
   - Timeline layout looks good
```

**Tablet (800x600)**:
```
Steps:
1. Set DevTools to 800x600
2. Verify:
   - Tile layout adapts
   - Text still readable
   - No important content hidden
   - Search/filter controls visible
```

**Mobile (375x667)**:
```
Steps:
1. Set DevTools to 375x667
2. Verify:
   - Layout stacks vertically if needed
   - Touch targets are large enough
   - Scrolling works
   - No tiny unreadable text
```

**Pass Criteria**:
- ✅ Readable on desktop
- ✅ Readable on tablet
- ✅ Readable on mobile
- ✅ No horizontal scrolling on any size
- ✅ Controls accessible on all sizes

---

### T8: Integration with Other Tiles ✅ IMPORTANT
**Purpose**: Verify Time Wizard tile doesn't break other functionality

**Steps**:
1. Verify all other tiles still load:
   - Chat tile
   - Terminal tile
   - Memory tile
   - Monitor tile
   - Studio tile
   - Proposals tile
   - Tickets tile
   - Docs tile
2. Click between tiles, verify switching works
3. Use Refresh button in header, verify all tiles refresh
4. Check console for any errors from other tiles

**Pass Criteria**:
- ✅ All 8 existing tiles render
- ✅ Tile switching works
- ✅ Refresh refreshes all tiles
- ✅ No errors in console

---

### T9: Data Accuracy ✅ CRITICAL
**Purpose**: Verify displayed data matches API responses

**Steps**:
1. In browser console, run:
```javascript
fetch('/api/timeline')
  .then(r => r.json())
  .then(data => console.log(JSON.stringify(data, null, 2)))
```
2. Compare API response with what's displayed in UI:
   - ✅ Same number of decisions
   - ✅ Same IDs (001, 002)
   - ✅ Same statuses (EXECUTED)
   - ✅ Same titles
   - ✅ Same dates (in same format)

3. Click decision to expand, verify details match:
```javascript
fetch('/api/decisions/001')
  .then(r => r.json())
  .then(data => console.log(JSON.stringify(data, null, 2)))
```
   - ✅ Issue text matches
   - ✅ Solution text matches
   - ✅ Commit hash matches

**Pass Criteria**:
- ✅ All displayed data matches API response
- ✅ No data corruption or truncation
- ✅ Detail modal shows correct info

---

### T10: Edge Cases ✅ MEDIUM
**Purpose**: Verify handling of unusual scenarios

#### T10a: Many Decisions (100+)
```
Setup: Add fake decisions to index
Steps:
1. Load page with 100 decisions
2. Verify page doesn't hang or crash
3. Check performance (should load in <2s)
4. Verify pagination or "Load More" works
```

**Pass Criteria**:
- ✅ Doesn't crash with many decisions
- ✅ Performance acceptable (<2s load)

#### T10b: Decision with Very Long Title
```
Setup: Create decision with 500-char title
Steps:
1. Verify title doesn't break layout
2. Verify text wraps or truncates appropriately
```

**Pass Criteria**:
- ✅ Layout doesn't break
- ✅ Title readable (not tiny or invisible)

#### T10c: Decision with Missing Fields
```
Code review check:
- Verify all fields have null checks
- Verify UI handles missing Issue, Solution, etc.
- Verify no "undefined" appears in UI
```

**Pass Criteria**:
- ✅ No undefined values in UI
- ✅ Graceful fallback for missing data

---

## Test Execution Plan

### Phase 1: Pre-Implementation (30 min)
**Run BEFORE any code is written**:
1. ✅ Verify preconditions (PC1-PC4) — 10 min
2. ✅ Review code design — 10 min
3. ✅ Prepare test environment — 10 min

### Phase 2: Implementation (30 min)
**Write the code**:
1. Add CSS for timeline styling
2. Add loadTimeWizard() function
3. Add expandDecision() function
4. Add tile HTML structure
5. Wire up event handlers

### Phase 3: Post-Implementation (20 min)
**Run tests T1-T10 in order**:
1. T1: Tile Rendering — 2 min
2. T2: API Integration — 3 min
3. T3: Timeline Display — 3 min
4. T4: Detail Expansion — 3 min
5. T5: Filter/Search — 4 min
6. T6: Error Handling — 2 min
7. T7: Responsive Design — 3 min
8. T8: Integration — 2 min
9. T9: Data Accuracy — 2 min
10. T10: Edge Cases — 2 min

### Phase 4: Refinement (10 min)
**Fix any issues found, re-test critical paths**

---

## Test Results (To Be Filled During Execution)

| Test | Status | Notes | Pass/Fail |
|------|--------|-------|-----------|
| PC1: API Endpoints | ⏳ | | |
| PC2: Service Running | ⏳ | | |
| PC3: File Accessible | ⏳ | | |
| PC4: No Current Errors | ⏳ | | |
| T1: Tile Rendering | ⏳ | | |
| T2: API Integration | ⏳ | | |
| T3: Timeline Display | ⏳ | | |
| T4: Detail Expansion | ⏳ | | |
| T5: Filter/Search | ⏳ | | |
| T6: Error Handling | ⏳ | | |
| T7: Responsive Design | ⏳ | | |
| T8: Integration | ⏳ | | |
| T9: Data Accuracy | ⏳ | | |
| T10: Edge Cases | ⏳ | | |

**Overall Result**: ⏳ TO BE EXECUTED

---

## Sign-Off

**Test Plan Created**: 2026-03-29T00:25:00Z  
**Status**: Ready for execution  
**Next Step**: Execute preconditions, then begin implementation
