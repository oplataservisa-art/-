"""Этап 4b: связь темы с найденными материалами.

Единственная новая таблица topic_source_items (join, раздел 9 ТЗ).
Таблицы Этапов 1-4a не изменяются.

Revision ID: 0006_stage4b
Revises: 0005_stage4
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_stage4b"
down_revision = "0005_stage4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_source_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(),
                  sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_item_id", sa.Integer(),
                  sa.ForeignKey("source_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("topic_id", "source_item_id", name="uq_topic_source_item"),
    )
    op.create_index("ix_topic_source_items_topic_id", "topic_source_items", ["topic_id"])
    op.create_index("ix_topic_source_items_source_item_id",
                    "topic_source_items", ["source_item_id"])


def downgrade() -> None:
    op.drop_index("ix_topic_source_items_source_item_id", table_name="topic_source_items")
    op.drop_index("ix_topic_source_items_topic_id", table_name="topic_source_items")
    op.drop_table("topic_source_items")
