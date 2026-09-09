"""One-time backfill: give every existing note a declared type, and move the two
legacy free-text result columns into the typed notes model (issue #118, PR2).

Background
----------
Until PR1 of #118 free text about an experiment lived in four places with
nothing declaring what each was for:

* experiment_notes -- the "description" was whichever note came FIRST, and the
  three readers disagreed on "first": v_experiments ordered by created_at, the
  experiments list and dashboard by min(id). Because created_at is the
  transaction timestamp, every note a bulk upload inserted in one transaction
  shares a created_at, so the view's LIMIT 1 was arbitrary.
* experimental_results.description -- NOT NULL, required by the UI, faked by
  the Master upload for a blank cell, rendered nowhere in the app. A required
  field with no feedback loop collects filler ("Gas sample", "Liquid sample").
* experimental_results.brine_modification_description -- the only timepoint
  text with a visible affordance (the MOD badge), so real content was
  smuggled into it.

PR1 added note_type / result_id / created_by / needs_review to experiment_notes
(every existing row landed as 'observation') and made every write path write
BOTH the legacy column and a typed note. This script is the one-time
reclassification of what was already there. PR3 switches the readers to the
notes model; PR4 drops the legacy columns.

Rules, in order (deterministic; nothing is guessed)
----------------------------------------------------
Only LEGACY notes are touched: rows with created_by IS NULL. Every note PR1's
dual-write has written since carries a created_by and already has the right
type, so this script never rewrites those.

1. Per experiment, the oldest legacy note by min(id) becomes 'description'.
   min(id), not created_at -- see above for why created_at cannot order notes
   from one bulk transaction. Every other legacy note becomes 'observation'
   with result_id NULL (it already is; the UPDATE is explicit so the outcome
   does not depend on the migration default). If the experiment already holds
   a 'description' note written through PR1's API, that explicit choice is
   kept and the min(id) note stays 'observation' -- reported, not overridden.
2. A legacy note whose trimmed text lowercases to 'nan' is an artifact of the
   blank-initial_note bug PR1 fixed (docs/issues/issue-blank-initial-note-
   parses-to-nan.md), not researcher text. It is flagged needs_review and is
   NOT promoted, even when it is the oldest note. Nothing else is promoted in
   its place -- that would be a guess -- so such an experiment ends with no
   description; the report names it.
3. Every non-blank brine_modification_description becomes a note row:
   note_type='modification', result_id=er.id, experiment_fk=er.experiment_fk,
   created_at=er.created_at, created_by='reclassify_notes_020'. If a
   'modification' note with the same text already sits on that result
   (PR1's dual-write put it there), nothing is inserted.
4. experimental_results.description is classified by pattern:
   * matches ^\\s*(gas|liquid|solid|aqueous|gas\\s*\\+\\s*liquid)(\\s+sample)?\\s*$
     case-insensitively, or starts with 'Master upload — day ': discarded --
     it carries no information (the second is text this codebase generated).
   * 4b (Mat, 2026-09-09): a GC method / injection tag -- text built only from
     the tokens gas, liquid, liq, solid, DI, GC-A, GC-B, FL, Full Loop (with
     optional parenthesised method, e.g. 'Gas (GC-A)') joined by , ; . / + and,
     and containing at least one GC token -- is discarded. These say which GC
     method produced a reading; they matter to the person running the GC on
     the results sheet, not as a note on the experiment. Any extra word
     ('Cold dip tube liquid, GC-A') keeps the text out of this rule, and a
     plain fraction list with no GC token ('gas, liquid') is NOT covered.
     Reported on its own line so the audit can see the split.
   * blank: nothing to carry.
   * otherwise: an 'observation' note on the result with needs_review=true,
     created_at=er.created_at, created_by='reclassify_notes_020'. If an
     'observation' note with the same text already sits on that result, nothing
     is inserted.
   The pattern is applied AS SPECIFIED. The report prints the most frequent
   preserved texts precisely so a human can see what the pattern did not
   catch; the pattern is not widened here to make the numbers look better.
5. Anything the rules cannot place is written with needs_review=true, never
   dropped, never guessed at. In this data set that is exactly the rule-2 and
   rule-4 rows; the report's last line is the total review queue.

Idempotent: re-running after --apply finds nothing to promote (no legacy note
lacks a type decision it already has) and inserts no duplicate result notes.

Legacy columns are NOT cleared here. Power BI reads them until PR3, and PR4
drops them.

Usage:
    # Dry run (preview only, no writes) -- the report Mat audits
    python database/data_migrations/reclassify_notes_020.py

    # Apply (only after the dry-run report has been audited)
    python database/data_migrations/reclassify_notes_020.py --apply

    # Against a specific database (defaults to $DATABASE_URL, then the dev DB)
    DATABASE_URL=postgresql://... python database/data_migrations/reclassify_notes_020.py
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database import get_db  # noqa: E402

SOURCE_TAG = "reclassify_notes_020"

# Rule 4 filler pattern -- exactly as specified in issue #118.
FILLER_REGEX = r"^\s*(gas|liquid|solid|aqueous|gas\s*\+\s*liquid)(\s+sample)?\s*$"
MASTER_FALLBACK_PREFIX = "Master upload — day "

# Rule 4b -- GC method / injection tags (Mat, 2026-09-09). A text made only of
# these tokens and separators, containing at least one GC token, is a tag for
# whoever runs the GC, not a note. Python `re`, applied to the trimmed text.
_GC_TOKENS = r"(?:gc-a|gc-b|di|fl|full\s*loop)"
_FRACTION_TOKENS = r"(?:gas|liquid|liq|solid)"
_TAG_TOKEN = rf"(?:{_FRACTION_TOKENS}|{_GC_TOKENS})(?:\s*\(\s*{_GC_TOKENS}\s*\))?"
_TAG_SEP = r"\s*(?:,|;|\.|/|\+|\band\b)\s*"
GC_TAG_REGEX = re.compile(
    rf"^(?=.*{_GC_TOKENS})\s*{_TAG_TOKEN}(?:{_TAG_SEP}{_TAG_TOKEN})*\s*\.?\s*$",
    re.IGNORECASE,
)

SAMPLE_SIZE = 20
TOP_N_PRESERVED = 15


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    # Rule 1
    promote_ids: List[int] = field(default_factory=list)          # legacy note ids -> description
    demote_ids: List[int] = field(default_factory=list)           # legacy note ids -> observation (explicit)
    kept_pr1_description: List[Tuple[str, int, int]] = field(default_factory=list)  # (experiment_id, pr1 note id, min legacy id)
    already_promoted_experiments: int = 0                        # a prior run's description exists
    # Rule 2
    nan_note_ids: List[int] = field(default_factory=list)          # every legacy 'nan' note
    nan_newly_flagged: List[int] = field(default_factory=list)     # ...of which not yet needs_review
    nan_experiments_without_description: List[str] = field(default_factory=list)
    # Rule 3
    modification_inserts: List[Tuple[int, int, str]] = field(default_factory=list)  # (result_id, experiment_fk, text)
    modification_already_mirrored: int = 0
    # Rule 4
    discarded_filler: List[Tuple[int, str]] = field(default_factory=list)          # (result_id, text)  rule 4
    discarded_gc_tags: List[Tuple[int, str]] = field(default_factory=list)         # (result_id, text)  rule 4b
    blank_descriptions: int = 0
    observation_inserts: List[Tuple[int, int, str]] = field(default_factory=list)  # (result_id, experiment_fk, text)
    observation_already_mirrored: int = 0
    # Context
    experiments_total: int = 0
    experiments_with_zero_notes: List[str] = field(default_factory=list)
    legacy_notes_total: int = 0
    pr1_notes_total: int = 0

    @property
    def review_queue_total(self) -> int:
        """Rows --apply will ADD to the review queue (idempotent on re-run)."""
        return len(self.nan_newly_flagged) + len(self.observation_inserts)


def _is_nan(text_value: Optional[str]) -> bool:
    return text_value is not None and text_value.strip().lower() == "nan"


def build_plan(db: Session) -> Plan:
    """Read-only. Everything --apply will do is decided here."""
    plan = Plan()

    plan.experiments_total = db.execute(text("SELECT COUNT(*) FROM experiments")).scalar()
    plan.experiments_with_zero_notes = [
        r[0] for r in db.execute(text(
            "SELECT e.experiment_id FROM experiments e"
            " WHERE NOT EXISTS (SELECT 1 FROM experiment_notes n WHERE n.experiment_fk = e.id)"
            " ORDER BY e.experiment_id"
        ))
    ]
    plan.legacy_notes_total = db.execute(
        text("SELECT COUNT(*) FROM experiment_notes WHERE created_by IS NULL")
    ).scalar()
    plan.pr1_notes_total = db.execute(
        text("SELECT COUNT(*) FROM experiment_notes WHERE created_by IS NOT NULL")
    ).scalar()

    # Experiments that already hold a description note. created_by set -> written
    # through PR1's API (kept, rule 1 last sentence); created_by NULL -> promoted
    # by a previous run of this script (idempotency: nothing to do).
    existing_descriptions = {
        fk: (nid, is_pr1) for fk, nid, is_pr1 in db.execute(text(
            "SELECT experiment_fk, MIN(id), bool_or(created_by IS NOT NULL) FROM experiment_notes"
            " WHERE note_type = 'description'"
            " GROUP BY experiment_fk"
        ))
    }

    # Rules 1 + 2 over legacy notes, grouped by experiment in id order.
    rows = db.execute(text(
        "SELECT n.id, n.experiment_fk, e.experiment_id, n.note_text,"
        "       n.note_type::text, n.result_id, n.needs_review"
        " FROM experiment_notes n JOIN experiments e ON e.id = n.experiment_fk"
        " WHERE n.created_by IS NULL"
        " ORDER BY n.experiment_fk, n.id"
    )).fetchall()
    current_fk = None
    promoted_for_current = False
    for note_id, fk, exp_id, note_text, note_type, result_id, needs_review in rows:
        if fk != current_fk:
            current_fk = fk
            promoted_for_current = False
            first_in_experiment = True
            if fk in existing_descriptions and not existing_descriptions[fk][1]:
                plan.already_promoted_experiments += 1
        else:
            first_in_experiment = False

        def _demote():
            # Explicit, but only when the row is not already in the target state.
            if note_type != "observation" or result_id is not None:
                plan.demote_ids.append(note_id)

        if _is_nan(note_text):
            plan.nan_note_ids.append(note_id)
            if not needs_review:
                plan.nan_newly_flagged.append(note_id)
            _demote()
            if first_in_experiment and fk not in existing_descriptions:
                # Rule 2: not promoted, and nothing promoted in its place.
                plan.nan_experiments_without_description.append(exp_id)
                promoted_for_current = True  # blocks promotion of a later note
            continue

        if fk in existing_descriptions:
            existing_id, is_pr1 = existing_descriptions[fk]
            if existing_id == note_id:
                # This legacy note IS the description already (prior run). Keep.
                promoted_for_current = True
                continue
            if first_in_experiment and is_pr1:
                plan.kept_pr1_description.append((exp_id, existing_id, note_id))
            promoted_for_current = True
            _demote()
            continue

        if not promoted_for_current:
            plan.promote_ids.append(note_id)
            promoted_for_current = True
        else:
            _demote()

    # Rule 3: brine_modification_description -> modification note.
    for result_id, fk, brine in db.execute(text(
        "SELECT er.id, er.experiment_fk, btrim(er.brine_modification_description)"
        " FROM experimental_results er"
        " WHERE btrim(coalesce(er.brine_modification_description, '')) <> ''"
        " ORDER BY er.id"
    )):
        if _is_nan(brine):
            # 019 cleaned these; defensive -- a 'nan' modification is filler, not text.
            continue
        exists = db.execute(text(
            "SELECT 1 FROM experiment_notes"
            " WHERE result_id = :rid AND note_type = 'modification' AND btrim(note_text) = :t LIMIT 1"
        ), {"rid": result_id, "t": brine}).first()
        if exists:
            plan.modification_already_mirrored += 1
        else:
            plan.modification_inserts.append((result_id, fk, brine))

    # Rule 4: experimental_results.description classified by pattern.
    for result_id, fk, desc in db.execute(text(
        "SELECT er.id, er.experiment_fk, er.description FROM experimental_results er ORDER BY er.id"
    )):
        stripped = (desc or "").strip()
        if not stripped:
            plan.blank_descriptions += 1
            continue
        is_filler = db.execute(
            text("SELECT :d ~* :re OR :d LIKE :prefix"),
            {"d": stripped, "re": FILLER_REGEX, "prefix": MASTER_FALLBACK_PREFIX + "%"},
        ).scalar()
        if is_filler:
            plan.discarded_filler.append((result_id, stripped))
            continue
        if GC_TAG_REGEX.match(stripped):
            plan.discarded_gc_tags.append((result_id, stripped))
            continue
        exists = db.execute(text(
            "SELECT 1 FROM experiment_notes"
            " WHERE result_id = :rid AND note_type = 'observation' AND btrim(note_text) = :t LIMIT 1"
        ), {"rid": result_id, "t": stripped}).first()
        if exists:
            plan.observation_already_mirrored += 1
        else:
            plan.observation_inserts.append((result_id, fk, stripped))

    return plan


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _sample(items, n=SAMPLE_SIZE):
    return items[:n]


def print_report(plan: Plan) -> None:
    p = print
    p("=" * 78)
    p("reclassify_notes_020 -- plan report")
    p("=" * 78)
    p(f"experiments total:                                {plan.experiments_total}")
    p(f"experiments with ZERO notes:                      {len(plan.experiments_with_zero_notes)}")
    if plan.experiments_with_zero_notes:
        p("  sample: " + ", ".join(_sample(plan.experiments_with_zero_notes)))
    p(f"legacy notes (created_by IS NULL):                {plan.legacy_notes_total}")
    p(f"PR1-era notes (created_by set, left untouched):   {plan.pr1_notes_total}")
    p("")
    p("-- Rule 1: oldest legacy note per experiment by min(id) -> description")
    p(f"  notes to promote to 'description':              {len(plan.promote_ids)}")
    p(f"  notes set to 'observation' (result_id NULL):    {len(plan.demote_ids)}")
    p(f"  experiments keeping a PR1-era description:      {len(plan.kept_pr1_description)}")
    p(f"  experiments already promoted by a prior run:    {plan.already_promoted_experiments}")
    for exp_id, pr1_id, legacy_id in _sample(plan.kept_pr1_description):
        p(f"    {exp_id}: keeps note {pr1_id}, legacy min(id) note {legacy_id} stays observation")
    p("")
    p("-- Rule 2: legacy notes reading 'nan' -> needs_review, never promoted")
    p(f"  'nan' legacy notes:                             {len(plan.nan_note_ids)}")
    p(f"  ...newly flagged needs_review by this run:      {len(plan.nan_newly_flagged)}")
    p(f"  experiments whose OLDEST note is 'nan' and therefore end with NO description: "
      f"{len(plan.nan_experiments_without_description)}")
    if plan.nan_experiments_without_description:
        p("  " + ", ".join(plan.nan_experiments_without_description))
    p("")
    p("-- Rule 3: brine_modification_description -> 'modification' note on the result")
    p(f"  notes to insert:                                {len(plan.modification_inserts)}")
    p(f"  already mirrored by PR1 dual-write (skipped):   {plan.modification_already_mirrored}")
    for rid, _fk, t in _sample(plan.modification_inserts, 10):
        p(f"    result {rid}: {t[:90]!r}")
    p("")
    p("-- Rule 4: experimental_results.description")
    p(f"  filler pattern:  {FILLER_REGEX}")
    p(f"  or prefix:       {MASTER_FALLBACK_PREFIX!r}")
    p(f"  blank (nothing to carry):                       {plan.blank_descriptions}")
    p(f"  DISCARDED as filler (rule 4):                   {len(plan.discarded_filler)}")
    p(f"  DISCARDED as GC method tag (rule 4b):           {len(plan.discarded_gc_tags)}")
    p(f"  PRESERVED as observation, needs_review=true:    {len(plan.observation_inserts)}")
    p(f"  already mirrored by PR1 dual-write (skipped):   {plan.observation_already_mirrored}")
    p("")
    p(f"  sample of {SAMPLE_SIZE} DISCARDED (result_id: text):")
    for rid, t in _sample(plan.discarded_filler):
        p(f"    {rid}: {t!r}")
    p(f"  distinct GC method tags discarded (rule 4b), by frequency:")
    for t, n in Counter(t for _r, t in plan.discarded_gc_tags).most_common():
        p(f"    {n:5d}  {t!r}")
    p(f"  sample of {SAMPLE_SIZE} PRESERVED (result_id: text):")
    for rid, _fk, t in _sample(plan.observation_inserts):
        p(f"    {rid}: {t[:90]!r}")
    p(f"  top {TOP_N_PRESERVED} PRESERVED texts by frequency (what the pattern did NOT catch):")
    for t, n in Counter(t for _r, _f, t in plan.observation_inserts).most_common(TOP_N_PRESERVED):
        p(f"    {n:5d}  {t[:80]!r}")
    p("")
    p("-- Review queue (needs_review = true after --apply)")
    p(f"  'nan' legacy notes newly flagged:               {len(plan.nan_newly_flagged)}")
    p(f"  preserved result descriptions:                  {len(plan.observation_inserts)}")
    p(f"  TOTAL rows landing in the review queue:         {plan.review_queue_total}")
    p("=" * 78)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_plan(db: Session, plan: Plan) -> None:
    """Execute the plan in one transaction. Caller commits."""
    if plan.demote_ids:
        db.execute(text(
            "UPDATE experiment_notes SET note_type = 'observation', result_id = NULL"
            " WHERE id = ANY(:ids)"
        ), {"ids": plan.demote_ids})
    if plan.nan_newly_flagged:
        db.execute(text(
            "UPDATE experiment_notes SET needs_review = true WHERE id = ANY(:ids)"
        ), {"ids": plan.nan_newly_flagged})
    if plan.promote_ids:
        db.execute(text(
            "UPDATE experiment_notes SET note_type = 'description', result_id = NULL"
            " WHERE id = ANY(:ids)"
        ), {"ids": plan.promote_ids})
    for result_id, fk, t in plan.modification_inserts:
        db.execute(text(
            "INSERT INTO experiment_notes"
            " (experiment_id, experiment_fk, note_text, note_type, result_id, created_by, needs_review, created_at)"
            " SELECT e.experiment_id, er.experiment_fk, :t, 'modification', er.id, :src, false, er.created_at"
            " FROM experimental_results er JOIN experiments e ON e.id = er.experiment_fk"
            " WHERE er.id = :rid AND er.experiment_fk = :fk"
        ), {"t": t, "src": SOURCE_TAG, "rid": result_id, "fk": fk})
    for result_id, fk, t in plan.observation_inserts:
        db.execute(text(
            "INSERT INTO experiment_notes"
            " (experiment_id, experiment_fk, note_text, note_type, result_id, created_by, needs_review, created_at)"
            " SELECT e.experiment_id, er.experiment_fk, :t, 'observation', er.id, :src, true, er.created_at"
            " FROM experimental_results er JOIN experiments e ON e.id = er.experiment_fk"
            " WHERE er.id = :rid AND er.experiment_fk = :fk"
        ), {"t": t, "src": SOURCE_TAG, "rid": result_id, "fk": fk})


def after_counts(db: Session) -> dict:
    q = lambda s: db.execute(text(s)).scalar()  # noqa: E731
    return {
        "description_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'description'"),
        "experiments_with_description": q(
            "SELECT COUNT(DISTINCT experiment_fk) FROM experiment_notes WHERE note_type = 'description'"
        ),
        "modification_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'modification'"),
        "observation_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'observation'"),
        "review_queue": q("SELECT COUNT(*) FROM experiment_notes WHERE needs_review"),
        "notes_total": q("SELECT COUNT(*) FROM experiment_notes"),
    }


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        before = after_counts(db)
        plan = build_plan(db)
        print_report(plan)
        print("before:", before)

        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return

        apply_plan(db, plan)
        db.commit()
        after = after_counts(db)
        print("after: ", after)
        if after["review_queue"] != before["review_queue"] + plan.review_queue_total:
            print(
                "WARNING: review queue after apply does not match the plan "
                f"(expected {before['review_queue'] + plan.review_queue_total}, got {after['review_queue']})",
                file=sys.stderr,
            )
            sys.exit(2)
        print(f"\nApplied. Review queue = {after['review_queue']} (matches the dry-run plan).")
    except Exception as exc:
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
