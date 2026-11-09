# Navigation audit, 2026-11-09 — Dashboard, Experiments, Detail, Group, HPHT run, Core Flood run

Read-only audit of the links between the six pages a researcher moves between
every day. Method: (1) a route/entity map from `frontend/src/App.tsx`, (2) a
link graph built from every `<Link>`, `navigate()` and row `onClick` under
`frontend/src/pages` and `frontend/src/components`, (3) a content-ownership
matrix, (4) five cognitive walkthroughs (novice researcher, first week, knows
the lab vocabulary, has not used the app) using the `cognitive-walkthrough`
skill, (5) the visual pass is **not done** — it waits on confirmation that the
backend and Vite are running. Every finding cites `file:line` as of develop
`91cc2e7` (branch `chore/navigation-audit`).

The deliverable is §4, a prioritized list of 22 concrete improvements
(`NAV-01` … `NAV-22`). §1–§3 are the evidence. §5 names the three shared
components that would close most of them together.

---

## 1. Route / entity map

Routes are declared in `frontend/src/App.tsx:39-57`. `/dashboard` is not a
route: it reaches the dashboard only through the catch-all redirect at
`App.tsx:57` (the e2e specs rely on this — see NAV-12).

| Route | Page | Entity the URL names | Breadcrumb / parent it claims | Source |
|---|---|---|---|---|
| `/` | `DashboardPage` | none (reactor slots, timeline, activity) | no breadcrumb | `App.tsx:39` |
| `/experiments` | `ExperimentListPage` | experiment rows; group rows when "Group replicates" is on | no breadcrumb | `App.tsx:40`, `ExperimentList.tsx:52` |
| `/experiments/new` | `NewExperimentPage` | wizard | — | `App.tsx:41` |
| `/experiments/groups/:baseId` | `ReplicateGroupPage` | **replicate group**, addressed by `base_experiment_id` string | `Experiments › Group {baseId}` | `App.tsx:42`, `ReplicateGroup/index.tsx:171-175` |
| `/experiments/:id` | `ExperimentDetailPage` | **one experiment row**: a serum vial, a lettered replicate, an HPHT/CF segment (`HPHT_297-2`) or a variant (`_Desorption`) | `Experiments › {id}` — always, whatever the row is | `App.tsx:43`, `ExperimentDetail/index.tsx:226-231` |
| `/hpht` | `HphtListPage` | HPHT runs (one row per base ID) | no breadcrumb | `App.tsx:44` |
| `/hpht/:baseId` | `HphtRunPage` | **run** = every experiment sharing `base_experiment_id` (`run_service.py:3-7`, `:56-57`) | `HPHT` (single crumb, the h1 is the base ID) | `App.tsx:45`, `HphtRunPage.tsx:118-121` |
| `/core-floods` | `CoreFloodListPage` | Core Flood runs | no breadcrumb | `App.tsx:46` |
| `/core-floods/:baseId` | `CoreFloodRunPage` | run (same definition) | `Core Floods` | `App.tsx:47`, `CoreFloodRunPage.tsx:82-85` |
| `*` | `<Navigate to="/" replace />` | — | silent redirect to Dashboard, no message | `App.tsx:57` |

### Where two routes disagree about hierarchy

1. **A segment has two parents and admits to neither.** The run page says a
   segment's parent is the run (`HphtRunPage.tsx:119`, `CoreFloodRunPage.tsx:83`)
   and links each segment to `/experiments/{id}` (`SegmentsTable.tsx:160-165`).
   That page's breadcrumb says the parent is the flat Experiments list
   (`ExperimentDetail/index.tsx:228`) and never mentions the run. The only
   way back to the run is the "Open run page" link inside the Results tab
   (`ResultsTab.tsx:256-271`), which is not the default tab
   (`ExperimentDetail/index.tsx:50`). → NAV-03, NAV-18.
2. **The detail page knows its reactor but not its run.** The header prints
   `Reactor R07` as text (`ExperimentDetail/index.tsx:393-394`) and the
   Conditions tab prints it again as text (`ConditionsTab.tsx:285`). Neither
   is a link to `/hpht/{base}` or to the dashboard slot. → NAV-03.
3. **Sequential segments are invisible to the replicate strip.** The strip at
   `ExperimentDetail/index.tsx:287-329` renders only when `inReplicateSet`
   (`:209-214`). Group membership is defined once, in
   `backend/services/replicate_groups.py:96-112` (`_member_clause`): a lettered
   replicate or a letterless `-t<days>` vial of the stem. `HPHT_297-2` is
   neither, so an HPHT or Core Flood segment shows no siblings and no group
   link, while a serum vial shows both. The run page is the only place the
   segment family is listed, and there it is collapsed (`HphtRunPage.tsx:72`,
   `CoreFloodRunPage.tsx:29`). → NAV-04, NAV-18.
4. **Run URLs accept only a base ID.** `GET /api/hpht/{base_id}` filters on
   `Experiment.base_experiment_id == base_id` (`run_service.py:56-57`) and maps a
   miss to 404 (`backend/api/routers/hpht.py:24-28`). `/hpht/HPHT_297-2`
   (a segment ID, the thing a researcher copies from the reactor card) is a
   dead end: "No HPHT run HPHT_297-2 · Back to HPHT" (`HphtRunPage.tsx:91-97`).
   Core Flood is the same (`CoreFloodRunPage.tsx:48-56`). → NAV-09.
5. **The group page and the run page are siblings that never meet.** Both are
   addressed by `base_experiment_id`, both sit under "Experiments" in the
   breadcrumb or sidebar, but a serum base ID goes to
   `/experiments/groups/{base}` (`ExperimentList.tsx:356-358`) and an HPHT base
   ID has no row link at all — the list never links to `/hpht/*` or
   `/core-floods/*` (no edge in §2). → NAV-07.

---

## 2. Link graph

Source → destination, with the condition under which the link exists. Edges
that are not routes (modal open, in-page expand) are listed where they gate a
route. Tests that pin an edge are in the last column.

### Global

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| G1 | Sidebar `NavLink` | `/`, `/experiments`, `/experiments/new`, `/bulk-uploads`, `/samples`, `/chemicals`, `/data-export`, `/hpht`, `/core-floods`, `/notes/review` (in that order) | always | `layouts/AppLayout.tsx:13-119`, `:159-161` | `AppLayout.nav.test.tsx:27-45` (asserts href order) |
| G2 | Sign out | `/login` | — | `AppLayout.tsx:138` | — |
| G3 | any unknown URL | `/` (replace) | — | `App.tsx:57` | e2e `04-update-status-dashboard.spec.ts:15`, `14-dashboard-cf-slots.spec.ts:30,89,109,129` (all `goto('/dashboard')`) |
| G4 | `ProtectedRoute` | `/login` | unauthenticated | `auth/ProtectedRoute.tsx:26` | — |
| G5 | Login success | `from` or `/` | — | `pages/Login.tsx:51` | — |

### Dashboard (`/`)

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| D1 | Reactor card click | opens `ReactorDetailModal` (not a route) | card occupied | `ReactorGrid.tsx:176`, `:617-630` | `ReactorGrid.test.tsx:305-309` |
| D2 | Modal "Open run page" (secondary style) | `/hpht/{base_experiment_id}` | `runPagePath(card) !== null`: label not `CF*`, status `ONGOING`, base present — **null for every Core Flood card and every QUEUED card** | `ReactorGrid.tsx:32-35`, `:533-540` | `ReactorGrid.test.tsx:291-303` (asserts null for CF and QUEUED) |
| D3 | Modal "View Detail →" (primary, `bg-brand-red`) | `/experiments/{experiment_id}` | always | `ReactorGrid.tsx:541-546` | — |
| D4 | Modal status badge dropdown | PATCH status (no navigation) | — | `ReactorGrid.tsx:47-61`, `:101-117` | e2e `04-update-status-dashboard.spec.ts:18-36` |
| D5 | Timeline row | `/experiments/{experiment_id}` | always | `ExperimentTimeline.tsx:36` | — |
| D6 | Activity feed ID button | `/experiments/{experiment_id}` | `entry.experiment_id` present | `ActivityFeed.tsx:51-60` | — |

