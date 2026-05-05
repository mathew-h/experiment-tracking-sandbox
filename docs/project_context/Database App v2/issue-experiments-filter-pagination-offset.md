## Bug: Filtering on Experiments view returns empty or truncated results unless page size is extended

**Labels:** `bug` `frontend` `pagination`
**Component:** Experiments view — filter + pagination interaction

---

### Summary

Applying any filter on the Experiments view produces an empty list or a suspiciously short result set when the page size is left at the default (25). Expanding the page size to 50 or 100 causes the correct results to appear. The symptom is non-deterministic — sometimes the list is empty, sometimes it is just shorter than expected — suggesting the issue is tied to which page the user is currently on when the filter is applied.

---

### Steps to Reproduce

1. Navigate to the Experiments view.
2. Scroll to or navigate to page 2 or beyond (page size = 25, so offset ≥ 25).
3. Apply any filter (status, date, researcher, etc.).
4. Observe: results are empty or far fewer than expected.
5. Change page size to 50 or 100.
6. Observe: correct filtered results now appear.

---

### Expected Behavior

When a filter is applied, the pagination offset should reset to page 1 (offset = 0). The filtered result set should be fetched from the beginning, not from whatever offset was active before the filter was applied.

---

### Actual Behavior

The page index is **not reset** when a filter is applied. The API query is sent with the pre-existing offset (e.g., `skip=25`). If the filtered result set contains fewer rows than the current offset, the API correctly returns an empty or short slice — making it appear as if the filter is broken.

Example: user is on page 2 (offset = 25) and applies a status filter that matches only 18 experiments total. The request goes out as `skip=25&limit=25`, which returns 0 results.

---

### Root Cause Hypothesis

The filter state change does not trigger a page reset in the pagination controller. The fix is to reset the active page to 1 (offset to 0) any time a filter value changes, before the API call is fired.

Likely location: the filter `onChange` handler(s) in the Experiments table component, or wherever `skip`/`offset` is computed from the current page index.

---

### Acceptance Criteria

- [ ] Applying any filter on the Experiments view always resets the view to page 1.
- [ ] The page indicator reflects the reset (shows "Page 1 of N").
- [ ] Filtered results are correct and complete regardless of which page was active before filtering.
- [ ] Clearing a filter also resets to page 1.
- [ ] No regression on default unfiltered pagination behavior.

---

### Workaround

Set page size to 50 or 100 before applying filters. This reduces the likelihood that the current offset exceeds the filtered result count, but does not fully eliminate the bug.

---

### Environment

- **Frontend:** React 18 + TypeScript
- **Backend:** FastAPI + SQLAlchemy 2.x (pagination via `skip`/`limit` query params)
- **Default page size:** 25
