"""Add alert condition fields to wishlist_items

Revision ID: 005
Revises: 004
Create Date: 2025-01-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 알림 조건 필드 추가
    op.add_column(
        "wishlist_items",
        sa.Column(
            "alert_on_lowest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="90일 최저가 도달 시 알림",
        ),
    )
    op.add_column(
        "wishlist_items",
        sa.Column(
            "alert_on_target",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="목표가 도달 시 알림",
        ),
    )
    op.add_column(
        "wishlist_items",
        sa.Column(
            "alert_on_drop_percent",
            sa.Integer(),
            nullable=True,
            comment="N% 이상 하락 시 알림",
        ),
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "alert_on_drop_percent")
    op.drop_column("wishlist_items", "alert_on_target")
    op.drop_column("wishlist_items", "alert_on_lowest")