The card payload carries `base_experiment_id` for every slot, Core Flood
included (`routers/dashboard.py:99`, `:155`); only the frontend
guard at `ReactorGrid.tsx:33` drops it.

### Experiment list (`/experiments`)

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| L1 | "New Experiment" button | `/experiments/new` | — | `ExperimentList.tsx:92` | — |
| L2 | Row click | `/experiments/groups/{displayId}` | `isGroupRow` (lettered group, or letterless multi-vial stem) | `ExperimentList.tsx:350-358`, `:375` | `ExperimentList.test.tsx:534-590` |
| L3 | Row click | `/experiments/{experiment_id}` | otherwise — **HPHT and CF rows always land on the segment, never the run** | `ExperimentList.tsx:356-358`, `:375` | `ExperimentList.test.tsx:560-575` |
| L4 | "n replicates: a, b, c" badge | expands child rows in place (not a route); children follow L3 | `hasReplicates` | `ExperimentList.tsx:237-256`, `:271-272` | — |
| L5 | Row status `<select>` | PATCH status | `!statusReadOnly` | `ExperimentList.tsx:339`, `:400-417` | — |

No edge from this page to `/hpht/*` or `/core-floods/*`.

### Experiment detail (`/experiments/:id`)

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| E1 | Breadcrumb "Experiments" | `/experiments` | always | `ExperimentDetail/index.tsx:228` | — |
| E2 | Rename saved | `/experiments/{newId}` (replace) | — | `ExperimentDetail/index.tsx:103` | — |
| E3 | "Group {base}" link | `/experiments/groups/{base}` | `inReplicateSet` (`:209-214`) — never for a sequential HPHT/CF segment | `ExperimentDetail/index.tsx:287-305` | `GroupStrip.test.tsx:91`, `:194` |
| E4 | Member chips | `/experiments/{member}` | lettered or `-t` members only | `ExperimentDetail/index.tsx:306-327` | `GroupStrip.test.tsx:94-96`, `:156` |
| E5 | "+ New Experiment" | `/experiments/new` | — | `ExperimentDetail/index.tsx:432` | — |
| E6 | Delete confirmed | `/experiments` (replace) | — | `ExperimentDetail/index.tsx:480` | `DeleteExperiment.test.tsx:92` |
| E7 | Results tab "Open run page" | `/core-floods/{base ?? id}` | `isCoreFloodType(conditions.experiment_type)` — **only on the Results tab; no conditions row → no link** | `ResultsTab.tsx:192`, `:254-261` | `ResultsTab.columns.test.tsx:269-284` |
| E8 | Results tab "Open run page" | `/hpht/{base ?? id}` | `isHphtType(...)`, same caveats | `ResultsTab.tsx:193`, `:264-272` | `ResultsTab.columns.test.tsx:286-299` |
| E9 | Grouped view drill-in chips | `/experiments/{vial}` | grouped mode | `GroupedResultsView.tsx:255-265` | `GroupedResultsView.test.tsx:136`, `:293` |
| E10 | "Reactor R07" | **none** — plain text | — | `ExperimentDetail/index.tsx:393-394`; `ConditionsTab.tsx:285` | — |
| E11 | "Experiment not found" | **none** — dead end, no link | load error | `ExperimentDetail/index.tsx:207` | — |
| E12 | Status badge | **none** — read-only `StatusBadge`; the page cannot change status | — | `ExperimentDetail/index.tsx:276` | e2e `04-update-status-dashboard.spec.ts:45-46` (asserts the badge text) |

### Replicate group (`/experiments/groups/:baseId`)

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| R1 | Breadcrumb "Experiments" | `/experiments` | — | `ReplicateGroup/index.tsx:172` | — |
| R2 | Member row ID | `/experiments/{member}` | — | `ReplicateGroup/index.tsx:126-130` | `ReplicateGroupPage.test.tsx:93-95`, `:356` |
| R3 | Rollup card drill-in chips | `/experiments/{vial}` | via `GroupedResultsView` | `ReplicateGroup/index.tsx:291` → `GroupedResultsView.tsx:255-265` | — |
| R4 | "Replicate group not found" | **none** — dead end | 404 | `ReplicateGroup/index.tsx:311-313` | — |

### HPHT list and run (`/hpht`, `/hpht/:baseId`)

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| H1 | List row "Run" cell | `/hpht/{base_id}` | — | `HphtListPage.tsx:114-119`, `hphtWrites.ts:25` | `HphtListPage.test.tsx:52` |
| H2 | Breadcrumb "HPHT" | `/hpht` | — | `HphtRunPage.tsx:119` | — |
| H3 | 404 "Back to HPHT" | `/hpht` | 404 only; the segment ID in the URL is not offered | `HphtRunPage.tsx:91-97` | `HphtRunPage.test.tsx:175-190` |
| H4 | Non-404 error | **none** | — | `HphtRunPage.tsx:99-101` | — |
| H5 | Conditions card "Edit on Conditions tab" | `/experiments/{latest non-variant segment}` | conditions present | `ConditionsSummaryCard.tsx:47-54` | `HphtRunPage.test.tsx:103-105` |
| H6 | Segments table ID | `/experiments/{segment}` | inside a `Collapsible` **closed by default** | `HphtRunPage.tsx:72`, `:172-187`; `SegmentsTable.tsx:160-165` | — |
| H7 | Rename that moves the only segment | `/hpht/{newBase}` (replace) | `segmentCount === 1` | `SegmentsTable.tsx:53-56`; `hphtWrites.ts:30` | — |
| H8 | Samples table "Segment" cell | **none** — plain text; row click opens the edit modal | — | `HphtSamplesTable.tsx:98`, `:121` | `HphtRunPage.test.tsx:154-165` |
| H9 | "Ongoing: HPHT_297-2" badge | **none** — text | — | `HphtRunPage.tsx:125` | `HphtRunPage.test.tsx:101` |
| H10 | "Reactor R07" | **none** — text | — | `HphtRunPage.tsx:124` | `HphtRunPage.test.tsx:100` |

### Core Flood list and run (`/core-floods`, `/core-floods/:baseId`)

| # | Source | Destination | Condition | Source line | Pinned by |
|---|---|---|---|---|---|
| C1 | List row "Run" cell | `/core-floods/{base_id}` | — | `CoreFloodListPage.tsx:107-113` | `CoreFloodListPage.test.tsx:58-59` |
| C2 | Breadcrumb "Core Floods" | `/core-floods` | — | `CoreFloodRunPage.tsx:83` | — |
| C3 | 404 "Back to Core Floods" | `/core-floods` | 404 only | `CoreFloodRunPage.tsx:48-56` | `CoreFloodRunPage.test.tsx:349-356` |
| C4 | Segments table ID | `/experiments/{segment}` | `Collapsible` closed by default | `CoreFloodRunPage.tsx:29`, `:126-140`; `SegmentsTable.tsx:160-165` | `CoreFloodRunPage.test.tsx:442-480` (rename flow) |
| C5 | Rename that moves the only segment | `/core-floods/{newBase}` | as H7 | `SegmentsTable.tsx:55`; `useCoreFloodWrites.ts:28` | `CoreFloodRunPage.test.tsx:451`, `:480` |
| C6 | Side-sample segment ID under the date | **none** — text | variant rows | `SamplesTable.tsx:103` | — |
| C7 | "Ongoing: CF_018-3" badge | **none** — text | — | `CoreFloodRunPage.tsx:89` | — |
| C8 | There is no conditions card on the CF run page, so no edge to a segment's Conditions tab at all | — | — | `CoreFloodRunPage.tsx:78-183` (no `ConditionsSummaryCard` import) | — |

