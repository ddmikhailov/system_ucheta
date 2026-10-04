"""задачи: ступень проверки для двухступенчатой проверки

Revision ID: i0d1e2f3a4b5
Revises: h9c0d1e2f3a4
Create Date: 2026-10-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'i0d1e2f3a4b5'
down_revision = 'h9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('task_assignments', sa.Column('review_step', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('task_assignments', 'review_step')
