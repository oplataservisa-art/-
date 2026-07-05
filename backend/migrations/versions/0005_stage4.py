"""Этап 4a: найденные материалы и история проверок источников.

Только create_table; таблицы Этапов 1-3.2 не изменяются.

Revision ID: 0005_stage4
Revises: 0003_stage3
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_stage4"
down_revision = "0003_stage3"
branch_labels = None
depends_on = None

sourceitemstatus = sa.Enum("new", "reviewed", "info_event_created", "hidden",
                           name="sourceitemstatus")
sourcecheckstatus = sa.Enum("ok", "error", "blocked", name="sourcecheckstatus")


def upgrade() -> None:
    op.create_table(
        "source_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(),
                  sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("excerpt", sa.String(1500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("importance", sa.String(20), nullable=True),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sourceitemstatus, nullable=False),
        sa.Column("info_event_id", sa.Integer(),
                  sa.ForeignKey("info_events.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("source_id", "url", name="uq_source_item_url"),
    )
    op.create_index("ix_source_items_source_id", "source_items", ["source_id"])
    op.create_index("ix_source_items_collected_at", "source_items", ["collected_at"])
    op.create_index("ix_source_items_content_hash", "source_items", ["content_hash"])
    op.create_index("ix_source_items_status", "source_items", ["status"])

    op.create_table(
        "source_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(),
                  sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sourcecheckstatus, nullable=False),
        sa.Column("found_new", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=True),
    )
    op.create_index("ix_source_checks_source_id", "source_checks", ["source_id"])
    op.create_index("ix_source_checks_started_at", "source_checks", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_source_checks_started_at", table_name="source_checks")
    op.drop_index("ix_source_checks_source_id", table_name="source_checks")
    op.drop_table("source_checks")
    for ix in ("status", "content_hash", "collected_at", "source_id"):
        op.drop_index(f"ix_source_items_{ix}", table_name="source_items")
    op.drop_table("source_items")
    sourceitemstatus.drop(op.get_bind(), checkfirst=True)
    sourcecheckstatus.drop(op.get_bind(), checkfirst=True)