### Other pages that land on the six (for completeness)

| Source | Destination | Source line |
|---|---|---|
| New Experiment wizard success | `/experiments/{id}` | `NewExperiment/index.tsx:218` |
| Sample detail overview experiment rows | `/experiments/{id}` | `SampleDetail/OverviewTab.tsx:169` |
| Notes review experiment link | `/experiments/{id}` | `NotesReview.tsx:252` |
| Bulk Uploads result panel | **none** — counts and message only, no experiment IDs | `BulkUploadRow.tsx:198-254` |

### Cycles, vanishing links and pages with no route to their parent

- **Cycle: run ↔ segment through the Results tab.** Run → "Edit on Conditions
  tab" (H5) → detail opens on Conditions (`ExperimentDetail/index.tsx:50`) → no run link on that
  tab → Results tab → "Open run page" (E8) → run. Every lap costs two extra
  clicks, and a user who edits conditions and wants back to the run has to
  know the link is on a different tab.
- **Cycle: dashboard → segment → run → segment.** D3 is the emphasized button,
  so the common path to a run is dashboard → detail (Conditions) → Results →
  run → Segments (closed) → open → segment. See walkthrough (a) and (c).
- **Conditional links that silently disappear:** D2 (null for CF rigs and
  QUEUED cards, `ReactorGrid.tsx:33`); E7/E8 (hidden unless the Results tab is
  open and `conditions.experiment_type` is set); E3 (never for a sequential
  segment); H6/C4 (behind a closed collapsible).
- **No route back to the logical parent:** every `/experiments/{segment}` page
  for an HPHT or CF segment (parent = run; only reachable via E7/E8); the
  `/hpht/{segmentId}` and `/core-floods/{segmentId}` 404 states (H3, C3 offer
  only the list); E11 and R4 (no link at all); G3 (a typo in any URL lands on
  the dashboard with no explanation).

---

## 3. Content overlap and write ownership

| Content | Shown on | Writes happen on | Sends the user elsewhere? |
|---|---|---|---|
| Conditions | Detail Conditions tab (`ConditionsTab.tsx:267-296`); HPHT run summary card, read-only by design (`ConditionsSummaryCard.tsx:23-24`, `:61-88`); Group page shared panel (`ReplicateGroup/index.tsx:249-285`); Dashboard modal partial (`ReactorGrid.tsx:355-451`) | Detail Conditions tab modal (`ConditionsTab.tsx:269`, `:348-398`) **owner**; CF run Cleanup "Set pore volume for all segments" also patches conditions (`CleanupPanel.tsx:19-84`, `:31`) | Yes: HPHT run → "Edit on Conditions tab" (H5). CF run shows no conditions at all (C8) |
| Results entry (add) | — | Detail Results tab "+ Add Results" → `ResultEntryModal` (`ResultsTab.tsx:273-275`, `:350-360`); HPHT run "+ Add sample" → `HphtSampleModal` → the same `ResultEntryModal` (`HphtRunPage.tsx:130-132`, `HphtSampleModal.tsx:103-115`); CF run "+ Add sample" → `CoreFloodSampleModal` (`CoreFloodRunPage.tsx:94-96`, `CoreFloodSampleModal.tsx:187-194`) | Yes: a CF segment's Results tab offers only "Open run page" with no explanation (`ResultsTab.tsx:254-261`) |
| Results entry (edit) | — | Detail expanded row "Edit", primary rows, not CF (`ResultsTab.tsx:82-88`, `:337`); run page row click (`HphtSamplesTable.tsx:98`; `SamplesTable.tsx:74`) | CF: yes, Edit is absent on the detail page with no hint (`ResultsTab.tsx:337`) |
| Samples table | Detail Results tab, one segment (`ResultsTab.tsx:292-343`); HPHT run, whole run (`HphtSamplesTable.tsx`); CF run, whole run (`SamplesTable.tsx`) — three tables, three column sets | n/a | — |
| Charts | ICP over time: detail (`ResultsTab.tsx:348`, `IcpSection.tsx:8-10`, always open), HPHT run (`HphtRunPage.tsx:166-170`, collapsed), CF run (`CoreFloodRunPage.tsx:120-124`, `defaultOpen`). Cumulative H₂ / rate: HPHT run only (`HphtRunPage.tsx:149-158`). Grouped mean ± sd: detail Results tab grouped mode (`ResultsTab.tsx:281-284`) and Group page Rollup (`ReplicateGroup/index.tsx:288-293`), same component | n/a | — |
| Notes | Detail Notes tab (`NotesTab.tsx`) | **Owner of retype/delete:** Notes tab (`NotesTab.tsx:88`, `:99-100`). Writers elsewhere: description on detail (`ExperimentDetail/index.tsx:334`) and in both run pages' Segments table (`SegmentsTable.tsx:103-130`); modification note from the Dashboard modal (`ReactorGrid.tsx:287-302`) and `ResultEntryModal` (`ResultEntryModal.tsx:246`, `:254`); result note from `ResultEntryModal` and `CoreFloodSampleModal` (`:149`, `:193`) | Correcting any note: yes, Notes tab only (comment at `ReactorGrid.tsx:285-286`) |
| Status change | Dashboard card badge (`ReactorGrid.tsx:47-61`); list row select (`ExperimentList.tsx:400-417`); run pages Segments table and warnings (`SegmentsTable.tsx:178-181`; `HphtRunPage.tsx:53-56`; `CleanupPanel.tsx:122-125`) | all four of those | **The detail page — the entity's own page — cannot change status** (`ExperimentDetail/index.tsx:276`) |
| Replicate members | Detail strip (`ExperimentDetail/index.tsx:287-329`); Group page table (`ReplicateGroup/index.tsx:194-246`); list expander (`ExperimentList.tsx:237-256`); grouped view chips (`GroupedResultsView.tsx:255-265`) | Create replicates, outlier, background: detail quick actions (`ExperimentDetail/index.tsx:436`, `:441-457`); H₂ background: group page only (`H2BackgroundRow.tsx`) | Group page is read-only by design (`ReplicateGroup/index.tsx:28-29`, `:189`) |
| Delete | — | Detail only (`ExperimentDetail/index.tsx:459-461`, `:468-495`); bulk sheet (`BulkUploads.tsx:418-433`) | Run pages: yes — Segments → ID → detail → Delete |
| Export all | Detail (`ExperimentDetail/index.tsx:458`); both run pages (`HphtRunPage.tsx:129`; `CoreFloodRunPage.tsx:93`) | same component | no |
| Rename | Detail (`ExperimentDetail/index.tsx:268-274`); both run pages (`SegmentsTable.tsx:34-100`) | same validation hook | no |

---

## 4. Walkthroughs

Persona for all five: a researcher in their first week, comfortable with
"reactor", "segment", "replicate", never used this app, desktop on the lab LAN.
Click counts exclude typing and scrolling. Stalls are the steps where the
four walkthrough questions scored ⚠️ or ❌; each stall maps to an improvement.

