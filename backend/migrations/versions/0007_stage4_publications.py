"""Этап 4: лог публикаций (таблица publications, §9 и 6.10 ТЗ).

Единственная новая таблица — publications. Существующий тип versionchannel
переиспользуется (create_type=False, чтобы не пересоздавать его), новый тип
publicationstatus создаётся. Таблицы и типы Этапов 1-4b не изменяются.

Revision ID: 0007_stage4_publications
Revises: 0006_stage4b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_stage4_publications"
down_revision = "0006_stage4b"
branch_labels = None
depends_on = None

# Новый тип — создаётся этой миграцией.
publicationstatus = sa.Enum("published", "error", name="publicationstatus")
# Существующий тип — только ссылаемся, не пересоздаём.
versionchannel = postgresql.ENUM(
    "site", "dzen", "vk", "telegram", "markdown",
    name="versionchannel", create_type=False)


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(),
                  sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_version_id", sa.Integer(),
                  sa.ForeignKey("article_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", versionchannel, nullable=False),
        sa.Column("publication_url", sa.String(1000), nullable=True),
        sa.Column("status", publicationstatus, nullable=False, server_default="published"),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publications_article_id", "publications", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_publications_article_id", table_name="publications")
    op.drop_table("publications")
    publicationstatus.drop(op.get_bind(), checkfirst=True)
