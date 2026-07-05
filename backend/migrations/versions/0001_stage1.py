"""Этап 1: users, sources, knowledge_base_items, topics, articles, audit_logs.

Revision ID: 0001_stage1
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_stage1"
down_revision = None
branch_labels = None
depends_on = None

# Имена типов совпадают с теми, что создаёт SQLAlchemy для Enum-колонок
role = sa.Enum("admin", "editor", "expert", "content_manager", "manager", name="role")
sourcetype = sa.Enum("official", "legal_acts", "news", "legal_system", "effecom",
                     "forum", "rss", "manual", "competitor", name="sourcetype")
sourcestatus = sa.Enum("active", "paused", "error", name="sourcestatus")
knowledgetype = sa.Enum("course", "direction", "pricing", "documents", "faq",
                        "advantages", "forbidden_phrases", "brand_style",
                        "legal_limits", "other", name="knowledgetype")
topicstatus = sa.Enum("idea", "needs_brief", "brief_ready", "writing",
                      "article_created", "rejected", "archived", name="topicstatus")
articlestatus = sa.Enum("draft", "needs_revision", "editing", "expert_review",
                        "ready", "scheduled", "published", "publish_error",
                        "archived", name="articlestatus")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sourcetype, nullable=False),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("access_rules", sa.Text(), nullable=True),
        sa.Column("check_frequency", sa.String(50), nullable=False),
        sa.Column("status", sourcestatus, nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responsible_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "knowledge_base_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", knowledgetype, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(500), nullable=True),
        sa.Column("is_actual", sa.Boolean(), nullable=False),
        sa.Column("responsible_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("direction", sa.String(255), nullable=True),
        sa.Column("audience", sa.String(255), nullable=True),
        sa.Column("intent", sa.String(255), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", topicstatus, nullable=False),
        sa.Column("cta", sa.String(500), nullable=True),
        sa.Column("source_id", sa.Integer(),
                  sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("responsible_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(),
                  sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("channel", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("slug", sa.String(500), nullable=True),
        sa.Column("seo_title", sa.String(500), nullable=True),
        sa.Column("seo_description", sa.String(1000), nullable=True),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("status", articlestatus, nullable=False),
        sa.Column("responsible_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("articles")
    op.drop_table("topics")
    op.drop_table("knowledge_base_items")
    op.drop_table("sources")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    bind = op.get_bind()
    for enum in (articlestatus, topicstatus, knowledgetype,
                 sourcestatus, sourcetype, role):
        enum.drop(bind, checkfirst=True)
