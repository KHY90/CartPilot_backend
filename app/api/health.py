"""
헬스체크 엔드포인트
서버 및 외부 서비스 상태 확인
"""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.services.session_store import get_session_store

router = APIRouter()


class HealthResponse(BaseModel):
    """헬스체크 응답"""

    status: Literal["healthy", "degraded", "unhealthy"]
    llm_provider: str
    naver_api: Literal["up", "down", "unchecked"]
    active_sessions: int


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    서버 상태 확인

    Returns:
        HealthResponse: 서버 및 외부 서비스 상태
    """
    settings = get_settings()
    session_store = get_session_store()

    # 활성 세션 수 조회
    active_sessions = await session_store.get_active_count()

    # LLM API 키 설정 여부 확인
    llm_configured = False
    if settings.llm_provider == "openai" and settings.openai_api_key:
        llm_configured = True
    elif settings.llm_provider == "gemini" and settings.google_api_key:
        llm_configured = True

    # 네이버 API 설정 여부 확인
    naver_configured = bool(settings.naver_client_id and settings.naver_client_secret)

    # 전체 상태 결정
    if llm_configured and naver_configured:
        status = "healthy"
    elif llm_configured or naver_configured:
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        llm_provider=settings.llm_provider,
        naver_api="up" if naver_configured else "unchecked",
        active_sessions=active_sessions,
    )
