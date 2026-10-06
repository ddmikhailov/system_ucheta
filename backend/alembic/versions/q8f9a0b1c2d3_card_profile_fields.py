"""поля личной карточки в досье: место рождения, образование до поступления, приказ о зачислении

Revision ID: q8f9a0b1c2d3
Revises: p7e8f9a0b1c2
Create Date: 2026-10-06 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'q8f9a0b1c2d3'
down_revision = 'p7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('student_profiles', sa.Column('birth_place', sa.String(length=255), nullable=True))
    op.add_column('student_profiles', sa.Column('previous_education', sa.String(length=500), nullable=True))
    op.add_column('student_profiles', sa.Column('enrollment_order', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('student_profiles', 'enrollment_order')
    op.drop_column('student_profiles', 'previous_education')
    op.drop_column('student_profiles', 'birth_place')
