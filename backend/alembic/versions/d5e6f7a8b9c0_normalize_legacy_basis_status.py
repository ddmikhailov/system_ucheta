"""normalize legacy basis_status values (PENDING/OVERDUE were removed from
BasisStatus when the hard confirmation-deadline control was dropped — see
attendance_service.py docstring — but old rows created before that change
still hold those raw values in MySQL's native ENUM column; SQLAlchemy can no
longer deserialize them, so any SELECT touching such a row raises
LookupError). PENDING/OVERDUE both meant "not yet confirmed", which today is
just NOT_REQUIRED (basis_reference presence is what makes it CONFIRMED).

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e6f7a8b9c0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw SQL, не ORM — колонка типизирована как Enum(BasisStatus) и ORM
    # попытается провалидировать/десериализовать старые значения при чтении.
    op.execute(
        sa.text(
            "UPDATE attendance_marks SET basis_status = 'NOT_REQUIRED' "
            "WHERE basis_status IN ('PENDING', 'OVERDUE')"
        )
    )


def downgrade() -> None:
    pass  # необратимая нормализация данных, откатывать нечего
