"""user display title

Revision ID: d4e8a0c3f6b1
Revises: c7a2e4f9d1b3
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e8a0c3f6b1'
down_revision = 'c7a2e4f9d1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('display_title', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'display_title')
