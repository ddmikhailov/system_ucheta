"""пол студента в досье (по нему склоняются документы: «обучающийся / обучающаяся»)

Revision ID: o6d7e8f9a0b1
Revises: n5c6d7e8f9a0
Create Date: 2026-10-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'o6d7e8f9a0b1'
down_revision = 'n5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('student_profiles', sa.Column('gender', sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column('student_profiles', 'gender')
