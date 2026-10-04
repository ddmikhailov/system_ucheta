"""досье: доп. образование (поле, которое наполняют задачи)

Revision ID: j1e2f3a4b5c6
Revises: i0d1e2f3a4b5
Create Date: 2026-10-04 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'j1e2f3a4b5c6'
down_revision = 'i0d1e2f3a4b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('student_profiles', sa.Column('additional_education', sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column('student_profiles', 'additional_education')
