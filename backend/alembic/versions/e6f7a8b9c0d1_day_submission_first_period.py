"""day_submissions.first_period — к какой паре группа пришла в этот день
(выставляет куратор при сдаче дня, нужна для свода «всего / к 1 паре»)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("day_submissions")}
    if "first_period" not in columns:
        op.add_column("day_submissions", sa.Column("first_period", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("day_submissions", "first_period")
