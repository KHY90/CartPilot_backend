"""
구매 기록 모델
수동 입력 기반 구매 이력 추적
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


class PurchaseRecord(Base):
    """구매 기록 모델"""

    __tablename__ = "purchase_records"

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
    product_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="상품 카테고리",
    )
    mall_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # 구매 정보
    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="구매 가격",
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="구매 수량",
    )
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="구매 일시",
    )

    # 메모
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="구매 메모",
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
    user = relationship("User", backref="purchases")

    __table_args__ = ({"comment": "구매 기록 테이블"},)

    def __repr__(self) -> str:
        return f"<PurchaseRecord(id={self.id}, product_name={self.product_name})>"

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "id": str(self.id),
            "product_name": self.product_name,
            "category": self.category,
            "mall_name": self.mall_name,
            "price": self.price,
            "quantity": self.quantity,
            "purchased_at": self.purchased_at.isoformat() if self.purchased_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