### (a) Check an ongoing HPHT reactor from the dashboard and add a new sample result

| Step | Click | Lands on | Q1 goal clear | Q2 control visible | Q3 label fits | Q4 feedback | Stall |
|---|---|---|---|---|---|---|---|
| 1 | Reactor card R08 (`ReactorGrid.tsx:176`) | `ReactorDetailModal` | ✅ | ✅ hover border | ✅ | ✅ | — |
| 2 | Footer: Close · **Open run page** (secondary) · **View Detail →** (primary red) (`ReactorGrid.tsx:526-547`) | — | ⚠️ "add a sample" is on neither button | ✅ | ❌ the emphasized button is the wrong one; the only red control in the body is "Save" on a *modification note* textarea (`:508-521`) | — | S-a1 (NAV-02), S-a2 (NAV-17) |
| 3 | "Open run page" | `/hpht/HPHT_312` | ✅ | ⚠️ secondary style | ✅ | ✅ | — |
| 4 | "+ Add sample" (`HphtRunPage.tsx:130-132`) | modal titled **"Add Results"** (`HphtSampleModal.tsx:52`) | ✅ | ✅ | ⚠️ title ≠ button | ✅ | S-a3 (NAV-15) |
| 5 | Fill, "Save Results" (`ResultEntryModal.tsx:346`) | run page refreshed (`ResultEntryModal.tsx:264-267`) | ✅ | ✅ | ✅ | ✅ toast + table | — |

**Count: 4 clicks + form.** If the user takes the emphasized button at step 2
instead: View Detail → Conditions tab (default, `ExperimentDetail/index.tsx:50`) → Results tab
(`ExperimentDetail/index.tsx:499-521`) → "+ Add Results" (`ResultsTab.tsx:273`) → Save =
**5 clicks**, with no run context (cumulative H₂, sibling segments) and no
way back to the run except the Results tab link. S-a4 (NAV-03, NAV-18).

### (b) Find H₂ yield for a serum vial replicate set and compare replicates

| Step | Click | Lands on | Q1 | Q2 | Q3 | Q4 | Stall |
|---|---|---|---|---|---|---|---|
| 1 | Sidebar "Experiments" (`AppLayout.tsx:28`) | `/experiments` | ✅ | ✅ | ✅ | ✅ | — |
| 2 | Type filter "Serum" (`ExperimentList.tsx:126-132`) or ID filter (`:135-139`) | filtered list; group rows show "3 replicates: a, b, c" | ✅ | ✅ | ⚠️ the badge is a button that *expands*; the row itself opens the *group page*; nothing says so (`:237-256` vs `:375`) | ✅ | S-b1 (NAV-16) |
| 3 | Row click | `/experiments/groups/SERUM_001` | ✅ | ✅ | ✅ | ✅ | — |
| 4 | Scroll: Members table (`ReplicateGroup/index.tsx:194-246`, a Results *count*, no H₂), Conditions card, then **Rollup** third (`:288-293`) | — | ⚠️ user expects the yield near the top | ❌ below the fold, no anchor, no tab | — | — | S-b2 (NAV-10) |
| 5 | Metric select defaults to H₂ (ppm) (`GroupedResultsView.tsx:63`); change to H₂ (g/t) (`:237-243`) | chart with mean ± sd and one line per letter (`:64`) | ⚠️ "H₂ yield" is the g/t column everywhere else (`HphtListPage.tsx:99`; `ResultsTab.tsx:302`) | ✅ | ✅ | ✅ | S-b3 (NAV-10) |

**Count: 4 clicks + scroll.** The rollup table under the chart already shows
g/t without the select (`GroupedResultsView.tsx:321`, `:345-347`). Alternative
path: expand badge → child row → detail → Results → "Grouped (n=3)"
(`ResultsTab.tsx:246-251`) = 5 clicks to the same component. A mistyped base
ID ends at "Replicate group not found" with no link (`ReplicateGroup/index.tsx:312`) — S-b4 (NAV-08).

### (c) Open a core flood from the dashboard and review its segments

| Step | Click | Lands on | Q1 | Q2 | Q3 | Q4 | Stall |
|---|---|---|---|---|---|---|---|
| 1 | CF01 card | modal | ✅ | ✅ | ✅ | ✅ | — |
| 2 | Footer has **no "Open run page"**: `runPagePath` returns null for `CF*` (`ReactorGrid.tsx:33`) although `/core-floods/CF_018` exists and the card carries `base_experiment_id` (`routers/dashboard.py:155`) | — | ✅ | ❌ the correct action is not offered | — | — | S-c1 (NAV-01) |
| 3 | "View Detail →" | `/experiments/CF_018-3`, Conditions tab; no strip (`-3` is not a member, `replicate_groups.py:96-112`), no run link | ⚠️ "where are the other segments?" | ❌ | — | — | S-c2 (NAV-03, NAV-18) |
| 4 | Results tab → "Open run page" (`ResultsTab.tsx:256-261`) | `/core-floods/CF_018` | ⚠️ nothing suggests segments live under Results | ⚠️ | ✅ | ✅ | S-c3 (NAV-19) |
| 5 | "Segments" collapsible, closed by default (`CoreFloodRunPage.tsx:29`, `:126-131`); summary lists IDs as text (`:128`) | `SegmentsTable` | ✅ | ⚠️ one more click, IDs visible but inert until opened | ✅ | ✅ | S-c4 (NAV-04, NAV-05) |

**Count: 5 clicks** (card, View Detail, Results, Open run page, Segments).
With NAV-01 and NAV-04: 2. Via the sidebar today: Core Floods → row → Segments = 3.

### (d) After an ICP bulk upload, verify the values landed on the right experiment

| Step | Click | Lands on | Q1 | Q2 | Q3 | Q4 | Stall |
|---|---|---|---|---|---|---|---|
| 1 | Sidebar "Bulk Uploads" | `/bulk-uploads` | ✅ | ✅ | ✅ | ✅ | — |
| 2 | Expand "ICP-OES Data" (`BulkUploads.tsx:250-261`) | drop zone | ✅ | ✅ | ✅ | ✅ | — |
| 3 | Drop the CSV (`BulkUploadRow.tsx:169-174`) | badges "Created / Updated / Skipped", warnings (`:198-254`), toast "Upload complete — n created, n updated" (`:111`) | ✅ | ✅ | ✅ | ❌ **no experiment IDs and no links** — the user cannot tell *which* experiments received rows unless a warning names one | S-d1 (NAV-20) |
| 4 | Sidebar "Experiments" | list | ✅ | ✅ | ✅ | ✅ | — |
| 5 | Type the ID from memory into "Experiment ID…" | filtered | ⚠️ depends on remembering the CSV label | ✅ | ✅ | ✅ | S-d1 |
| 6 | Row click | `/experiments/{id}` — **or** the group page if the ID is a `-t` vial of a multi-vial stem (`ExperimentList.tsx:350-358`), which shows no ICP at all; then member link → detail (+2) | ⚠️ | ⚠️ | ⚠️ | ✅ | S-d2 (NAV-19) |
| 7 | Results tab | rows with an "ICP" badge (`ResultsTab.tsx:326`) | ⚠️ page opened on Conditions | ✅ | ✅ | ✅ | S-d3 (NAV-19) |
| 8 | Expand the row (`:313`) | ICP-OES block (`:145-163`), or scroll to "ICP over time" (`:348`) | ✅ | ✅ | ✅ | ✅ | — |

