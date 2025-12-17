"""
응답 모델 정의
API 응답 관련 Pydantic 모델
"""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.models.request import IntentType
from app.models.recommendation import (
    BundleRecommendation,
    GiftRecommendation,
    ReviewAnalysis,
    TrendSignal,
    ValueRecommendation,
)


class ClarificationQuestion(BaseModel):
    """추가 질문"""

    question: str = Field(..., description="질문 내용")
    field: str = Field(..., description="관련 필드 (budget, recipient 등)")
    suggestions: List[str] = Field(default_factory=list, description="예시 답변")


class ChatResponse(BaseModel):
    """채팅 응답 (통합)"""

    type: Literal["recommendation", "clarification", "error"] = Field(
        ..., description="응답 유형"
    )
    intent: Optional[IntentType] = Field(None, description="분류된 의도")

    # 추천 결과 (type=recommendation)
    recommendations: Optional[
        Union[
            GiftRecommendation,
            ValueRecommendation,
            BundleRecommendation,
            ReviewAnalysis,
            TrendSignal,
        ]
    ] = Field(None, description="추천 결과")

    # 추가 질문 (type=clarification)
    clarification: Optional[ClarificationQuestion] = Field(None, description="추가 질문")

    # 에러 (type=error)
    error_message: Optional[str] = Field(None, description="에러 메시지")
    fallback_suggestions: List[str] = Field(default_factory=list, description="대체 제안")

    # 메타
    processing_time_ms: int = Field(..., description="처리 시간 (밀리초)")
    cached: bool = Field(default=False, description="캐시 히트 여부")


class ErrorResponse(BaseModel):
    """에러 응답"""

    error: str = Field(..., description="에러 코드")
    message: str = Field(..., description="에러 메시지")
    suggestions: List[str] = Field(default_factory=list, description="대체 제안")
