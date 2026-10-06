"""поля протокола беседы в заметках досье: цель, присутствовавшие, итог

Revision ID: p7e8f9a0b1c2
Revises: o6d7e8f9a0b1
Create Date: 2026-10-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'p7e8f9a0b1c2'
down_revision = 'o6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('student_notes', sa.Column('goal', sa.String(length=500), nullable=True))
    op.add_column('student_notes', sa.Column('participants', sa.Text(), nullable=True))
    op.add_column('student_notes', sa.Column('result', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('student_notes', 'result')
    op.drop_column('student_notes', 'participants')
    op.drop_column('student_notes', 'goal')