**Count: 8 clicks minimum, 10 for a grouped `-t` vial.** The Dashboard's
Recent Activity does list `icp_results — {id}` with a link (`ActivityFeed.tsx:50-60`),
which is 4 clicks (Dashboard, link, Results, expand), but it holds only the
last 20 changes and nothing points the user to it.

### (e) Navigate from an HPHT segment to its sibling segments and back

Start: `/experiments/HPHT_297-2` (from D3, L3, D5 or D6).

| Step | Click | Lands on | Q1 | Q2 | Q3 | Q4 | Stall |
|---|---|---|---|---|---|---|---|
| 1 | Look for siblings: breadcrumb `Experiments › HPHT_297-2`, "Reactor R07" text, no strip (`ExperimentDetail/index.tsx:209-214`, `:393-394`) | — | ✅ | ❌ nothing on the page names the run or its segments | — | — | S-e1 (NAV-03, NAV-18) |
| 2 | Results tab | — | ⚠️ guess | ✅ | ⚠️ | ✅ | S-e2 (NAV-19) |
| 3 | "Open run page" (`ResultsTab.tsx:266-271`) | `/hpht/HPHT_297` | ✅ | ✅ | ✅ | ✅ | — |
| 4 | "Ongoing: HPHT_297-2" is text (`HphtRunPage.tsx:125`); Samples "Segment" column is text (`HphtSamplesTable.tsx:121`); open "Segments" (`HphtRunPage.tsx:172-177`) | `SegmentsTable` | ✅ | ⚠️ | ⚠️ IDs everywhere, links nowhere until the collapsible opens | ✅ | S-e3 (NAV-04, NAV-05) |
| 5 | Sibling "HPHT_297" (`SegmentsTable.tsx:160-165`) | `/experiments/HPHT_297`, Conditions tab | ✅ | ✅ | ✅ | ✅ | — |
| 6–9 | Back to `-2`: Results tab, Open run page, Segments, `HPHT_297-2` | — | — | — | — | — | S-e1 again |

**Count: 4 clicks one way, 8 for the round trip** (1 each way with a sibling
strip). Pasting the segment ID into the run URL, `/hpht/HPHT_297-2`, gives
"No HPHT run HPHT_297-2 · Back to HPHT" (`HphtRunPage.tsx:91-97`;
`run_service.py:56-57`; `routers/hpht.py:28`) — S-e4 (NAV-09).

---

## 5. Improvements

Sorted by value over effort: quick wins (S, no route change) first, then M,
then L. "Tests affected" lists the vitest files under `__tests__` (or
`*.test.tsx` beside the component) and the `e2e/journeys` specs whose
assertions touch the change. Risk is "none" unless a URL, the API, a locked
component or the lab PC is involved.

### Quick wins — S, no route change

**NAV-01 — Offer the run page from every reactor card, not only ONGOING HPHT**
- Found at: walkthrough (c) step 2; `ReactorGrid.tsx:32-35`
- Problem: `runPagePath` returns null for every Core Flood rig and every QUEUED card, so the modal hides the one link that leads to segments, cumulative H₂ and cleanup. The payload already has `base_experiment_id` for those cards (`routers/dashboard.py:99`, `:155`).
- Improvement: `runPagePath` returns `/core-floods/{base}` for `CF*` labels and `/hpht/{base}` for R/P labels whenever `base_experiment_id` is set, regardless of status. Keep null only when the base is missing.
- Files: `frontend/src/pages/ReactorGrid.tsx:32-35`, `:533-540`
- Effort: S
- Tests affected: `src/pages/__tests__/ReactorGrid.test.tsx:291-310` (the "gives no link for Core Flood rigs, QUEUED cards" case inverts); e2e `14-dashboard-cf-slots.spec.ts` (reads the card only, unaffected)
- Risk: none

**NAV-02 — Make "Open run page" the primary button in the reactor modal**
- Found at: walkthrough (a) step 2; `ReactorGrid.tsx:526-547`
- Problem: "View Detail →" carries `bg-brand-red` and sits last; "Open run page" is a bordered secondary button. A researcher checking a reactor wants the run (samples, charts, segments); the segment's Conditions tab is the less useful destination, and it has no way back to the run except the Results tab.
- Improvement: swap the emphasis: "Open run page" becomes the `variant="primary"` button (last in the footer), "View Detail →" becomes `variant="secondary"` and is relabelled "Open segment {experiment_id}". Use the shared `Button` component instead of the hand-styled `<button>`s so the variants follow `docs/frontend/DESIGN_SYSTEM.md` ("primary — the single primary action per screen").
- Files: `frontend/src/pages/ReactorGrid.tsx:526-547`
- Effort: S
- Tests affected: `src/pages/__tests__/ReactorGrid.test.tsx:305-309` (role/name query still passes; add a `variant` or class assertion); e2e `04-update-status-dashboard.spec.ts` (uses the badge only)
- Risk: none. Confirm in the visual pass (§6) before merging.

**NAV-03 — Breadcrumb states the real parent: run for a segment, group for a replicate**
- Found at: §1 disagreements 1–3; walkthrough (a) S-a4, (c) step 3, (e) step 1; `ExperimentDetail/index.tsx:226-231`
- Problem: every detail page claims `Experiments › {id}`. An HPHT or Core Flood segment has a run page and a serum replicate has a group page, and both are already known on this page (`experiment.base_experiment_id` at `:536`, `conditions.experiment_type` at `:534`, `replicateGroup` at `:74-78`). No extra fetch is needed.
- Improvement: unify to `Experiments › Run HPHT_297 › HPHT_297-2` (middle crumb → `/hpht/{base}`, or `/core-floods/{base}` by `isCoreFloodType`) and `Experiments › Group SERUM_001 › SERUM_001a` (middle crumb → `/experiments/groups/{base}`) using the existing `isHphtType` / `isCoreFloodType` helpers (`utils/experimentId.ts:32-40`). Also make the "Reactor R07" text at `:393-394` a link to the same run path. The Results-tab "Open run page" links (E7/E8) can stay for now; NAV-19 retires them.
- Files: `frontend/src/pages/ExperimentDetail/index.tsx:226-231`, `:393-394`
- Effort: S
- Tests affected: `src/pages/ExperimentDetail/__tests__/GroupStrip.test.tsx:91`, `:194` (group link href unchanged, breadcrumb text changes); `Tabs.test.tsx`; e2e `16-results-tab-columns.spec.ts:21-23` (navigates by URL, unaffected)
- Risk: none

**NAV-04 — Open the Segments section by default on both run pages**
- Found at: walkthrough (c) step 5, (e) step 4; `HphtRunPage.tsx:72`, `CoreFloodRunPage.tsx:29`
- Problem: the segment list, status selects and rename/describe controls sit in a `Collapsible` that starts closed; the summary line prints the IDs as plain text (`HphtRunPage.tsx:174`, `CoreFloodRunPage.tsx:128`), so the user sees the names and cannot click them.
- Improvement: `useState(true)` for `segmentsOpen` when `run.segments.length > 1`; keep closed for a single-segment run. The Cleanup/Data-checks `onRename` / `onEditDescription` handlers already force it open (`CoreFloodRunPage.tsx:148-155`), so nothing else changes.
- Files: `frontend/src/pages/Hpht/HphtRunPage.tsx:72`, `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx:29`
- Effort: S
- Tests affected: `src/pages/CoreFloods/__tests__/CoreFloodRunPage.test.tsx:442-480` (rename tests that click "Segments" to open it will now close it — switch them to asserting the table is present); `src/pages/Hpht/__tests__/HphtRunPage.test.tsx` (no Segments-open test today)
- Risk: none

