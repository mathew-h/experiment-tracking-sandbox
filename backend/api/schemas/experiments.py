from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from database.models.enums import ExperimentStatus, NoteType


class ExperimentCreate(BaseModel):
    experiment_id: str
    experiment_number: Optional[int] = None   # auto-assigned if omitted
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: ExperimentStatus = ExperimentStatus.ONGOING
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None


class ExperimentUpdate(BaseModel):
    experiment_id: Optional[str] = Field(None, min_length=1, max_length=100)
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[ExperimentStatus] = None
    is_outlier: Optional[bool] = None

    @field_validator("is_outlier")
    @classmethod
    def _is_outlier_not_null(cls, v: Optional[bool]) -> bool:
        if v is None:
            raise ValueError("is_outlier cannot be null; send true or false, or omit the field")
        return v


class ExperimentStatusUpdate(BaseModel):
    status: ExperimentStatus


class NextIdResponse(BaseModel):
    next_id: str


class ExperimentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    experiment_number: int
    status: Optional[ExperimentStatus] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    created_at: datetime
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    replicate_label: Optional[str] = None
    is_outlier: bool = False
    id_timepoint_days: Optional[float] = None
    # Joined from conditions (may be None if no conditions recorded yet)
    experiment_type: Optional[str] = None
    reactor_number: Optional[int] = None
    # Derived from additives view
    additives_summary: Optional[str] = None
    # First note text
    condition_note: Optional[str] = None
    # Issue #98. What the ID column should render: the group stem in grouped
    # mode, the timepoint-stripped stem in flat mode. `experiment_id` above
    # continues to name the real representative row -- do not conflate them.
    group_display_id: Optional[str] = None
    # Number of experiment rows this row stands for (1 = an ordinary row).
    vial_count: int = 1
    # Grouped mode only: the group's DISTINCT replicate letters, for the badge.
    # None in flat mode and for rows that are not groups.
    replicate_letters: Optional[list[str]] = None
    # Grouped-list mode only (group_replicates=true): one entry per replicate
    # letter-row of this group, collapsed on the timepoint stem (issue #98 D8 --
    # this includes the representative's own letter). None in flat mode and for
    # rows that are not groups.
    replicates: Optional[list["ExperimentListItem"]] = None


ExperimentListItem.model_rebuild()


class ExperimentListResponse(BaseModel):
    """Paginated list response."""
    items: list[ExperimentListItem]
    total: int
    skip: int
    limit: int


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    experiment_number: int
    status: Optional[ExperimentStatus] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    sample_id: Optional[str] = None
    base_experiment_id: Optional[str] = None
    parent_experiment_fk: Optional[int] = None
    replicate_label: Optional[str] = None
    is_outlier: bool = False
    id_timepoint_days: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExperimentDetailResponse(ExperimentResponse):
    """Full detail including nested conditions, notes, modifications."""
    conditions: Optional[dict] = None
    notes: list[dict] = []
    modifications: list[dict] = []


class NoteCreate(BaseModel):
    """Body of POST /experiments/{id}/notes.

    Issue #118: `note_type` defaults to the scope-free 'observation' so every
    existing caller keeps working unchanged. `result_id` scopes the note to one
    of the experiment's own result rows; the router rejects a result of another
    experiment (422) before the composite FK would, and the DB's ck_note_scope
    is mirrored as a 422 for a friendlier message. Nothing here is required
    beyond the text itself -- behaviour change comes from visibility, not
    validators.
    """
    note_text: str
    note_type: NoteType = NoteType.observation
    result_id: Optional[int] = None


class NoteUpdate(BaseModel):
    """Body of PATCH /experiments/{id}/notes/{note_id}. Every field optional;
    at least one must be present. `needs_review=false` is how a review-queue
    row is resolved without deleting it (issue #118 PR3); `note_type` retypes
    a note (scope rules apply: 'description' cannot carry a result_id, and
    'modification' / 'result_note' must)."""
    note_text: Optional[str] = Field(default=None, min_length=1)
    note_type: Optional[NoteType] = None
    needs_review: Optional[bool] = None

    @model_validator(mode="after")
    def _at_least_one_field(self):
        # A field validator would not run for an omitted field, so check the model.
        if self.note_text is None and self.note_type is None and self.needs_review is None:
            raise ValueError("provide at least one of note_text, note_type, needs_review")
        return self


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: str
    note_text: Optional[str] = None
    note_type: NoteType = NoteType.observation
    result_id: Optional[int] = None
    created_by: Optional[str] = None
    needs_review: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReviewNoteItem(NoteResponse):
    """One review-queue row (issue #118 PR3): a note with needs_review = true,
    plus enough experiment context to act on it without another request."""
    experiment_fk: int
    researcher: Optional[str] = None
    time_post_reaction_days: Optional[float] = None


class ReviewQueueResponse(BaseModel):
    items: list[ReviewNoteItem]
    total: int
    skip: int
    limit: int


