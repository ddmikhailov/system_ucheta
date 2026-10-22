"""надёжность и обратная связь: индекс журнала действий по объекту, «Что нового» просмотрено пользователем

Revision ID: r1a2b3c4d5e6
Revises: z7c1m2p3n4s5
Create Date: 2026-10-21 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'r1a2b3c4d5e6'
down_revision = 'z7c1m2p3n4s5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Обезличивание (redact_audit_history) и фильтры по объекту шли полным перебором журнала.
    op.create_index('ix_audit_log_entity', 'audit_log', ['entity_type', 'entity_id'])
    # Версия, чью плашку «Что нового» пользователь уже закрыл (одна на все его устройства).
    op.add_column('users', sa.Column('seen_release', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'seen_release')
    op.drop_index('ix_audit_log_entity', table_name='audit_log')
