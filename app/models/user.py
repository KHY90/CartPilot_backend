"""
사용자 모델
소셜 로그인(카카오, 네이버) 기반 인증
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base

if TYPE_CHECKING:
    from app.models.wishlist import WishlistItem
    from app.models.rating import ProductRating


class User(Base):
    """사용자 모델"""

    __tablename__ = "users"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # 기본 정보
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    profile_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 소셜 로그인 정보
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="소셜 로그인 제공자: kakao, naver",
    )
    provider_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="소셜 계정 고유 ID",
    )

    # 알림용 정보
    kakao_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="카카오 사용자 ID",
    )
    kakao_access_token: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="카카오 액세스 토큰 (나에게 보내기용)",
    )
    kakao_refresh_token: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="카카오 리프레시 토큰",
    )
    kakao_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="카카오 토큰 만료 시간",
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="전화번호",
    )
    notification_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="알림 수신용 이메일",
    )

    # 알림 설정
    kakao_notification_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="카카오 알림 활성화",
    )
    email_notification_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="이메일 알림 활성화",
    )

    # 메타데이터
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    # 관계 정의
    wishlist_items: Mapped[list["WishlistItem"]] = relationship(
        "WishlistItem", back_populates="user", cascade="all, delete-orphan"
    )
    ratings: Mapped[list["ProductRating"]] = relationship(
        "ProductRating", back_populates="user", cascade="all, delete-orphan"
    )

    # 복합 유니크 제약 (provider + provider_id)
    __table_args__ = (
        {"comment": "사용자 테이블 - 소셜 로그인 기반"},
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, provider={self.provider})>"

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (API 응답용)"""
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "profile_image": self.profile_image,
            "provider": self.provider,
            "kakao_notification_enabled": self.kakao_notification_enabled,
            "email_notification_enabled": self.email_notification_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
