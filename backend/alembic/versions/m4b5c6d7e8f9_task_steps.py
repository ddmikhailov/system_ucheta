"""многошаговые задачи: цепочка задач-шагов и закрытые назначения

Revision ID: m4b5c6d7e8f9
Revises: l3a4b5c6d7e8
Create Date: 2026-10-04 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'm4b5c6d7e8f9'
down_revision = 'l3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('series_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('step_no', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('tasks', sa.Column('unlock_on', sa.String(16), nullable=True))
    op.create_index('ix_tasks_series_id', 'tasks', ['series_id'])
    op.add_column('task_assignments', sa.Column('locked', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('task_assignments', 'locked')
    op.drop_index('ix_tasks_series_id', table_name='tasks')
    op.drop_column('tasks', 'unlock_on')
    op.drop_column('tasks', 'step_no')
    op.drop_column('tasks', 'series_id')
