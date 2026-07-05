"""Этап 2: инфоповоды, версии по каналам, чек-лист, комментарии,
поля планирования публикации у статей.

Revision ID: 0002_stage2
Revises: 0001_stage1
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_stage2"
down_revision = "0001_stage1"
branch_labels = None
depends_on = None

infoeventstatus = sa.Enum("new", "in_progress", "topic_created", "rejected",
                          "archived", name="infoeventstatus")
importance = sa.Enum("low", "medium", "high", name="importance")
versionchannel = sa.Enum("site", "dzen", "vk", "telegram", "markdown",
                         name="versionchannel")
versionstatus = sa.Enum("draft", "ready", "published", name="versionstatus")


def upgrade() -> None:
    # --- Инфоповоды (11.5) ---
    op.create_table(
        "info_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_id", sa.Integer(),
                  sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("direction", sa.String(255), nullable=True),
        sa.Column("importance", importance, nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("links", sa.Text(), nullable=True),
        sa.Column("why_important", sa.Text(), nullable=True),
        sa.Column("related_services", sa.Text(), nullable=True),
        sa.Column("suggested_titles", sa.Text(), nullable=True),
        sa.Column("status", infoeventstatus, nullable=False),
        sa.Column("responsible_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Тема помнит исходный инфоповод ---
    op.add_column("topics", sa.Column("info_event_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_topics_info_event", "topics", "info_events",
                          ["info_event_id"], ["id"], ondelete="SET NULL")

    # --- Новые поля статьи: редактор 11.7 и планирование 11.8 ---
    op.add_column("articles", sa.Column("faq", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("cta", sa.String(1000), nullable=True))
    op.add_column("articles", sa.Column("internal_links", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("sources_list", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("effecom_block", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("planned_at",
                  sa.DateTime(timezone=True), nullable=True))
    op.add_column("articles", sa.Column("review_deadline",
                  sa.DateTime(timezone=True), nullable=True))
    op.add_column("articles", sa.Column("published_at",
                  sa.DateTime(timezone=True), nullable=True))

    # --- Версии по каналам (6.8) ---
    op.create_table(
        "article_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(),
                  sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", versionchannel, nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", versionstatus, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "channel", name="uq_article_channel"),
    )
    op.create_index("ix_article_versions_article_id",
                    "article_versions", ["article_id"])

    # --- Чек-лист качества (6.9) ---
    op.create_table(
        "article_checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(),
                  sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "key", name="uq_article_checklist_key"),
    )
    op.create_index("ix_article_checklist_items_article_id",
                    "article_checklist_items", ["article_id"])

    # --- Комментарии (11.7.5) ---
    op.create_table(
        "article_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(),
                  sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("author_role", sa.String(50), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_article_comments_article_id",
                    "article_comments", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_article_comments_article_id", table_name="article_comments")
    op.drop_table("article_comments")
    op.drop_index("ix_article_checklist_items_article_id",
                  table_name="article_checklist_items")
    op.drop_table("article_checklist_items")
    op.drop_index("ix_article_versions_article_id", table_name="article_versions")
    op.drop_table("article_versions")
    for col in ("published_at", "review_deadline", "planned_at", "effecom_block",
                "sources_list", "internal_links", "cta", "faq"):
        op.drop_column("articles", col)
    op.drop_constraint("fk_topics_info_event", "topics", type_="foreignkey")
    op.drop_column("topics", "info_event_id")
    op.drop_table("info_events")
    bind = op.get_bind()
    for enum in (versionstatus, versionchannel, importance, infoeventstatus):
        enum.drop(bind, checkfirst=True)
