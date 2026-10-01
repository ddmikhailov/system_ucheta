"""удаление Telegram-бота: таблицы telegram_link_tokens и notification_log,
поля users.telegram_chat_id / telegram_linked_at / receives_leadership_digest

Данные из этих таблиц и полей (привязки чатов, журнал рассылок) удаляются
безвозвратно — Telegram-интеграции в платформе больше нет. Downgrade
возвращает только структуру (пустую), не данные.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-01 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = set(inspector.get_table_names())
    for table in ("telegram_link_tokens", "notification_log"):
        if table in existing_tables:
            op.drop_table(table)

    # В MySQL уникальный индекс по telegram_chat_id исчезает вместе с колонкой.
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    for column in ("telegram_chat_id", "telegram_linked_at", "receives_leadership_digest"):
        if column in user_columns:
            op.drop_column("users", column)


def downgrade() -> None:
    op.add_column("users", sa.Column("receives_leadership_digest", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("telegram_linked_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
    op.create_unique_constraint("telegram_chat_id", "users", ["telegram_chat_id"])

    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "date", name="uq_notification_once"),
    )
