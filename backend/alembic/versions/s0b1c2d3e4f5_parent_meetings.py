"""родительские собрания и явка родителей (этап 10)

Revision ID: s0b1c2d3e4f5
Revises: r9a0b1c2d3e4
Create Date: 2026-10-06 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 's0b1c2d3e4f5'
down_revision = 'r9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'parent_meetings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('school_year', sa.String(length=9), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('meeting_date', sa.Date(), nullable=True),
        sa.Column('agenda', sa.Text(), nullable=True),
        sa.Column('staff', sa.Text(), nullable=True),
        sa.Column('speakers', sa.Text(), nullable=True),
        sa.Column('meeting_format', sa.String(length=16), nullable=False, server_default='in_person'),
        sa.Column('parents_count', sa.Integer(), nullable=True),
        sa.Column('listened', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_parent_meetings_study_group_id', 'parent_meetings', ['study_group_id'])
    op.create_index('ix_parent_meetings_school_year', 'parent_meetings', ['school_year'])
    op.create_table(
        'parent_meeting_attendees',
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('parent_meetings.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('guardian_id', sa.Integer(), sa.ForeignKey('student_guardians.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('parent_meeting_attendees')
    op.drop_index('ix_parent_meetings_school_year', table_name='parent_meetings')
    op.drop_index('ix_parent_meetings_study_group_id', table_name='parent_meetings')
    op.drop_table('parent_meetings')