class NotesBulkPatch(BaseModel):
    """Body of PATCH /experiments/notes/bulk (issue #122 PR-A).

    Acts on up to 500 notes at once. At least one of `needs_review` /
    `note_type` must be present. The call is atomic: any id that is unknown
    (404) or whose scope forbids the requested type (422) rejects the whole
    request before a row is written. Duplicate ids are collapsed.
    """
    ids: list[int] = Field(min_length=1, max_length=500)
    needs_review: Optional[bool] = None
    note_type: Optional[NoteType] = None

    @model_validator(mode="after")
    def _at_least_one_action(self):
        if self.needs_review is None and self.note_type is None:
            raise ValueError("provide at least one of needs_review, note_type")
        return self


class NotesBulkDelete(BaseModel):
    """Body of DELETE /experiments/notes/bulk (issue #122 PR-A). Same cap and
    atomicity as NotesBulkPatch."""
    ids: list[int] = Field(min_length=1, max_length=500)


class NotesBulkResponse(BaseModel):
    """`count` notes changed (or deleted); `ids` names them, sorted. A note
    already in the requested state is not counted and gets no audit row."""
    count: int
    ids: list[int]


class ReplicateGroupMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    experiment_id: str
    replicate_label: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    is_outlier: bool = False


class ReplicateGroupResponse(BaseModel):
    base_experiment_id: str
    parent: Optional[ReplicateGroupMember] = None
    members: list[ReplicateGroupMember] = []


class ReplicateGroupMemberDetail(ReplicateGroupMember):
    """A ReplicateGroupMember plus per-member detail for the group page:
    timepoint, researcher/date, result count, and — for fields the group's
    conditions diverge on — this member's own value under `conditions`.
    `conditions` holds ONLY the divergent fields; fields shared across the
    whole group live on the parent response's `shared_conditions` instead.
    """
    id_timepoint_days: Optional[float] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    result_count: int = 0
    conditions: dict[str, Any] = {}


class ReplicateLetterGroup(BaseModel):
    """One replicate letter and its vials (issue #98).

    A letter maps to several vials when the replicate set is sacrificed per
    timepoint: letter "a" of SERUM_001 is SERUM_001a-t1 plus SERUM_001a-t3.
    """
    replicate_label: str
    vials: list[ReplicateGroupMemberDetail] = []


class ReplicateGroupDetailResponse(BaseModel):
    """Response for GET /api/experiments/groups/{base_id}.

    Addressed by the base-ID *string*, which is not guaranteed to name an
    experiment row — `parent` is None when no group-parent row exists
    (the common case for lettered-only replicate sets).
    """
    base_experiment_id: str
    # Widened from ReplicateGroupMember (issue #98) so a parent that has its own
    # results can render its Timepoint / Results / divergent cells instead of
    # hard-coding em dashes.
    parent: Optional[ReplicateGroupMemberDetail] = None
    members: list[ReplicateGroupMemberDetail] = []
    # Per-VIAL count -- unchanged meaning, still equal to len(members).
    member_count: int = 0
    # Issue #98: the same members grouped by replicate letter, plus the count of
    # LETTERS. `member_count` above stays per-vial; these are additive.
    replicates: list[ReplicateLetterGroup] = []
    replicate_count: int = 0
    shared_conditions: dict[str, Any] = {}
    divergent_fields: list[str] = []
    additives_summary: Optional[str] = None
    additive_names: Optional[str] = None
    additives_diverge: bool = False


class ReplicateCreateRequest(BaseModel):
    base_experiment_id: str
    count: int = Field(3, ge=1, le=25)


class ReplicateCreateResponse(BaseModel):
    created: list[ExperimentResponse]
    skipped: list[str] = []


class DeleteImpactResponse(BaseModel):
    """What deleting an experiment destroys and decouples (issue #99).

    `total` sums the counts only. `background_for` and `replicate_children`
    are decoupled -- those experiments survive -- so they are excluded from it.
    The UI demands a typed-ID confirmation when anything is destroyed OR
    decoupled.
    """
    experiment_id: str
    # The setup row, hard-deleted by the ORM cascade. Counted so the dialog
    # cannot report "nothing else is affected" while destroying it.
    conditions: int = 0
    results: int = 0
    scalar_results: int = 0
    icp_results: int = 0
    result_files: int = 0
    notes: int = 0
    additives: int = 0
    external_analyses: int = 0
    xrd_phases: int = 0
    change_requests: int = 0
    total: int = 0
    background_for: list[str] = []
    replicate_children: list[str] = []


class ExperimentDeletedResponse(BaseModel):
    """Body of DELETE /api/experiments/{experiment_id} (issue #99).

    This endpoint returns 200 with a body, NOT 204: the acceptance criteria
    require it to report which experiments were decoupled, which a 204 cannot
    carry. `impact` is measured immediately before the delete, so it reflects
    what actually happened rather than the pre-flight estimate.
    """
    experiment_id: str
    deleted: bool = True
    impact: DeleteImpactResponse
