"""add icp element columns ag ce k la na pb sc th v

Revision ID: b2c3d4e5f6a7
Revises: fad70818aaf6
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'fad70818aaf6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    existing = {col['name'] for col in inspector.get_columns('icp_results')}

    new_columns = {
        'ag': sa.Column('ag', sa.Float(), nullable=True),
        'ce': sa.Column('ce', sa.Float(), nullable=True),
        'k':  sa.Column('k',  sa.Float(), nullable=True),
        'la': sa.Column('la', sa.Float(), nullable=True),
        'na': sa.Column('na', sa.Float(), nullable=True),
        'pb': sa.Column('pb', sa.Float(), nullable=True),
        'sc': sa.Column('sc', sa.Float(), nullable=True),
        'th': sa.Column('th', sa.Float(), nullable=True),
        'v':  sa.Column('v',  sa.Float(), nullable=True),
    }

    for name, column in new_columns.items():
        if name not in existing:
            op.add_column('icp_results', column)


def downgrade() -> None:
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    existing = {col['name'] for col in inspector.get_columns('icp_results')}

    for name in ['v', 'th', 'sc', 'pb', 'na', 'la', 'k', 'ce', 'ag']:
        if name in existing:
            op.drop_column('icp_results', name)
