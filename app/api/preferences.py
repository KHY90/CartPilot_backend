"""
사용자 성향 API
개인화를 위한 성향 분석 결과 조회 + 알림 설정
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.preference_analyzer import get_preference_analyzer
from app.services.notifications.email_service import get_email_service

logger = logging.getLogger(__name__)

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


# ========== 당신의 취향 Schemas ==========


class TasteInsight(BaseModel):
    """개별 취향 인사이트"""

    icon: str
    label: str
    value: str
    description: str | None = None


class YourTasteResponse(BaseModel):
    """당신의 취향 응답"""

    has_data: bool
    insights: list[TasteInsight]
    summary: str
    data_points: int
    last_updated: str | None


@router.get("/preferences/your-taste", response_model=YourTasteResponse)
async def get_your_taste(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    "당신의 취향" 인사이트 조회

    사용자 친화적인 취향 분석 결과를 반환합니다.
    프론트엔드의 개인화 섹션 표시용입니다.
    """
    analyzer = get_preference_analyzer()
    prefs = await analyzer.analyze(db, str(current_user.id))

    if prefs.data_points == 0:
        return YourTasteResponse(
            has_data=False,
            insights=[],
            summary="구매 기록이나 별점 데이터가 아직 없어요. 상품을 탐색하고 평가해 보세요!",
            data_points=0,
            last_updated=None,
        )

    insights: list[TasteInsight] = []

    # 가격대 인사이트
    if prefs.avg_purchase_price:
        price_label = (
            "저가 선호" if prefs.price_sensitivity == "high"
            else "프리미엄 선호" if prefs.price_sensitivity == "low"
            else "균형 잡힌 소비"
        )
        insights.append(
            TasteInsight(
                icon="💰",
                label="가격 성향",
                value=price_label,
                description=f"평균 {int(prefs.avg_purchase_price):,}원대 구매"
            )
        )

    # 카테고리 인사이트
    if prefs.preferred_categories:
        top_cat = prefs.preferred_categories[0]
        insights.append(
            TasteInsight(
                icon="🏷️",
                label="관심 카테고리",
                value=top_cat,
                description=f"외 {len(prefs.preferred_categories) - 1}개 카테고리" if len(prefs.preferred_categories) > 1 else None
            )
        )

    # 구매 빈도 인사이트
    freq_labels = {"high": "활발한 쇼핑러", "medium": "신중한 구매자", "low": "선택적 소비자"}
    insights.append(
        TasteInsight(
            icon="🛒",
            label="구매 패턴",
            value=freq_labels.get(prefs.purchase_frequency, "보통"),
            description=None
        )
    )

    # 선호 쇼핑몰 인사이트
    if prefs.preferred_malls:
        insights.append(
            TasteInsight(
                icon="🏪",
                label="선호 쇼핑몰",
                value=prefs.preferred_malls[0],
                description=f"외 {len(prefs.preferred_malls) - 1}곳" if len(prefs.preferred_malls) > 1 else None
            )
        )

    # 높게 평가한 키워드
    if prefs.high_rated_keywords:
        insights.append(
            TasteInsight(
                icon="⭐",
                label="높게 평가한 유형",
                value=", ".join(prefs.high_rated_keywords[:3]),
                description=None
            )
        )

    # 요약 생성
    summary_parts = []
    if prefs.preferred_categories:
        summary_parts.append(f"{prefs.preferred_categories[0]}을(를) 좋아하시는군요")
    if prefs.price_sensitivity == "high":
        summary_parts.append("가성비를 중시하시네요")
    elif prefs.price_sensitivity == "low":
        summary_parts.append("품질을 중시하시네요")

    summary = "! ".join(summary_parts) + "!" if summary_parts else "취향 분석 완료!"

    return YourTasteResponse(
        has_data=True,
        insights=insights,
        summary=summary,
        data_points=prefs.data_points,
        last_updated=prefs.analyzed_at.isoformat() if prefs.analyzed_at else None,
    )


# ========== 알림 설정 Schemas ==========


class NotificationSettingsResponse(BaseModel):
    """알림 설정 응답"""

    email_notification_enabled: bool
    notification_email: Optional[str]


class NotificationSettingsUpdate(BaseModel):
    """알림 설정 수정 요청"""

    email_notification_enabled: Optional[bool] = None
    notification_email: Optional[str] = None


# ========== 알림 설정 Endpoints ==========


@router.get("/notification-settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
):
    """
    알림 설정 조회

    이메일 알림 활성화 여부와 알림 수신 이메일을 반환합니다.
    """
    return NotificationSettingsResponse(
        email_notification_enabled=current_user.email_notification_enabled,
        notification_email=current_user.notification_email,
    )


@router.put("/notification-settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    request: NotificationSettingsUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    알림 설정 수정

    이메일 알림 활성화 여부와 알림 수신 이메일을 수정합니다.
    새 이메일 설정 시 환영 이메일을 발송합니다.
    """
    # 이메일이 새로 설정되었는지 확인
    old_email = current_user.notification_email
    new_email = request.notification_email

    if request.email_notification_enabled is not None:
        current_user.email_notification_enabled = request.email_notification_enabled

    if new_email is not None:
        current_user.notification_email = new_email

    await db.commit()
    await db.refresh(current_user)

    # 새 이메일이 설정되고 알림이 활성화된 경우 환영 이메일 발송
    if (
        new_email
        and new_email != old_email
        and current_user.email_notification_enabled
    ):
        email_service = get_email_service()
        if email_service.is_available():
            # 백그라운드에서 이메일 발송 (응답 지연 방지)
            async def send_welcome():
                success = await email_service.send_welcome_notification(new_email)
                if success:
                    logger.info(f"환영 이메일 발송 성공: {new_email}")
                else:
                    logger.warning(f"환영 이메일 발송 실패: {new_email}")

            background_tasks.add_task(send_welcome)

    return NotificationSettingsResponse(
        email_notification_enabled=current_user.email_notification_enabled,
        notification_email=current_user.notification_email,
    )
