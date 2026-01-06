"""
가격 예측 모델
단순 추세 분석 기반 가격 예측 결과
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PriceHistoryPoint(BaseModel):
    """가격 이력 포인트"""

    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    price: int = Field(..., description="가격")
    source: str = Field(default="wishlist", description="출처")


class PriceTrend(BaseModel):
    """가격 추세"""

    direction: Literal["up", "down", "stable"] = Field(..., description="추세 방향")
    change_rate: float = Field(..., description="변동률 (%)")
    period_days: int = Field(..., description="분석 기간 (일)")


class UpcomingSale(BaseModel):
    """다가오는 세일 정보"""

    name: str = Field(..., description="세일명")
    start_date: str = Field(..., description="시작일")
    end_date: str = Field(..., description="종료일")
    days_until: int = Field(..., description="D-day")
    expected_discount: int = Field(..., description="예상 할인율 (%)")
    applicable: bool = Field(..., description="해당 상품에 적용 가능 여부")


class PricePrediction(BaseModel):
    """가격 예측 결과"""

    product_id: str = Field(..., description="상품 ID")
    current_price: int = Field(..., description="현재 가격")

    # 추세 분석
    trend: PriceTrend = Field(..., description="가격 추세")
    lowest_price_90d: Optional[int] = Field(None, description="90일 최저가")
    highest_price_90d: Optional[int] = Field(None, description="90일 최고가")

    # 예측
    predicted_price_7d: Optional[int] = Field(None, description="7일 후 예상 가격")
    predicted_price_30d: Optional[int] = Field(None, description="30일 후 예상 가격")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="예측 신뢰도")

    # 세일 정보
    upcoming_sales: List[UpcomingSale] = Field(
        default_factory=list, description="다가오는 세일"
    )
    best_buy_timing: str = Field(
        default="분석 중", description="최적 구매 시점 추천"
    )

    # 구매 추천
    buy_recommendation: Literal["buy_now", "wait", "neutral"] = Field(
        default="neutral", description="구매 추천"
    )
    recommendation_reason: str = Field(
        default="", description="추천 사유"
    )

    # 메타데이터
    analyzed_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="분석 시점",
    )
    history_points: int = Field(default=0, description="분석에 사용된 가격 이력 수")

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_id": "prod_123",
                "current_price": 49900,
                "trend": {
                    "direction": "down",
                    "change_rate": -5.2,
                    "period_days": 30,
                },
                "lowest_price_90d": 45000,
                "highest_price_90d": 55000,
                "predicted_price_7d": 48000,
                "predicted_price_30d": 45000,
                "confidence": 0.7,
                "upcoming_sales": [
                    {
                        "name": "블랙프라이데이",
                        "start_date": "2025-11-20",
                        "end_date": "2025-11-30",
                        "days_until": 15,
                        "expected_discount": 35,
                        "applicable": True,
                    }
                ],
                "best_buy_timing": "15일 후 블랙프라이데이 세일 추천",
                "buy_recommendation": "wait",
                "recommendation_reason": "다가오는 블랙프라이데이에서 35% 할인이 예상됩니다.",
            }
        }
    }


class PredictionSummary(BaseModel):
    """여러 상품의 예측 요약 (관심상품 목록용)"""

    total_products: int = Field(..., description="분석 상품 수")
    buy_now_count: int = Field(default=0, description="지금 구매 추천 수")
    wait_count: int = Field(default=0, description="대기 추천 수")
    neutral_count: int = Field(default=0, description="중립 추천 수")
    next_sale: Optional[UpcomingSale] = Field(None, description="가장 가까운 세일")
    potential_savings: int = Field(default=0, description="예상 절약 금액")
