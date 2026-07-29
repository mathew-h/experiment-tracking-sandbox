# Raise text contrast: shift the ink ramp up one step

**Labels:** `frontend`, `design-system`, `accessibility`
**Depends on:** nothing
**Blocks:** nothing

## Problem

Body and label text across the app is hard to read against the navy surfaces. The cause is a single design token, not per-component styling.

Measured contrast against `surface.raised` (`#0a2440`), which is what most panels and table rows use:

| Token | Hex | Contrast | WCAG AA (4.5:1) |
|---|---|---|---|
| `ink.primary` | `#F0F4F8` | 14.19:1 | pass |
| `ink.secondary` | `#8BACC8` | 6.60:1 | pass |
| `ink.muted` | `#4d6e8a` | **2.92:1** | **fail** |

`Th` is the worst case in practice: 10px uppercase text on `surface.overlay` (`#0e3158`), where `ink.muted` measures **2.45:1**.

Every dim label in the app uses `ink.muted`: condition field labels, table `Th` headers, breadcrumbs, empty states, chart axis ticks. On the replicate group page this is why `SERUM_DEMO_901` (which uses `ink.primary`) reads cleanly while every surrounding label blends into the background.

## Change

Shift the three-tier ramp up one step. `ink.muted` inherits today's `ink.secondary` value, and `ink.secondary` gets a new, brighter blue-white. Hierarchy is preserved (three distinct tiers), and all three tiers clear AA.

| Token | Before | After | On `base` | On `raised` | On `overlay` |
|---|---|---|---|---|---|
| `ink.primary` | `#F0F4F8` | `#F0F4F8` (unchanged) | 16.33:1 | 14.19:1 | 11.88:1 |
| `ink.secondary` | `#8BACC8` | `#C5D9EA` | 12.45:1 | 10.82:1 | 9.06:1 |
| `ink.muted` | `#4d6e8a` | `#A3C2DC` | 9.72:1 | 8.44:1 | 7.07:1 |

Every tier clears AA on all three surfaces, including `Th` on `surface.overlay`.

**Shipped update:** `ink.muted` landed at `#A3C2DC` rather than the `#8BACC8` proposed above — at the AA floor (5.52:1 on `overlay`), the `Th`/hint-text tier still read as hard to read in situ, so it was pushed to AAA-level contrast (7.07:1+) instead.

## Files

The three token definitions must change together or they drift:

1. `frontend/src/styles/tokens.css`: `--color-ink-secondary`, `--color-ink-muted`
2. `frontend/tailwind.config.ts`: `theme.extend.colors.ink.secondary`, `.muted`
3. `frontend/src/assets/brand.ts`: `colors.inkSecondary`, `colors.inkMuted`

`tokens.css` carries a "keep in sync with brand.ts" comment already. No component files need to change.

## Knock-on effects (verify visually, do not "fix")

These inherit the new values automatically and are the intended outcome:

- `chartColors.axis` = `inkMuted` and `chartColors.label` = `inkSecondary`, so all Recharts axis lines, ticks, and legend text brighten. Confirm the rollup chart in `GroupedResultsView` still reads as chart chrome rather than competing with the data series.
- `::-webkit-scrollbar-thumb:hover` uses `--color-ink-muted`.

These use `ink-muted` as a deliberately recessive *affordance* rather than as text, and will become more prominent. Check each still reads as secondary; if any now competes with real data, drop it to `opacity` or `surface-border` rather than reverting the token:

- Outlier replicate links in `GroupedResultsView`: `text-ink-muted line-through`
- The `n = {n_replicates}` cell in the rollup table
- The expand chevron (`▲`/`▼`) in `ResultsTab`
- `Th` in `components/ui/Table.tsx` (uppercase `text-2xs`, so it was the worst offender at 2.9:1)
- `Card.tsx` stat sub-labels and units

## Acceptance criteria

- [ ] All three token definition sites updated to the same values
- [ ] `ink.muted`, `ink.secondary`, `ink.primary` each clear 4.5:1 against `surface.base` (`#05172B`), `surface.raised` (`#0a2440`), and `surface.overlay` (`#0e3158`)
- [ ] Replicate group page condition labels are legible without leaning in
- [ ] Rollup chart axis and legend text still read as chrome, not data
- [ ] No component-level color classes changed as part of this issue

## Tests

Add a regression guard so this cannot silently drift back. New vitest file, e.g. `frontend/src/test/contrast.test.ts`:

- Import the token values from `assets/brand.ts` (the TS source of truth)
- Compute WCAG relative luminance and contrast ratio
- Assert `>= 4.5` for `inkPrimary`, `inkSecondary`, `inkMuted` against `navyBase`, `navyRaised`, and `navyOverlay`
- Assert the three ramp tiers are strictly ordered by luminance, so a future edit cannot invert the hierarchy

This test also catches the "someone edited tailwind.config.ts but not brand.ts" failure mode if you additionally parse the config, though asserting on `brand.ts` alone is the minimum.

## Docs

- [ ] `docs/DESIGN.md`: update the text hierarchy table with the new hex values and note the AA floor

## Out of scope

- Changing surface colors, red accent, or status colors
- Font sizes and weights
- Any per-component color reassignment
