"""
리뷰 데이터 모델
크롤링된 리뷰 데이터 및 분석 결과 모델
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CrawledReview(BaseModel):
    """크롤링된 개별 리뷰"""

    review_id: str = Field(..., description="리뷰 ID")
    product_id: str = Field(..., description="상품 ID")
    content: str = Field(..., description="리뷰 내용")
    rating: Optional[int] = Field(None, ge=1, le=5, description="별점 (1-5)")
    author: Optional[str] = Field(None, description="작성자 (익명화)")
    date: Optional[str] = Field(None, description="작성일")
    helpful_count: int = Field(default=0, description="도움됨 수")
    purchase_verified: bool = Field(default=False, description="구매 확인 여부")
    source: str = Field(..., description="출처 (naver, coupang 등)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "review_id": "review_123",
                "product_id": "prod_456",
                "content": "배송이 빠르고 제품 품질도 좋습니다.",
                "rating": 5,
                "author": "구매자***",
                "date": "2025-01-05",
                "helpful_count": 12,
                "purchase_verified": True,
                "source": "naver",
            }
        }
    }


class ReviewSentiment(BaseModel):
    """리뷰 감정 분석 결과"""

    review_id: str = Field(..., description="리뷰 ID")
    sentiment: Literal["positive", "negative", "neutral"] = Field(
        ..., description="감정 분류"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도")
    key_phrases: List[str] = Field(default_factory=list, description="핵심 문구")
    aspects: dict = Field(
        default_factory=dict,
        description="측면별 감정 (예: {'품질': 'positive', '배송': 'negative'})",
    )


class ReviewSummary(BaseModel):
    """리뷰 요약 정보"""

    product_id: str = Field(..., description="상품 ID")
    total_reviews: int = Field(..., description="총 리뷰 수")
    average_rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="평균 별점")
    rating_distribution: dict = Field(
        default_factory=dict, description="별점 분포 (예: {'5': 100, '4': 50, ...})"
    )

    # 감정 분포
    positive_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="긍정 비율")
    negative_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="부정 비율")
    neutral_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="중립 비율")

    # 핵심 토픽
    positive_topics: List[str] = Field(
        default_factory=list, description="긍정 키워드 TOP 5"
    )
    negative_topics: List[str] = Field(
        default_factory=list, description="부정 키워드 TOP 5"
    )

    # 대표 리뷰
    representative_positive: Optional[str] = Field(None, description="대표 긍정 리뷰")
    representative_negative: Optional[str] = Field(None, description="대표 부정 리뷰")

    crawled_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="크롤링 시점",
    )


class ProductReviewData(BaseModel):
    """상품별 리뷰 데이터 (캐싱용)"""

    product_id: str = Field(..., description="상품 ID")
    product_title: str = Field(..., description="상품명")
    reviews: List[CrawledReview] = Field(default_factory=list, description="리뷰 목록")
    summary: Optional[ReviewSummary] = Field(None, description="리뷰 요약")
    sentiments: List[ReviewSentiment] = Field(
        default_factory=list, description="감정 분석 결과"
    )
    cached_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="캐시 시점",
    )
    cache_valid_until: str = Field(..., description="캐시 만료 시점")


class CategoryReviewInsights(BaseModel):
    """카테고리별 리뷰 인사이트 (REVIEW 모드용)"""

    category: str = Field(..., description="상품 카테고리")

    # 실제 리뷰 기반 분석
    total_reviews_analyzed: int = Field(default=0, description="분석된 리뷰 수")
    average_satisfaction: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="평균 만족도 (%)"
    )

    # 핵심 인사이트
    common_praises: List[str] = Field(
        default_factory=list, description="자주 언급되는 장점"
    )
    common_complaints: List[str] = Field(
        default_factory=list, description="자주 언급되는 불만"
    )

    # 구매 결정 요소
    purchase_decision_factors: List[str] = Field(
        default_factory=list, description="구매 결정에 영향을 미치는 요소"
    )

    # 실제 사용 후기
    real_user_quotes: List[dict] = Field(
        default_factory=list,
        description="실제 사용자 인용문 (예: [{'quote': '...', 'sentiment': 'positive'}])",
    )

    # 메타 정보
    data_freshness: str = Field(
        default="unknown", description="데이터 신선도 (예: '1일 전')"
    )
    source_breakdown: dict = Field(
        default_factory=dict, description="출처별 리뷰 수 (예: {'naver': 50, 'coupang': 30})"
    )