**NAV-05 — Every segment ID printed on a run page is a link to that segment**
- Found at: walkthrough (e) step 4; H8, H9, C6, C7
- Problem: the Samples table "Segment" column (`HphtSamplesTable.tsx:121`), the side-sample ID under the date (`SamplesTable.tsx:103`), the "Ongoing: X" badge (`HphtRunPage.tsx:125`, `CoreFloodRunPage.tsx:89`) and the Segments summary line all show experiment IDs as text. The only clickable copy is inside the closed collapsible.
- Improvement: one `SegmentLink` component (`<Link to={/experiments/{id}}>` in `font-mono-data text-red-400`) used in all four places. In the sample tables wrap it with `onClick={(e) => e.stopPropagation()}` so the row's edit-on-click (`HphtSamplesTable.tsx:98`, `SamplesTable.tsx:74`) is not triggered.
- Files: `frontend/src/pages/Hpht/HphtSamplesTable.tsx:121`, `frontend/src/pages/CoreFloods/SamplesTable.tsx:103`, `frontend/src/pages/Hpht/HphtRunPage.tsx:125`, `:174`, `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx:89`, `:128`; new `frontend/src/components/runs/SegmentLink.tsx`
- Effort: S
- Tests affected: `src/pages/Hpht/__tests__/HphtRunPage.test.tsx:101` (`getByText('Ongoing: HPHT_297-2')` becomes a link query), `:108-118`; `src/pages/CoreFloods/__tests__/SamplesTable.test.tsx`, `CoreFloodRunPage.test.tsx`
- Risk: none

**NAV-06 — Let the detail page change status**
- Found at: §3 "Status change"; E12; `ExperimentDetail/index.tsx:276`
- Problem: status is editable on the dashboard card, the list row and the run page, but the experiment's own page shows a read-only `StatusBadge`. Completing a segment from its page means leaving it.
- Improvement: replace the badge with `SegmentStatusSelect` (`components/runs/SegmentStatusSelect.tsx`, already generic over `{ experiment_id, status }`), `onChanged` invalidating `['experiment', id]`, `['experiments']`, `['dashboard']` and the run keys from `hphtWrites.ts` / `useCoreFloodWrites.ts` by type. The 409 occupancy toast is already handled in that component (`:28`).
- Files: `frontend/src/pages/ExperimentDetail/index.tsx:276`
- Effort: S
- Tests affected: `src/pages/ExperimentDetail/__tests__/Tabs.test.tsx`; e2e `04-update-status-dashboard.spec.ts:45-46` (`getByText(/COMPLETED/i)` will also match the select's option text — tighten to the select's value)
- Risk: none (same `PATCH /status` the other four callers use)

**NAV-07 — Give HPHT and Core Flood rows on the Experiments list a link to their run**
- Found at: §1 disagreement 5; L3
- Problem: the list is the page researchers filter on, and its rows always open the segment. There is no path from `/experiments` to `/hpht/*` or `/core-floods/*`; the sidebar entries are the only way in.
- Improvement: in the Reactor cell (`ExperimentList.tsx:391-393`), when `isHphtType(exp.experiment_type)` or `isCoreFloodType(...)` and `exp.base_experiment_id` is set, render the slot as a `<Link>` to the run (with `stopPropagation`), titled "Open run {base}". `ExperimentListItem` already carries both fields (`H2BackgroundRow.tsx:24`, `:96`).
- Files: `frontend/src/pages/ExperimentList.tsx:391-393`
- Effort: S
- Tests affected: `src/pages/__tests__/ExperimentList.test.tsx:534-590` (row navigation unchanged; add a run-link case)
- Risk: none

**NAV-08 — Not-found states on the detail and group pages link back**
- Found at: walkthrough (b) S-b4; E11, R4
- Problem: "Experiment not found" (`ExperimentDetail/index.tsx:207`) and "Replicate group not found" (`ReplicateGroup/index.tsx:311-313`) render a sentence and nothing else. The run pages already do this right (`HphtRunPage.tsx:95`, `CoreFloodRunPage.tsx:52`).
- Improvement: add "Back to Experiments" (`/experiments`) to both; on the group page also "Search for {baseId}" → `/experiments?search={baseId}` once NAV-19's search-param pattern exists (plain link to `/experiments` until then).
- Files: `frontend/src/pages/ExperimentDetail/index.tsx:207`, `frontend/src/pages/ReplicateGroup/index.tsx:311-313`
- Effort: S
- Tests affected: `src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx` (if it asserts the not-found text, keep the text and add the link); `src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`
- Risk: none

**NAV-09 — A run URL that holds a segment ID offers that segment, not only the list**
- Found at: §1 disagreement 4; walkthrough (e) S-e4; `HphtRunPage.tsx:91-97`, `CoreFloodRunPage.tsx:48-56`
- Problem: `/hpht/HPHT_297-2` is the natural thing to type or bookmark from a reactor card, and it 404s with "Back to HPHT". The backend filters strictly on `base_experiment_id` (`run_service.py:56-57`).
- Improvement: in the 404 branch, add a second link "Open experiment {baseId}" → `/experiments/{baseId}`; that page (with NAV-03) carries the real run link, so the detour is one click. Optional follow-on, not part of this item: have `GET /api/hpht/{id}` resolve a segment ID to its run (API change).
- Files: `frontend/src/pages/Hpht/HphtRunPage.tsx:91-97`, `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx:48-56`
- Effort: S
- Tests affected: `src/pages/Hpht/__tests__/HphtRunPage.test.tsx:175-190`, `src/pages/CoreFloods/__tests__/CoreFloodRunPage.test.tsx:349-356`
- Risk: none (the follow-on would be a backend/API change)

**NAV-10 — Put the Rollup first on the group page and default the chart to H₂ (g/t)**
- Found at: walkthrough (b) steps 4–5; `ReplicateGroup/index.tsx:194-293`, `GroupedResultsView.tsx:63`
- Problem: the question a group page answers is "what did the set yield?", but the Rollup card is third, below a members table (which shows only a result count) and a conditions panel. The chart then opens on H₂ (ppm) while every list and table calls the headline number H₂ (g/t).
- Improvement: order the cards Rollup → Members → Conditions, and set `useState('h2_gpt')` as the default metric. The members table stays as the drill-in.
- Files: `frontend/src/pages/ReplicateGroup/index.tsx:193-293`, `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx:63`
- Effort: S
- Tests affected: `src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx`, `src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`, `ResultsTab.groupToggle.test.tsx` (any assertion on the default metric label)
- Risk: none

**NAV-11 — Move HPHT and Core Floods next to Experiments in the sidebar**
- Found at: G1; `AppLayout.tsx:13-119`
- Problem: the two run lists sit below Data Export, between a utility page and Notes review. A user who thinks "experiments" scans the top of the nav and finds only the flat list.
- Improvement: order Dashboard, Experiments, HPHT, Core Floods, New Experiment, Bulk Uploads, Samples, Chemicals, Data Export, Notes review.
- Files: `frontend/src/layouts/AppLayout.tsx:13-119`
- Effort: S
- Tests affected: `src/layouts/__tests__/AppLayout.nav.test.tsx:27-45` (asserts `navHrefs` order)
- Risk: none

