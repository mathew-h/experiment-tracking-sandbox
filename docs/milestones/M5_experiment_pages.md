# Milestone 5: Experiment Management Pages

**Owner:** frontend-builder (primary), api-developer
**Branch:** `feature/m5-experiment-pages`

**Pages to build:**

**Experiment List (`/experiments`):** Filterable table (status, type, sample ID, date range, reactor number). Server-side pagination. Row click → detail.

**New Experiment (`/experiments/new`):** Multi-step form:
- Step 1: Basic info. Step 2: Conditions (show live `water_to_rock_ratio` preview). Step 3: Chemical additives (searchable, multiple). Step 4: Review + submit.
- Real-time experiment ID uniqueness check.

**Experiment Detail (`/experiments/:id`):** Tabs: Conditions (read-only with derived fields shown, edit modal), Results (timepoints with scalar + ICP expandable rows including yield fields), Notes (chronological feed + add note), Analysis (linked XRD/pXRF/elemental), Files.

**Acceptance criteria:** Creation round-trips with derived fields populated; all filters work; derived fields display from stored DB values; lineage visible; Chrome DevTools loop confirms no errors.

**Test Writer Agent:** Form validation, API integration, filter logic, lineage display tests.
**Documentation Agent:** User-facing guide for creating and managing experiments.
