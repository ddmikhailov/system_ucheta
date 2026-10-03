"""задачи от администрации: задачи, назначения по группам, ответы, комментарии

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
Create Date: 2026-10-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'h9c0d1e2f3a4'
down_revision = 'g8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('collect_mode', sa.String(16), nullable=False),
        sa.Column('reviewer_rule', sa.String(24), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('fields_json', sa.Text(), nullable=False),
        sa.Column('scope_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'task_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='new'),
        sa.Column('group_values_json', sa.Text(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('review_comment', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('task_id', 'study_group_id', name='uq_task_assignment_group'),
    )
    op.create_index('ix_task_assignments_task_id', 'task_assignments', ['task_id'])
    op.create_index('ix_task_assignments_study_group_id', 'task_assignments', ['study_group_id'])
    op.create_table(
        'task_rows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('task_assignments.id'), nullable=False),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('is_included', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('values_json', sa.Text(), nullable=False),
        sa.UniqueConstraint('assignment_id', 'student_id', name='uq_task_row_student'),
    )
    op.create_index('ix_task_rows_assignment_id', 'task_rows', ['assignment_id'])
    op.create_table(
        'task_comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('task_assignments.id'), nullable=False),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_task_comments_assignment_id', 'task_comments', ['assignment_id'])


def downgrade() -> None:
    op.drop_table('task_comments')
    op.drop_table('task_rows')
    op.drop_table('task_assignments')
    op.drop_table('tasks')
