"""add reactor_slot to conditions

Revision ID: 1c1ef9b555e0
Revises: 293d0ea59422
Create Date: 2026-07-30 06:33:05.367964

Issue #97. Stores the canonical physical slot label so occupancy comparisons stop
keying on the bare `reactor_number`, which conflates R01 (HPHT vessel 1) with CF01
(Core Flood rig 1).

Purely additive: one nullable column, one index, one UPDATE. It cannot fail against
production data, which matters because update.ps1 runs `alembic upgrade head` on the
lab PC nightly. The one-ONGOING-per-slot trigger and the
`CHECK (reactor_number > 0)` from the issue's §4 are deliberately NOT here — both
fail against current data until the cleanup in
docs/issues/audit-2026-07-28-results-and-cleanup.md has run.

The CASE below re-expresses database/reactor_slot.py::derive_reactor_slot in SQL.
tests/models/test_reactor_slot_column.py pins the two together over every
experiment_type spelling found in prod (`HPHT`, `Serum`, `SERUM`, `Autoclave`,
`Core Flood`, `Other`, `OTHER`, `AUTO`, `AUTOCLAVE`, `CF`). Rows with a
non-occupancy type, or reactor_number <= 0, are left NULL on purpose: NULL means
"holds no physical slot", which is what makes every downstream occupancy query
type-safe by construction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c1ef9b555e0'
down_revision: Union[str, None] = '293d0ea59422'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKFILL = """
UPDATE experimental_conditions
SET reactor_slot = CASE
    WHEN lower(btrim(regexp_replace(coalesce(experiment_type, ''), '\\s+', ' ', 'g')))
         IN ('core flood', 'coreflood', 'cf')
        THEN 'CF' || lpad(reactor_number::text, 2, '0')
    WHEN lower(btrim(regexp_replace(coalesce(experiment_type, ''), '\\s+', ' ', 'g')))
         = 'hpht'
        THEN 'R' || lpad(reactor_number::text, 2, '0')
    ELSE NULL
END
WHERE reactor_number IS NOT NULL
  AND reactor_number > 0
"""


def upgrade() -> None:
    op.add_column(
        'experimental_conditions',
        sa.Column('reactor_slot', sa.String(length=8), nullable=True),
    )
    op.create_index(
        'ix_experimental_conditions_reactor_slot',
        'experimental_conditions',
        ['reactor_slot'],
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_index(
        'ix_experimental_conditions_reactor_slot',
        table_name='experimental_conditions',
    )
    op.drop_column('experimental_conditions', 'reactor_slot')
