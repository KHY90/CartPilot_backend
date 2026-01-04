"""Create wishlist and rating tables

Revision ID: 002
Revises: 001
Create Date: 2025-12-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 관심상품 테이블
    op.create_table(
        "wishlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("product_id", sa.String(50), nullable=False),
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("product_image", sa.String(500), nullable=True),
        sa.Column("product_link", sa.String(1000), nullable=True),
        sa.Column("mall_name", sa.String(100), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("current_price", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Integer(), nullable=True),
        sa.Column("lowest_price_90days", sa.Integer(), nullable=True),
        sa.Column("notification_enabled", sa.Boolean(), default=True),
        sa.Column("last_notified_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        comment="관심상품 테이블",
    )

    # 가격 이력 테이블
    op.create_table(
        "price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wishlist_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wishlist_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), default=sa.func.now(), index=True),
        comment="가격 이력 테이블",
    )

    # 별점 테이블
    op.create_table(
        "product_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("product_id", sa.String(50), nullable=False),
        sa.Column("product_name", sa.String(500), nullable=True),
        sa.Column("category", sa.String(100), nullable=True, index=True),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
        comment="상품 별점 테이블",
    )

    # 인덱스
    op.create_index(
        "ix_wishlist_user_product", "wishlist_items", ["user_id", "product_id"], unique=True
    )
    op.create_index(
        "ix_ratings_user_product", "product_ratings", ["user_id", "product_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_ratings_user_product", table_name="product_ratings")
    op.drop_index("ix_wishlist_user_product", table_name="wishlist_items")
    op.drop_table("product_ratings")
    op.drop_table("price_history")
    op.drop_table("wishlist_items")
