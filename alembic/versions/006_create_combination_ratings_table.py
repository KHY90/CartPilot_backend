"""Create combination ratings table

Revision ID: 006
Revises: 005
Create Date: 2025-01-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 조합 별점 테이블
    op.create_table(
        "combination_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("combination_hash", sa.String(64), nullable=False, index=True,
                  comment="조합 내 상품 ID들의 SHA256 해시"),
        sa.Column("combination_id", sa.String(10), nullable=False,
                  comment="조합 ID (A, B, C)"),
        sa.Column("product_ids", sa.Text(), nullable=False,
                  comment="조합 내 상품 ID 목록 (JSON array)"),
        sa.Column("product_names", sa.Text(), nullable=True,
                  comment="조합 내 상품명 목록 (JSON array)"),
        sa.Column("total_price", sa.Integer(), nullable=True,
                  comment="조합 총 가격"),
        sa.Column("item_categories", sa.Text(), nullable=True,
                  comment="품목 카테고리 목록 (JSON array)"),
        sa.Column("rating", sa.Integer(), nullable=False,
                  comment="별점 (1-5)"),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="check_combination_rating_range"),
        comment="조합 별점 테이블",
    )

    # 유니크 인덱스 (사용자 + 조합 해시)
    op.create_index(
        "ix_combination_ratings_user_hash",
        "combination_ratings",
        ["user_id", "combination_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_combination_ratings_user_hash", table_name="combination_ratings")
    op.drop_table("combination_ratings")
