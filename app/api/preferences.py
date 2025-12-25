"""
사용자 성향 API
개인화를 위한 성향 분석 결과 조회
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.preference_analyzer import get_preference_analyzer

router = APIRouter()


# ========== Schemas ==========


class PriceRangeResponse(BaseModel):
    """가격 범위 응답"""

    min: int | None
    max: int | None


class PreferencesResponse(BaseModel):
    """사용자 성향 응답"""

    avg_purchase_price: float | None
    price_range: PriceRangeResponse
    price_sensitivity: str
    preferred_categories: list[str]
    avg_rating: float | None
    high_rated_keywords: list[str]
    purchase_frequency: str
    preferred_malls: list[str]
    data_points: int
    analyzed_at: str | None


class PersonalizedPromptResponse(BaseModel):
    """개인화 프롬프트용 성향 컨텍스트"""

    context: str
    has_data: bool


# ========== Endpoints ==========


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    사용자 성향 분석 결과 조회

    구매 기록, 별점, 관심상품을 분석하여 사용자 성향을 반환합니다.
    """
    analyzer = get_preference_analyzer()
    prefs = await analyzer.analyze(db, str(current_user.id))

    return PreferencesResponse(
        avg_purchase_price=prefs.avg_purchase_price,
        price_range=PriceRangeResponse(
            min=prefs.price_range_min,
            max=prefs.price_range_max,
        ),
        price_sensitivity=prefs.price_sensitivity,
        preferred_categories=prefs.preferred_categories,
        avg_rating=prefs.avg_rating,
        high_rated_keywords=prefs.high_rated_keywords,
        purchase_frequency=prefs.purchase_frequency,
        preferred_malls=prefs.preferred_malls,
        data_points=prefs.data_points,
        analyzed_at=prefs.analyzed_at.isoformat() if prefs.analyzed_at else None,
    )


@router.get("/preferences/prompt-context", response_model=PersonalizedPromptResponse)
async def get_prompt_context(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    LLM 프롬프트용 성향 컨텍스트 조회

    추천 에이전트에서 사용할 수 있는 형식화된 문자열을 반환합니다.
    """
    analyzer = get_preference_analyzer()
    prefs = await analyzer.analyze(db, str(current_user.id))

    return PersonalizedPromptResponse(
        context=prefs.to_prompt_context(),
        has_data=prefs.data_points > 0,
    )
