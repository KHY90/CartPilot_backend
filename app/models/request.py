"""
요청 모델 정의
사용자 요청 및 요구사항 관련 Pydantic 모델
"""
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """의도 유형"""

    GIFT = "GIFT"  # 선물 추천
    VALUE = "VALUE"  # 가성비 비교
    BUNDLE = "BUNDLE"  # 묶음 구매
    REVIEW = "REVIEW"  # 리뷰 검증
    TREND = "TREND"  # 트렌드 추천


class UserRequest(BaseModel):
    """사용자 요청 모델"""

    raw_query: str = Field(..., description="원문 쿼리", min_length=1, max_length=500)
    intent: IntentType = Field(..., description="분류된 의도")
    intent_confidence: float = Field(..., ge=0.0, le=1.0, description="의도 분류 신뢰도")
    secondary_intents: List[IntentType] = Field(default_factory=list, description="부가 의도")
    session_id: str = Field(..., description="세션 ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "raw_query": "30대 남자 동료 퇴사 선물 5만원",
                "intent": "GIFT",
                "intent_confidence": 0.95,
                "secondary_intents": [],
                "session_id": "sess_abc123",
            }
        }
    }


class BudgetRange(BaseModel):
    """예산 범위"""

    min_price: Optional[int] = Field(None, ge=0, description="최소 예산 (원)")
    max_price: Optional[int] = Field(None, ge=0, description="최대 예산 (원)")
    total_budget: Optional[int] = Field(None, ge=0, description="총 예산 (BUNDLE용)")
    is_flexible: bool = Field(default=True, description="예산 유연성")


class RecipientInfo(BaseModel):
    """선물 대상 정보 (GIFT 모드용)"""

    relation: Optional[str] = Field(None, description="관계 (친구, 동료, 상사 등)")
    gender: Optional[Literal["male", "female", "unknown"]] = Field(None, description="성별")
    age_group: Optional[str] = Field(None, description="연령대 (20대, 30대 등)")
    occasion: Optional[str] = Field(None, description="상황 (생일, 퇴사 등)")


class Constraints(BaseModel):
    """제약 조건"""

    exclude_brands: List[str] = Field(default_factory=list, description="제외할 브랜드")
    delivery_deadline: Optional[str] = Field(None, description="배송 기한")
    exclude_used: bool = Field(default=True, description="중고 제외")
    exclude_rental: bool = Field(default=True, description="렌탈 제외")
    exclude_overseas: bool = Field(default=True, description="해외직구 제외")


class Requirements(BaseModel):
    """추출된 요구사항"""

    budget: Optional[BudgetRange] = Field(None, description="예산 정보")
    items: List[str] = Field(default_factory=list, description="품목/카테고리 목록")
    recipient: Optional[RecipientInfo] = Field(None, description="선물 대상 정보")
    constraints: Constraints = Field(default_factory=Constraints)

    # 추가 질문 관련
    missing_fields: List[str] = Field(default_factory=list, description="누락된 필수 필드")
    clarify_count: int = Field(default=0, ge=0, le=2, description="추가 질문 횟수")

    model_config = {
        "json_schema_extra": {
            "example": {
                "budget": {"min_price": 40000, "max_price": 60000, "is_flexible": True},
                "items": ["선물"],
                "recipient": {
                    "relation": "colleague",
                    "gender": "male",
                    "age_group": "30대",
                    "occasion": "farewell",
                },
                "constraints": {"exclude_used": True, "exclude_rental": True},
            }
        }
    }
