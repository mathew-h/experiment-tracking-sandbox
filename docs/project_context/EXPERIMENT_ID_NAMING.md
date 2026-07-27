# Experiment ID Naming Guide

How to name an experiment so the system files it correctly — groups replicates,
links re-runs to their parent, and tags treatment variants. Get the ID right and
all of this happens automatically; get it wrong and the experiment is filed as an
unrelated standalone.

---

## The base ID

Every experiment ID starts with one of two patterns:

| Pattern | Example | When to use |
|---|---|---|
| `Type_Index` | `HPHT_001` | Default — no researcher initials needed |
| `Type_Initials_Index` | `Serum_MH_101` | When you want initials in the ID itself |

**Type** must be one of (case-insensitive): `Serum`, `Autoclave` (or `AC`), `HPHT`,
`CF` / `Coreflood` / `Core Flood`, `Other`. Anything else is flagged as an unknown
type.

**Index** is your sequence number for that type (`001`, `101`, whatever numbering
convention your group uses). It's just a label to the system — pick something
unique and consistent.

That's it for a normal, first-time experiment. Everything below is *optional*
suffixes you add on top of the base ID for specific situations.

---

## Adding a suffix

Suffixes are appended in this order — skip any you don't need:

```
Type_Index  [letter]  [-N]  [_Treatment]  [-t<days>]
```

### 1. Replicate letter — sister vials run side by side

Append a single lowercase letter directly to the index: `SERUM_001a`, `SERUM_001b`,
`SERUM_001c`. These are separate vials of the identical setup, reported together as
mean ± std.

- The bare ID (`SERUM_001`, no letter) is "replicate 0" — the group parent.
- Full workflow, grouped results, and the outlier-flagging feature are documented in
  `docs/user_guide/REPLICATES.md`.

### 2. `-N` — a sequential re-run

Append a hyphen and a number to re-run the *same* experiment: `HPHT_001-2` is the
second run of `HPHT_001`. Use this when you're redoing the whole experiment (not
just one replicate vial) — e.g. the first run failed, or you want another full
trial for comparison.

- Re-running one specific replicate vial: put the number after its letter, e.g.
  `SERUM_001a-2` for the second run of vial `a`. This links to `SERUM_001a` as its
  parent, not to the group as a whole.
- **Avoid `-0` and `-1` for a genuine re-run.** Those two numbers are reserved as
  alternate spellings of the group parent itself (equivalent to the bare ID) — they
  will *not* be treated as separate experiments. Start real re-runs at `-2`.
- This only works when the part before the hyphen already ends in your index number.
  A type abbreviation like `CF` on its own doesn't count, so `CF-015` is read as a
  standalone experiment named "015", **not** a re-run of `CF`. If your coreflood
  numbering relies on distinguishing re-runs, spell the index out first, e.g.
  `CF_015` then `CF_015-2`.

### 3. `_Treatment` — a named variant, same base setup

Append an underscore and a short label to mark a post-hoc treatment or condition
variant: `HPHT_001_Desorption`, `HPHT_001-2_Desorption`. This links back to the base
(or the specific re-run, if combined with `-N`) as its parent.

- Keep the label text-only — not purely numeric, and not a single letter (those
  patterns are reserved for index/replicate parsing, so `HPHT_001_a` would be
  misread rather than treated as a treatment named "a").

### 4. `-t<days>` — a destructively-sampled timepoint

Append `-t` and a day count when each timepoint is its own vial that gets sacrificed
to sample it (rather than the same vial sampled repeatedly over time): `SERUM_001a-t7`
(day 7), `SERUM_001a-t0.5` (half a day). Decimals are allowed.

- Always goes last, after any letter/`-N`/`_Treatment`.
- The day you type here becomes locked as that vial's result time — see the full
  rules (and bulk-upload behavior) in the "Replicate timepoints" section of
  `docs/user_guide/REPLICATES.md`.

---

## Worked examples

| ID | Reads as |
|---|---|
| `HPHT_001` | Base experiment, type HPHT, index 001 |
| `Serum_MH_101` | Base experiment, type Serum, initials MH, index 101 |
| `HPHT_001-2` | 2nd full re-run of `HPHT_001` |
| `SERUM_001a` | Replicate "a" of the `SERUM_001` group |
| `SERUM_001a-2` | 2nd re-run of replicate vial `a` |
| `HPHT_001_Desorption` | Desorption treatment variant of `HPHT_001` |
| `HPHT_001-2_Desorption` | Desorption variant of the 2nd re-run |
| `SERUM_001a-t7` | Replicate `a`, sampled destructively at day 7 |
| `CF-015` | **Standalone** experiment "015" of type CF — *not* a re-run of anything (see caveat above) |

---

## Quick checklist before you submit an ID

- [ ] Type is one of the recognized abbreviations (case doesn't matter)
- [ ] Index is present and unique for that base
- [ ] If this is a re-run, you used `-2` or higher (not `-0`/`-1`)
- [ ] If this is a replicate vial, the letter is a single lowercase letter stuck
      directly on the index, with nothing between them
- [ ] If this is a coreflood ID and re-runs matter to you, the index is spelled
      with an underscore (`CF_015`), not a bare hyphen (`CF-015`)
- [ ] Suffix order is letter, then `-N`, then `_Treatment`, then `-t<days>`

If unsure, check the experiment list after creating it — a misparsed ID usually
shows up filed as its own standalone row instead of nested under the group/parent
you expected. Rename it and the system will re-file it correctly on save.
