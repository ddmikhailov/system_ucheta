"""мероприятия плана воспитательной работы группы и присутствовавшие (этап 9)

Revision ID: r9a0b1c2d3e4
Revises: q8f9a0b1c2d3
Create Date: 2026-10-06 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'r9a0b1c2d3e4'
down_revision = 'q8f9a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'group_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('school_year', sa.String(length=9), nullable=False),
        sa.Column('section', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=True),
        sa.Column('time_text', sa.String(length=32), nullable=True),
        sa.Column('responsible', sa.String(length=255), nullable=True),
        sa.Column('goal', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='planned'),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('is_class_hour', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_group_events_study_group_id', 'group_events', ['study_group_id'])
    op.create_index('ix_group_events_school_year', 'group_events', ['school_year'])
    op.create_table(
        'group_event_attendees',
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('group_events.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('group_event_attendees')
    op.drop_index('ix_group_events_school_year', table_name='group_events')
    op.drop_index('ix_group_events_study_group_id', table_name='group_events')
    op.drop_table('group_events')
