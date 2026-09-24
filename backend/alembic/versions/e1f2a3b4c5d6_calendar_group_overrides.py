"""calendar group overrides + remote day type

Revision ID: e1f2a3b4c5d6
Revises: d4e8a0c3f6b1
Create Date: 2026-09-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd4e8a0c3f6b1'
branch_labels = None
depends_on = None


_NEW_DAY_TYPE = sa.Enum('STUDY_DAY', 'WEEKEND', 'HOLIDAY', 'VACATION', 'REMOTE', name='daytype')
_OLD_DAY_TYPE = sa.Enum('STUDY_DAY', 'WEEKEND', 'HOLIDAY', 'VACATION', name='daytype')


def upgrade() -> None:
    # Обе операции сделаны переносимыми на повторный запуск: если процесс
    # оборвался между ALTER и CREATE TABLE (например, контейнер убили
    # посреди деплоя) и alembic_version не успел обновиться, следующий
    # upgrade не должен падать на "уже существует" / "уже применено".
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"]: c for c in inspector.get_columns("academic_calendar")}
    day_type_column = columns.get("day_type")
    already_has_remote = bool(
        day_type_column and "REMOTE" in (getattr(day_type_column["type"], "enums", None) or [])
    )
    if not already_has_remote:
        op.alter_column(
            'academic_calendar', 'day_type',
            existing_type=_OLD_DAY_TYPE, type_=_NEW_DAY_TYPE, existing_nullable=False,
        )

    if "academic_calendar_group_override" not in inspector.get_table_names():
        op.create_table(
            'academic_calendar_group_override',
            sa.Column('study_group_id', sa.Integer(), nullable=False),
            sa.Column('date', sa.Date(), nullable=False),
            sa.Column('day_type', _NEW_DAY_TYPE, nullable=False),
            sa.ForeignKeyConstraint(['study_group_id'], ['study_groups.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('study_group_id', 'date'),
        )


def downgrade() -> None:
    op.drop_table('academic_calendar_group_override')
    op.alter_column(
        'academic_calendar', 'day_type',
        existing_type=_NEW_DAY_TYPE, type_=_OLD_DAY_TYPE, existing_nullable=False,
    )
