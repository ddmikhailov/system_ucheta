"""периодические задачи: расписание на шаблоне, связь задачи с шаблоном

Revision ID: l3a4b5c6d7e8
Revises: k2f3a4b5c6d7
Create Date: 2026-10-04 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'l3a4b5c6d7e8'
down_revision = 'k2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('task_templates', sa.Column('repeat', sa.String(16), nullable=False, server_default=''))
    op.add_column('task_templates', sa.Column('repeat_day', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('task_templates', sa.Column('due_offset_days', sa.Integer(), nullable=False, server_default='14'))
    op.add_column('task_templates', sa.Column('next_run', sa.Date(), nullable=True))
    op.add_column('task_templates', sa.Column('last_run_date', sa.Date(), nullable=True))
    op.add_column('task_templates', sa.Column('last_error', sa.String(500), nullable=True))
    op.add_column('tasks', sa.Column('template_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('period_key', sa.String(16), nullable=True))
    op.create_foreign_key('fk_tasks_template_id', 'tasks', 'task_templates', ['template_id'], ['id'])
    op.create_unique_constraint('uq_task_template_period', 'tasks', ['template_id', 'period_key'])


def downgrade() -> None:
    op.drop_constraint('uq_task_template_period', 'tasks', type_='unique')
    op.drop_constraint('fk_tasks_template_id', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'period_key')
    op.drop_column('tasks', 'template_id')
    for column in ('last_error', 'last_run_date', 'next_run', 'due_offset_days', 'repeat_day', 'repeat'):
        op.drop_column('task_templates', column)
