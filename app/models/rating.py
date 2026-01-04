"""
별점 모델
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


class ProductRating(Base):
    """상품 별점 모델"""

    __tablename__ = "product_ratings"

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
        comment="상품 고유 ID",
    )
    product_name: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    brand: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="평가 시점의 가격",
    )

    # 별점 (1-5)
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="별점 (1-5)",
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
    user = relationship("User", back_populates="ratings")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
        {"comment": "상품 별점 테이블"},
    )

    def __repr__(self) -> str:
        return f"<ProductRating(id={self.id}, rating={self.rating})>"

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "id": str(self.id),
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category": self.category,
            "brand": self.brand,
            "price": self.price,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
