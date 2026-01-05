"""
조합 별점 모델
묶음 구매 조합에 대한 사용자 평가
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import hashlib
import json

from app.database import Base


class CombinationRating(Base):
    """조합 별점 모델"""

    __tablename__ = "combination_ratings"

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

    # 조합 식별자 (상품 ID들의 해시)
    combination_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="조합 내 상품 ID들의 SHA256 해시",
    )

    # 조합 정보 (JSON 문자열)
    combination_id: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="조합 ID (A, B, C)",
    )
    product_ids: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="조합 내 상품 ID 목록 (JSON array)",
    )
    product_names: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="조합 내 상품명 목록 (JSON array)",
    )
    total_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="조합 총 가격",
    )
    item_categories: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="품목 카테고리 목록 (JSON array)",
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
    user = relationship("User", back_populates="combination_ratings")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_combination_rating_range"),
        {"comment": "조합 별점 테이블"},
    )

    def __repr__(self) -> str:
        return f"<CombinationRating(id={self.id}, combination_id={self.combination_id}, rating={self.rating})>"

    @staticmethod
    def generate_hash(product_ids: list[str]) -> str:
        """상품 ID 목록으로 조합 해시 생성"""
        # 정렬해서 순서에 관계없이 동일한 해시 생성
        sorted_ids = sorted(product_ids)
        combined = "|".join(sorted_ids)
        return hashlib.sha256(combined.encode()).hexdigest()

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "id": str(self.id),
            "combination_hash": self.combination_hash,
            "combination_id": self.combination_id,
            "product_ids": json.loads(self.product_ids) if self.product_ids else [],
            "product_names": json.loads(self.product_names) if self.product_names else [],
            "total_price": self.total_price,
            "item_categories": json.loads(self.item_categories) if self.item_categories else [],
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
