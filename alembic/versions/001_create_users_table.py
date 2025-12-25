"""Create users table

Revision ID: 001
Revises:
Create Date: 2025-12-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=True, index=True),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("profile_image", sa.String(500), nullable=True),
        # 소셜 로그인 정보
        sa.Column(
            "provider",
            sa.String(20),
            nullable=False,
            comment="소셜 로그인 제공자: kakao, naver",
        ),
        sa.Column(
            "provider_id",
            sa.String(100),
            nullable=False,
            comment="소셜 계정 고유 ID",
        ),
        # 알림용 정보
        sa.Column("kakao_id", sa.String(100), nullable=True, comment="카카오 알림톡용 ID"),
        sa.Column("phone", sa.String(20), nullable=True, comment="전화번호 (알림톡용)"),
        sa.Column(
            "notification_email", sa.String(255), nullable=True, comment="알림 수신용 이메일"
        ),
        # 알림 설정
        sa.Column(
            "kakao_notification_enabled",
            sa.Boolean(),
            default=True,
            comment="카카오 알림 활성화",
        ),
        sa.Column(
            "email_notification_enabled",
            sa.Boolean(),
            default=True,
            comment="이메일 알림 활성화",
        ),
        # 메타데이터
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        # 제약 조건
        sa.UniqueConstraint("provider", "provider_id", name="uq_users_provider_provider_id"),
        comment="사용자 테이블 - 소셜 로그인 기반",
    )

    # 인덱스 생성
    op.create_index("ix_users_provider_provider_id", "users", ["provider", "provider_id"])


def downgrade() -> None:
    op.drop_index("ix_users_provider_provider_id", table_name="users")
    op.drop_table("users")