**NAV-12 — Replace the silent catch-all redirect with a not-found page (keep `/dashboard`)**
- Found at: G3; `App.tsx:57`
- Problem: any mistyped or stale URL (`/experiment/HPHT_297`, `/hpht/`, an old bookmark) lands on the Dashboard with no message, so the user does not learn the link was wrong.
- Improvement: `*` renders a small not-found page with links to Experiments, HPHT, Core Floods and the Dashboard. Add an explicit `<Route path="/dashboard" element={<Navigate to="/" replace />} />` because the e2e specs and, likely, bookmarks use it.
- Files: `frontend/src/App.tsx:57`; new `frontend/src/pages/NotFound.tsx`
- Effort: S
- Tests affected: e2e `04-update-status-dashboard.spec.ts:15`, `14-dashboard-cf-slots.spec.ts:30`, `:89`, `:109`, `:129` (all `goto('/dashboard')`, kept working by the explicit redirect)
- Risk: route change — the `/dashboard` redirect above preserves bookmarked URLs; no other URL changes

**NAV-13 — Say why a Core Flood segment's Results tab cannot add or edit**
- Found at: §3 "Results entry"; `ResultsTab.tsx:254-261`, `:337`
- Problem: for a Core Flood segment the tab shows only "Open run page"; "+ Add Results" and the row "Edit" are absent with no explanation, so the user assumes the data is locked.
- Improvement: label the link "Add or edit samples on the run page" and add a one-line `text-ink-muted` note above the table ("Core flood samples record flow and permeability, which only the run page captures").
- Files: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx:254-261`
- Effort: S
- Tests affected: `src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx:269-284` (link name)
- Risk: none

**NAV-14 — One default for the ICP-over-time section across the three pages**
- Found at: §3 "Charts"
- Problem: the same `IcpChart` is always open on the detail Results tab (`ResultsTab.tsx:348`), collapsed on the HPHT run (`HphtRunPage.tsx:166-170`) and `defaultOpen` on the Core Flood run (`CoreFloodRunPage.tsx:120-124`). A user who saw it on one page looks for it in the wrong state on the next.
- Improvement: pick one (recommend collapsed with the sample count in the summary, as HPHT does) and apply it to all three; the detail page section becomes a `Collapsible` too.
- Files: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx:348`, `frontend/src/pages/ExperimentDetail/IcpSection.tsx`, `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx:121`
- Effort: S
- Tests affected: `src/pages/ExperimentDetail/__tests__/IcpSection.test.tsx`, `src/pages/CoreFloods/__tests__/CoreFloodRunPage.test.tsx`
- Risk: none

**NAV-15 — Match the sample modal's title to the button that opened it**
- Found at: walkthrough (a) step 4
- Problem: "+ Add sample" (`HphtRunPage.tsx:131`) opens a dialog titled "Add Results" (`HphtSampleModal.tsx:52`) whose primary button says "Save Results" (`ResultEntryModal.tsx:346`); the Core Flood modal says "Add sample" throughout (`CoreFloodSampleModal.tsx:269`, `:276`).
- Improvement: pass a `title` / `submitLabel` through `ResultEntryModal`'s props so the HPHT run page shows "Add sample" and "Save sample" while the Results tab keeps "Add Results".
- Files: `frontend/src/pages/Hpht/HphtSampleModal.tsx:52`, `frontend/src/pages/ExperimentDetail/ResultEntryModal.tsx:329-331`, `:346`
- Effort: S
- Tests affected: `src/pages/Hpht/__tests__/HphtRunPage.test.tsx:132-152`, `src/pages/ExperimentDetail/__tests__/ResultEntryModal.test.tsx`
- Risk: none

**NAV-16 — Tell the user that a group row opens the group page**
- Found at: walkthrough (b) step 2; `ExperimentList.tsx:237-256`, `:375`
- Problem: a group row has two click targets with different outcomes: the "3 replicates: a, b, c" badge expands in place, the rest of the row opens `/experiments/groups/…`. Nothing distinguishes them from a plain row that opens a detail page.
- Improvement: on group rows, render the ID as a link to the group page with a `title="Open group page"` and a small `Badge` "group" after it, and give the expander button a `title="Show replicates here"`.
- Files: `frontend/src/pages/ExperimentList.tsx:377-384`
- Effort: S
- Tests affected: `src/pages/__tests__/ExperimentList.test.tsx:534-590`
- Risk: none

**NAV-17 — Keep the reactor modal's only red control from reading as "enter a reading" (confirm in visual pass)**
- Found at: walkthrough (a) step 2; `ReactorGrid.tsx:480-523`
- Problem: the body of the modal ends with a date, a textarea placeholder "Enter a reactor modification…" and a `bg-brand-red` "Save" (`:515-521`). A novice checking a reactor to log a sample reads this as the entry form; it writes a *modification note*.
- Improvement: head the section "Log a reactor modification note", make its Save `variant="secondary"`, and move the navigation footer directly under the Experiment section so the next step is above the note form. Pair with NAV-02.
- Files: `frontend/src/pages/ReactorGrid.tsx:480-523`, `:526-547`
- Effort: S
- Tests affected: `src/pages/__tests__/ReactorGrid.test.tsx` (modification-note tests query by placeholder; unchanged)
- Risk: none. Logged from code; verify emphasis with a screenshot in §6 before changing.

### M

**NAV-18 — One `RunContextHeader` on the detail page: the run and its sibling segments**
- Found at: §1 disagreement 3; walkthroughs (a) S-a4, (c) step 3, (e) steps 1 and 6–9
- Problem: a serum vial's page shows "Replicate a · Group SERUM_001 · a [b] c" (`ExperimentDetail/index.tsx:287-329`); an HPHT or CF segment's page shows nothing about its run because `_member_clause` (`replicate_groups.py:96-112`) excludes sequential segments. Round-tripping between `HPHT_297` and `HPHT_297-2` costs eight clicks.
- Improvement: when `isHphtType` / `isCoreFloodType`, fetch the run (`hphtApi.get(base)` / `coreFloodsApi.get(base)`, both existing) and render the same strip shape: "Run HPHT_297 · HPHT_297 [HPHT_297-2] HPHT_297_Desorption", current segment bold, others links, "Ongoing" badge on the ongoing one. NAV-03's breadcrumb carries the run link; this adds the siblings. Extract the serum strip and this one into `components/experiments/RunContextHeader.tsx` so both read from one component.
- Files: `frontend/src/pages/ExperimentDetail/index.tsx:287-329`; new `frontend/src/components/experiments/RunContextHeader.tsx`
- Effort: M
- Tests affected: `src/pages/ExperimentDetail/__tests__/GroupStrip.test.tsx` (whole file: the strip moves into a component), `Tabs.test.tsx`
- Risk: none (reads existing `GET /api/hpht/{base}` and `GET /api/core-floods/{base}`)

**NAV-19 — Deep-link the detail page's tabs with `?tab=`**
- Found at: walkthrough (c) step 4, (d) steps 6–7, (e) step 2; the run ↔ segment cycle in §2
- Problem: `activeTab` is local state defaulting to Conditions (`ExperimentDetail/index.tsx:50`). Every inbound link lands there: "Edit on Conditions tab" happens to be right, but the ICP verification, the activity feed's `icp_results` link, the group page's result counts and the Results-tab-only run link all need Results.
- Improvement: read and write the tab through `useSearchParams` (`?tab=results|conditions|notes|xrd|logs`), keep Conditions as the default. Then: `ActivityFeed.tsx:55` links `icp_results` / `scalar_results` rows with `?tab=results`; `ReplicateGroup/index.tsx:139` makes the Results count a link to `?tab=results`; `ConditionsSummaryCard.tsx:49` appends `?tab=conditions`; the Results-tab "Open run page" links (E7/E8) can be retired once NAV-03 is in. No path changes, so no redirects.
- Files: `frontend/src/pages/ExperimentDetail/index.tsx:50`, `:497-522`; `frontend/src/pages/ActivityFeed.tsx:55`; `frontend/src/pages/ReplicateGroup/index.tsx:139`; `frontend/src/pages/Hpht/ConditionsSummaryCard.tsx:49`
- Effort: M
- Tests affected: `src/pages/ExperimentDetail/__tests__/Tabs.test.tsx`, `ResultsTab.columns.test.tsx:269-306` (if E7/E8 are retired), `src/pages/Hpht/__tests__/HphtRunPage.test.tsx:103-105` (href gains the query); e2e `16-results-tab-columns.spec.ts:21-23` and `15-wt-pct-fluid-additive.spec.ts:25` (still click the tab; unaffected)
- Risk: none (search param only; existing URLs keep working)

