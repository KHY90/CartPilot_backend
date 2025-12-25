"""create purchase_records table

Revision ID: 003
Revises: 002
Create Date: 2024-12-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        # 상품 정보
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("category", sa.String(100), nullable=True, comment="상품 카테고리"),
        sa.Column("mall_name", sa.String(100), nullable=True),
        # 구매 정보
        sa.Column("price", sa.Integer, nullable=False, comment="구매 가격"),
        sa.Column("quantity", sa.Integer, default=1, comment="구매 수량"),
        sa.Column("purchased_at", sa.DateTime, nullable=False, comment="구매 일시"),
        # 메모
        sa.Column("notes", sa.Text, nullable=True, comment="구매 메모"),
        # 메타데이터
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        comment="구매 기록 테이블",
    )

    # 인덱스 추가
    op.create_index("ix_purchase_records_purchased_at", "purchase_records", ["purchased_at"])
    op.create_index("ix_purchase_records_category", "purchase_records", ["category"])


def downgrade() -> None:
    op.drop_index("ix_purchase_records_category")
    op.drop_index("ix_purchase_records_purchased_at")
    op.drop_table("purchase_records")
