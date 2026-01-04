"""add kakao token fields to users

Revision ID: 004
Revises: 003
Create Date: 2024-12-25
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 카카오 액세스 토큰 (나에게 보내기 기능용)
    op.add_column(
        "users",
        sa.Column(
            "kakao_access_token",
            sa.String(500),
            nullable=True,
            comment="카카오 액세스 토큰 (나에게 보내기용)",
        ),
    )

    # 카카오 리프레시 토큰
    op.add_column(
        "users",
        sa.Column(
            "kakao_refresh_token",
            sa.String(500),
            nullable=True,
            comment="카카오 리프레시 토큰",
        ),
    )

    # 카카오 토큰 만료 시간
    op.add_column(
        "users",
        sa.Column(
            "kakao_token_expires_at",
            sa.DateTime,
            nullable=True,
            comment="카카오 토큰 만료 시간",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "kakao_token_expires_at")
    op.drop_column("users", "kakao_refresh_token")
    op.drop_column("users", "kakao_access_token")
