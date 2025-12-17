"""
추천 모델 정의
각 모드별 추천 결과 관련 모델
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class RecommendationCard(BaseModel):
    """추천 카드 (공통)"""

    product_id: str = Field(..., description="상품 ID")
    title: str = Field(..., description="상품명")
    image: Optional[HttpUrl] = Field(None, description="이미지 URL")
    price: int = Field(..., description="가격")
    price_display: str = Field(..., description="표시용 가격 (예: '45,000원')")
    mall_name: str = Field(..., description="쇼핑몰")
    link: HttpUrl = Field(..., description="구매 링크")

    # 추천 정보
    recommendation_reason: str = Field(..., description="추천 이유 (2-3문장)")
    warnings: List[str] = Field(default_factory=list, description="주의사항")

    # 선택적 필드 (모드별)
    tier: Optional[Literal["budget", "standard", "premium"]] = Field(
        None, description="가격 티어 (VALUE 모드)"
    )
    tier_benefits: Optional[str] = Field(None, description="이 가격대에서 얻는 것")
    tier_tradeoffs: Optional[str] = Field(None, description="이 가격대에서 포기하는 것")


class GiftRecommendation(BaseModel):
    """GIFT 모드 추천 결과"""

    cards: List[RecommendationCard] = Field(..., min_length=3, max_length=6)
    recipient_summary: str = Field(..., description="받는 분 요약")
    occasion: Optional[str] = Field(None, description="상황")
    budget_range: str = Field(..., description="예산 범위")


class ValueRecommendation(BaseModel):
    """VALUE 모드 추천 결과"""

    budget_tier: List[RecommendationCard] = Field(default_factory=list, description="저가 티어")
    standard_tier: List[RecommendationCard] = Field(
        default_factory=list, description="표준 티어"
    )
    premium_tier: List[RecommendationCard] = Field(
        default_factory=list, description="프리미엄 티어"
    )
    category: str = Field(..., description="상품 카테고리")


class BundleItem(BaseModel):
    """BUNDLE 조합 내 개별 품목"""

    item_category: str = Field(..., description="품목 카테고리 (예: 노트북)")
    product: RecommendationCard = Field(..., description="선택된 상품")
    alternatives: List[RecommendationCard] = Field(
        default_factory=list, max_length=2, description="대체 옵션"
    )


class BundleCombination(BaseModel):
    """BUNDLE 조합"""

    combination_id: str = Field(..., description="조합 ID (A, B, C)")
    items: List[BundleItem] = Field(..., min_length=2)
    total_price: int = Field(..., description="총액")
    total_display: str = Field(..., description="표시용 총액")
    budget_fit: bool = Field(..., description="예산 내 여부")
    adjustment_note: Optional[str] = Field(None, description="예산 조정 시 변경 내용")


class BundleRecommendation(BaseModel):
    """BUNDLE 모드 추천 결과"""

    combinations: List[BundleCombination] = Field(..., min_length=2, max_length=3)
    total_budget: int = Field(..., description="사용자 총 예산")
    items_count: int = Field(..., description="품목 수")


class ReviewComplaint(BaseModel):
    """반복 불만 항목"""

    rank: int = Field(..., ge=1, le=10, description="순위")
    issue: str = Field(..., description="불만 내용")
    frequency: str = Field(..., description="빈도 (예: '많음', '보통')")
    severity: Literal["low", "medium", "high"] = Field(..., description="심각도")


class ReviewAnalysis(BaseModel):
    """REVIEW 모드 분석 결과"""

    product_category: str = Field(..., description="상품 카테고리")
    top_complaints: List[ReviewComplaint] = Field(
        ..., min_length=1, max_length=5, description="반복 불만 TOP 3-5"
    )
    not_recommended_conditions: List[str] = Field(
        default_factory=list, description="비추천 조건들"
    )
    management_tips: List[str] = Field(default_factory=list, description="관리/사용 팁")
    overall_sentiment: Literal["positive", "mixed", "negative"] = Field(
        ..., description="전반적 평가"
    )
    disclaimer: str = Field(
        default="후기는 주관적이며 표본 편향이 있을 수 있습니다.", description="면책 조항"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_category": "에어프라이어",
                "top_complaints": [
                    {"rank": 1, "issue": "세척 어려움", "frequency": "많음", "severity": "medium"},
                    {"rank": 2, "issue": "소음", "frequency": "보통", "severity": "low"},
                    {"rank": 3, "issue": "용량 작음", "frequency": "보통", "severity": "medium"},
                ],
                "not_recommended_conditions": [
                    "1인 가구가 아닌 4인 이상 가족",
                    "기름진 요리를 자주 하는 경우",
                ],
                "management_tips": [
                    "사용 직후 뜨거울 때 내부 닦으면 쉽게 세척됨",
                    "종이호일 사용하면 세척이 편함",
                ],
                "overall_sentiment": "positive",
            }
        }
    }


class TrendingItem(BaseModel):
    """트렌드 상품"""

    category: str = Field(..., description="카테고리")
    keyword: str = Field(..., description="트렌드 키워드")
    growth_rate: Optional[str] = Field(None, description="상승률 (예: '+50%')")
    period: str = Field(..., description="기간 (예: '최근 1개월')")
    target_segment: Optional[str] = Field(None, description="주요 구매층")
    products: List[RecommendationCard] = Field(default_factory=list)


class TrendSignal(BaseModel):
    """TREND 모드 결과"""

    trending_items: List[TrendingItem] = Field(..., min_length=1, max_length=5)
    data_source: str = Field(default="네이버 데이터랩", description="데이터 출처")
    generated_at: str = Field(..., description="생성 시점")
    disclaimer: str = Field(
        default="인기 상품 ≠ 최저가. 트렌드는 빠르게 변할 수 있습니다.", description="면책 조항"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "trending_items": [
                    {
                        "category": "가전",
                        "keyword": "미니 가습기",
                        "growth_rate": "+120%",
                        "period": "최근 2주",
                        "target_segment": "20-30대 직장인",
                        "products": [],
                    }
                ],
                "data_source": "네이버 데이터랩",
                "generated_at": "2025-12-17T10:00:00Z",
            }
        }
    }