**NAV-20 — The ICP upload result names the experiments it wrote to, with links**
- Found at: walkthrough (d) step 3; `BulkUploadRow.tsx:198-254`
- Problem: after a drop the user sees "Created: 12 · Updated: 3" and must reconstruct from the CSV which experiments and timepoints were touched, then find each one by hand (8–10 clicks per check).
- Improvement: have the response carry `touched: [{experiment_id, time_post_reaction_days}]` and render them under the badges as links to `/experiments/{id}?tab=results` (NAV-19). The list is the verification step; one click per experiment.
- Files: `frontend/src/pages/BulkUploadRow.tsx:198-254`, `frontend/src/api/bulkUploads.ts` (`BulkUploadResult`); backend `backend/api/routers/bulk_uploads.py` (ICP endpoint response), `backend/api/schemas/` for the response model
- Effort: M
- Tests affected: `src/pages/__tests__/BulkUploads.test.tsx`, `BulkUploadRow.delegation.test.tsx`; pytest `tests/api/` for the ICP endpoint; e2e `03-upload-icp.spec.ts`
- Risk: backend/API need (additive response field). The IDs come from the rows `icp_service.py` already returns to the router; if collecting them needs a change inside `backend/services/icp_service.py` or `bulk_uploads/`, that is a locked parser — **Needs sign-off** for that part only.

**NAV-21 — Delete a segment from the run page's Segments table**
- Found at: §3 "Delete"
- Problem: a run page that can rename, re-describe and re-status a segment sends the user to the segment's detail page (three clicks, via a closed collapsible) to delete a mistaken one.
- Improvement: add a `variant="ghost"` "Delete" per row in `SegmentsTable` that opens the existing `DeleteExperimentModal` (`components/experiments/DeleteExperimentModal.tsx`, typed-ID gate included); on `onDeleted` call `writes.invalidate` and, if it was the only segment, `navigate(writes.runPath(...))` is wrong — go to the list route instead (`/hpht` or `/core-floods`, add `listPath` to `RunWrites`).
- Files: `frontend/src/pages/CoreFloods/SegmentsTable.tsx:146-199`, `frontend/src/components/runs/runWrites.ts`, `frontend/src/pages/Hpht/hphtWrites.ts`, `frontend/src/pages/CoreFloods/useCoreFloodWrites.ts`
- Effort: M
- Tests affected: `src/pages/CoreFloods/__tests__/CoreFloodRunPage.test.tsx`, `src/pages/Hpht/__tests__/HphtRunPage.test.tsx`, `src/components/experiments/DeleteExperimentModal.test.tsx`
- Risk: none to routes or API (same `DELETE /api/experiments/{id}`); it is a hard delete, so keep the typed-ID gate. Lowest priority of the M items.

### L

**NAV-22 — One samples table for the Results tab and both run pages**
- Found at: §3 "Samples table"
- Problem: the same result rows render through three tables with three column sets: `ResultsTab.tsx:292-343` (per segment, Fe²⁺ %, badges, expand-to-edit), `HphtSamplesTable.tsx` (per run, cumulative columns, click-to-edit, ICP expander) and `SamplesTable.tsx` (per run, flow/permeability). A user learns one and mis-reads the next; every column fix lands three times.
- Improvement: a `RunSamplesTable` keyed by a column spec (`components/results/sampleFields.ts` already defines the shared field definitions) with a `scope: 'segment' | 'run'` prop; the Results tab renders it in segment scope. Keep Core Flood's extra column group as a spec extension.
- Files: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`, `frontend/src/pages/Hpht/HphtSamplesTable.tsx`, `frontend/src/pages/CoreFloods/SamplesTable.tsx`, `frontend/src/components/results/sampleFields.ts`
- Effort: L
- Tests affected: `ResultsTab.columns.test.tsx`, `HphtRunPage.test.tsx:108-130`, `SamplesTable.test.tsx`, `CoreFloodRunPage.test.tsx`; e2e `16-results-tab-columns.spec.ts`
- Risk: none to routes or API

---

## 6. Patterns — shared components that close several items at once

1. **`RunContextHeader` (NAV-03, NAV-18, NAV-06, NAV-09's follow-on).** Every
   stall on the detail page comes from one cause: the page is built for a
   serum vial and treats an HPHT/CF segment as the same thing. One header
   component that takes the experiment plus its conditions type and renders
   breadcrumb, status control, run/group link and sibling chips fixes
   walkthroughs (a), (c) and (e) together, and gives the dashboard's "View
   Detail" a page worth landing on.
2. **One `runPathFor(experimentType, baseId)` helper (NAV-01, NAV-03, NAV-07,
   NAV-09).** The run route is spelled four times today: `ReactorGrid.tsx:34`,
   `ResultsTab.tsx:257` and `:267`, `hphtWrites.ts:25`, `useCoreFloodWrites.ts:28`.
   Three of the four new links in this list need the same decision ("HPHT or
   CF, which list, which path"). Put it beside `isHphtType` / `isCoreFloodType`
   in `utils/experimentId.ts` and have all callers use it; a future rename of
   either route then changes one line plus the redirect.
3. **`SegmentLink` + `?tab=` (NAV-05, NAV-16, NAV-19, NAV-20).** Experiment IDs
   are printed in `font-mono-data text-red-400` in eleven places and are links
   in six of them. A single component that always links, with an optional
   `tab` prop, makes "an ID is clickable" a rule the user can rely on and gives
   uploads, activity feed and group tables a one-click path to the right tab.

---

## 7. Verification of this audit

- Every edge in §2 and every `Found at` in §5 was read in this session from
  the file and line cited; nothing is inferred from names. "not found" is
  written where no control exists.
- The `-2` segment membership claim (§1 item 3, NAV-18) is taken from the
  `_member_clause` docstring and implementation at
  `backend/services/replicate_groups.py:96-112`, which admits only lettered
  replicates and letterless `-t` vials of the stem.
- No two items propose the same change: NAV-03 (breadcrumb, data already on
  the page) and NAV-18 (sibling strip, needs the run fetch) are split on that
  line; NAV-09 (frontend link) excludes the backend resolver it mentions.
- **Not done:** §5 of the brief, the visual pass. It needs the backend on
  :8000 and Vite on :5173 and I did not start either. The Playwright MCP named
  in the brief is not available in this session; the Chrome DevTools MCP is,
  and can drive the same login flow as `frontend/e2e/fixtures/auth.ts:34-44`
  (credentials from `frontend/e2e/.env.e2e`). NAV-02 and NAV-17 are the two
  items whose wording should be confirmed against a screenshot before they
  are implemented.
- No code, test or config file was changed. This file is the only addition;
  the docs hook copies it to `docs/project_context/`.
