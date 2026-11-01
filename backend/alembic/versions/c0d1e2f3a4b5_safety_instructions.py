"""журнал инструктажа по охране труда

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-10-29 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c0d1e2f3a4b5'
down_revision = 'b9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'safety_instructions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('school_year', sa.String(length=9), nullable=False),
        sa.Column('instruction_date', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('conducted_by', sa.String(length=200), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_safety_instructions_study_group_id', 'safety_instructions', ['study_group_id'])
    op.create_index('ix_safety_instructions_school_year', 'safety_instructions', ['school_year'])


def downgrade() -> None:
    op.drop_table('safety_instructions')
