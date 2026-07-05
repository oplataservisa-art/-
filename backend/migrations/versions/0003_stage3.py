"""Этап 3: промпты, версии промптов, журнал AI-запросов.

Таблицы Этапов 1-2 не изменяются.

Revision ID: 0003_stage3
Revises: 0002_stage2
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_stage3"
down_revision = "0002_stage2"
branch_labels = None
depends_on = None

airequeststatus = sa.Enum("ok", "error", "budget_denied", name="airequeststatus")


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=True),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("variables", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prompts_key", "prompts", ["key"], unique=True)

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prompt_id", sa.Integer(),
                  sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),
    )
    op.create_index("ix_prompt_versions_prompt_id", "prompt_versions", ["prompt_id"])

    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("prompt_key", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("article_id", sa.Integer(),
                  sa.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topic_id", sa.Integer(),
                  sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("status", airequeststatus, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_requests_created_at", "ai_requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_requests_created_at", table_name="ai_requests")
    op.drop_table("ai_requests")
    op.drop_index("ix_prompt_versions_prompt_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompts_key", table_name="prompts")
    op.drop_table("prompts")
    airequeststatus.drop(op.get_bind(), checkfirst=True)
