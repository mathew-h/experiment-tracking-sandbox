from __future__ import annotations
import hashlib
import json
from typing import Any, Literal, Optional
from pydantic import BaseModel


class PlanCreate(BaseModel):
    row: int
    experiment_id: str
    parent_id: Optional[str] = None
    copied_from: Optional[str] = None


class PlanRename(BaseModel):
    row: int
    from_id: str
    to_id: str


class PlanFieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class PlanOverwrite(BaseModel):
    row: int
    experiment_id: str
    fields_changed: list[PlanFieldChange] = []


class PlanSkip(BaseModel):
    row: int
    experiment_id: Optional[str] = None
    reason: str


class PlanConflict(BaseModel):
    row: int
    kind: str
    detail: str


class UploadPlan(BaseModel):
    """Structured create/rename/overwrite/skip/conflict summary (issue #100 item 2).
    Only populated for upload types that build one — currently new-experiments."""
    creates: list[PlanCreate] = []
    renames: list[PlanRename] = []
    overwrites: list[PlanOverwrite] = []
    skips: list[PlanSkip] = []
    conflicts: list[PlanConflict] = []
    counts: dict[str, int] = {}

    def fingerprint(self) -> str:
        """sha256 of this plan's content, for the preview->commit handshake
        (issue #100 item 5).

        Returned to the client as `UploadResponse.plan_hash` on a dry run and
        accepted back on the real submit, which recomputes it and refuses to
        commit on a mismatch.

        Two properties this relies on:

        - **Order is preserved, not sorted.** List order is meaningful for renames
          (chain renames depend on row ordering), and each entry carries its own
          `row`, so reordering rows moves the hash. Only dict keys are sorted.
        - **`counts` is excluded** because it is derived from the five lists;
          hashing it would let a client-supplied or stale `counts` change the
          fingerprint of an otherwise identical plan.

        Because `overwrites[].fields_changed` carries the *current* DB values as
        `old`, the fingerprint covers database state as well as file bytes — a
        concurrent edit by another researcher between preview and commit also
        invalidates the previewed plan, not just an edited workbook.

        `default=str` keeps this total over the arbitrary values that reach
        `PlanFieldChange.old`/`new` (dates, enums, Decimals — the field is `Any`
        because it mirrors whatever the ORM column held).
        """
        payload = {
            "creates": [c.model_dump() for c in self.creates],
            "renames": [r.model_dump() for r in self.renames],
            "overwrites": [o.model_dump() for o in self.overwrites],
            "skips": [s.model_dump() for s in self.skips],
            "conflicts": [c.model_dump() for c in self.conflicts],
        }
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class UploadResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
    message: str
    warnings: list[str] = []
    feedbacks: list[dict] = []
    dry_run: bool = False
    plan: Optional[UploadPlan] = None
    plan_hash: Optional[str] = None


class SampleConflictMatch(BaseModel):
    sample_id: str
    similarity: float


class SampleConflict(BaseModel):
    incoming_id: str
    normalized: str
    candidate_matches: list[SampleConflictMatch]


class ConflictCheckResponse(BaseModel):
    status: Literal["warnings"]
    conflicts: list[SampleConflict]
    message: str
