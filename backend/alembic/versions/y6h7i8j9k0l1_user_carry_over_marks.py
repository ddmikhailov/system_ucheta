"""user carry_over_marks preference

Revision ID: y6h7i8j9k0l1
Revises: x5g6h7i8j9k0
Create Date: 2026-10-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'y6h7i8j9k0l1'
down_revision = 'x5g6h7i8j9k0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users', sa.Column('carry_over_marks', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('users', 'carry_over_marks')
