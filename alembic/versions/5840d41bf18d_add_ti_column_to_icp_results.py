"""add ti column to icp results

Revision ID: 5840d41bf18d
Revises: 00063a5dd6a8
Create Date: 2026-09-22

Adds the Titanium fixed column ``icp_results.ti`` (Float, ppm, nullable) and
backfills it from ``all_elements`` JSONB, where the ICP-OES parser has been
storing Ti readings all along (120 rows on the 2026-09-04 production mirror).

The same backfill runs for ten *existing* fixed columns -- ``ag ce k la na pb
sc th v`` (added by b2c3d4e5f6a7, 2026-05) and ``s`` (e78eb12b81d6, 2026-06).
The ICP-OES upload route (``backend/api/routers/bulk_uploads.py``) installs the
parser's fixed-column list at runtime, and that list was a 27-element literal
that predated all ten, so every reading landed in ``all_elements`` only and
the fixed columns were NULL on all 1171 production rows. The route now mirrors
the canonical ``ICP_ELEMENTS`` list; this fills the history so the Power BI
``v_results_icp`` columns are continuous rather than NULL-then-populated.

Backfill semantics: only NULL fixed columns are written, only from a
numeric-looking JSON value, clamped at 0 to match 458f344f73d8 (negative ppm
clamp). ``all_elements`` is left untouched. Idempotent: re-running is a no-op.

Postgres-only (``->>`` and regex match); the project has been Postgres-only
since a0e1f2b3c4d5 converted JSON to JSONB.

Downgrade drops ``ti`` after dropping ``v_results_icp`` (which now selects
``ti_ppm``); the app recreates every reporting view on startup via
``database/event_listeners.py`` -- same precedent as bcecaa35be9c. Values
backfilled into the ten pre-existing columns are left in place on downgrade:
those columns belong to earlier revisions and the data still exists in JSONB.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5840d41bf18d'
down_revision: Union[str, None] = '00063a5dd6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# New fixed element column(s) introduced by this revision.
NEW_COLUMNS: tuple[str, ...] = ('ti',)

# Fixed element columns whose NULLs are filled from all_elements JSONB.
# 'ti' is new here; the other ten existed but were never populated (see docstring).
BACKFILL_FROM_JSON: tuple[str, ...] = (
    'ti', 'ag', 'ce', 'k', 'la', 'na', 'pb', 'sc', 'th', 'v', 's',
)

# Accept plain decimals and exponent notation; reject 'nd', '<0.01', '', etc.
_NUMERIC_RE = r'^\s*-?[0-9]+(\.[0-9]*)?([eE][-+]?[0-9]+)?\s*$'


def _existing_columns() -> set[str]:
    from alembic import context
    conn = context.get_context().bind
    return {col['name'] for col in sa.inspect(conn).get_columns('icp_results')}


def upgrade() -> None:
    existing = _existing_columns()

    for name in NEW_COLUMNS:
        if name not in existing:
            op.add_column('icp_results', sa.Column(name, sa.Float(), nullable=True))
            existing.add(name)

    for el in BACKFILL_FROM_JSON:
        if el not in existing:
            # Defensive: a DB that skipped an earlier revision has nowhere to
            # put the value; leave it in JSONB rather than fail the deploy.
            continue
        # `el` comes from the constant tuple above, never from input.
        op.execute(sa.text(
            f"UPDATE icp_results "
            f"   SET {el} = GREATEST((all_elements->>'{el}')::double precision, 0) "
            f" WHERE {el} IS NULL "
            f"   AND all_elements->>'{el}' IS NOT NULL "
            f"   AND all_elements->>'{el}' ~ :numeric_re"
        ).bindparams(numeric_re=_NUMERIC_RE))


def downgrade() -> None:
    existing = _existing_columns()

    # v_results_icp selects icp.ti AS ti_ppm; Postgres refuses to drop a column a
    # view depends on. The app recreates all reporting views on startup.
    op.execute("DROP VIEW IF EXISTS v_results_icp CASCADE")

    for name in reversed(NEW_COLUMNS):
        if name in existing:
            op.drop_column('icp_results', name)
