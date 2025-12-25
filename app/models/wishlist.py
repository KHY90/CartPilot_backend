"""
관심상품 모델
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


class WishlistItem(Base):
    """관심상품 모델"""

    __tablename__ = "wishlist_items"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # 사용자 연결
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 상품 정보
    product_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="상품 고유 ID (외부 쇼핑몰)",
    )
    product_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    product_image: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    product_link: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    mall_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # 가격 정보
    current_price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="현재 가격",
    )
    target_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="목표 가격 (이 가격 이하일 때 알림)",
    )
    lowest_price_90days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="최근 90일 최저가",
    )

    # 알림 설정
    notification_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="가격 알림 활성화",
    )
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="마지막 알림 발송 시간",
    )

    # 메모
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # 메타데이터
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 관계
    user = relationship("User", back_populates="wishlist_items")
    price_history = relationship(
        "PriceHistory",
        back_populates="wishlist_item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        {"comment": "관심상품 테이블"},
    )

    def __repr__(self) -> str:
        return f"<WishlistItem(id={self.id}, product_name={self.product_name})>"

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "id": str(self.id),
            "product_id": self.product_id,
            "product_name": self.product_name,
            "product_image": self.product_image,
            "product_link": self.product_link,
            "mall_name": self.mall_name,
            "category": self.category,
            "current_price": self.current_price,
            "target_price": self.target_price,
            "lowest_price_90days": self.lowest_price_90days,
            "notification_enabled": self.notification_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PriceHistory(Base):
    """가격 이력 모델"""

    __tablename__ = "price_history"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # 관심상품 연결
    wishlist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlist_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 가격 정보
    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 기록 시간
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )

    # 관계
    wishlist_item = relationship("WishlistItem", back_populates="price_history")

    __table_args__ = (
        {"comment": "가격 이력 테이블"},
    )

    def __repr__(self) -> str:
        return f"<PriceHistory(id={self.id}, price={self.price})>"
