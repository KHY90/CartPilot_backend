"""
채팅 엔드포인트
사용자 메시지 처리 및 추천 응답 반환
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Depends

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.models.request import IntentType
from app.models.response import ChatResponse, ClarificationQuestion
from app.services.session_store import get_session_store
from app.services.jwt_service import verify_access_token
from app.services.preference_analyzer import get_preference_analyzer
from app.services.cache import get_cache
from app.database import get_db

router = APIRouter()


class ChatRequest(BaseModel):
    """채팅 요청"""

    message: str = Field(..., min_length=1, max_length=500, description="사용자 메시지")
    session_id: Optional[str] = Field(None, description="세션 ID (없으면 자동 생성)")


class CachedProduct(BaseModel):
    """캐시된 상품 정보"""

    product_id: str
    title: str
    price: int
    price_display: str
    mall_name: str
    link: str
    image: Optional[str] = None


class CachedSearchResults(BaseModel):
    """캐시된 검색 결과"""

    session_id: str
    products: list[CachedProduct]


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    채팅 메시지 처리

    사용자 메시지를 받아 의도를 분류하고 적절한 추천을 반환합니다.
    - 8초 이내 응답 목표
    - 캐시 히트 시 1초 이내 응답
    - 로그인 사용자의 경우 개인화 성향 적용

    Args:
        request: 채팅 요청 (메시지, 세션 ID)
        authorization: JWT 토큰 (선택)

    Returns:
        ChatResponse: 추천 결과 또는 추가 질문
    """
    start_time = time.time()

    try:
        # 세션 조회 또는 생성
        session_store = get_session_store()
        session = await session_store.get_or_create_session(request.session_id)

        # 사용자 메시지 세션에 추가
        session.add_user_message(request.message)

        # 사용자 인증 및 성향 로드 (선택적)
        user_id = None
        user_preferences = None

        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            try:
                payload = verify_access_token(token)
                if payload and "user_id" in payload:
                    user_id = payload["user_id"]
                    # 성향 분석
                    analyzer = get_preference_analyzer()
                    prefs = await analyzer.analyze(db, user_id)
                    user_preferences = prefs.to_prompt_context()
            except Exception:
                # 토큰 검증 실패해도 계속 진행 (비로그인 사용자로)
                pass

        # 오케스트레이터 실행
        orchestrator = get_orchestrator()

        # LangGraph MemorySaver용 config (thread_id로 대화 구분)
        config = {"configurable": {"thread_id": session.session_id}}

        initial_state = {
            "raw_query": request.message,
            "session_id": session.session_id,
            "intent": None,
            "intent_confidence": 0.0,
            "secondary_intents": [],
            "requirements": None,
            "search_keywords": [],  # LLM이 생성할 검색 키워드
            "search_results": [],
            "recommendations": None,
            "clarification_needed": False,
            "clarification_question": None,
            "clarification_field": None,
            "error": None,
            "messages": [HumanMessage(content=request.message)],
            "processing_step": "started",
            "cached": False,
            # 개인화 (Phase 4)
            "user_id": user_id,
            "user_preferences": user_preferences,
        }

        # 그래프 실행 (config로 thread_id 전달)
        result = await orchestrator.ainvoke(initial_state, config=config)

        # 처리 시간 계산
        processing_time_ms = int((time.time() - start_time) * 1000)

        # 검색 결과가 있으면 캐시에 저장 (구매 기록 등록용)
        search_results = result.get("search_results", [])
        recommendations = result.get("recommendations")
        cards_data = []

        if recommendations:
            # GiftRecommendation 등의 cards 속성이 있는 경우
            if hasattr(recommendations, "cards") and recommendations.cards:
                cards_data = [
                    {
                        "product_id": card.product_id,
                        "title": card.title,
                        "price": card.price,
                        "price_display": card.price_display,
                        "mall_name": card.mall_name,
                        "link": card.link,
                        "image": card.image,
                    }
                    for card in recommendations.cards
                ]
            # ValueRecommendation의 tier별 cards
            elif hasattr(recommendations, "budget_tier"):
                all_cards = []
                if hasattr(recommendations, "budget_tier") and recommendations.budget_tier:
                    all_cards.extend(recommendations.budget_tier)
                if hasattr(recommendations, "standard_tier") and recommendations.standard_tier:
                    all_cards.extend(recommendations.standard_tier)
                if hasattr(recommendations, "premium_tier") and recommendations.premium_tier:
                    all_cards.extend(recommendations.premium_tier)
                cards_data = [
                    {
                        "product_id": card.product_id,
                        "title": card.title,
                        "price": card.price,
                        "price_display": card.price_display,
                        "mall_name": card.mall_name,
                        "link": card.link,
                        "image": card.image,
                    }
                    for card in all_cards
                ]

        if cards_data:
            cache = get_cache()
            cache_key = f"search_results:{session.session_id}"
            await cache.set(cache_key, cards_data, ttl_seconds=3600)  # 1시간 TTL
            logger.info(f"검색 결과 캐시 저장: {cache_key}, {len(cards_data)}개 상품")
        else:
            logger.debug(f"캐시 저장 스킵: recommendations={bool(recommendations)}")

        # 응답 생성
        if result.get("clarification_needed"):
            # 추가 질문 필요
            return ChatResponse(
                type="clarification",
                intent=result.get("intent"),
                session_id=session.session_id,
                clarification=ClarificationQuestion(
                    question=result.get("clarification_question", "추가 정보가 필요합니다."),
                    field=result.get("clarification_field", "unknown"),
                    suggestions=[],
                ),
                processing_time_ms=processing_time_ms,
                cached=False,
            )

        elif result.get("error"):
            # 에러 발생
            return ChatResponse(
                type="error",
                intent=result.get("intent"),
                session_id=session.session_id,
                error_message=result.get("error"),
                fallback_suggestions=[
                    "다시 시도해 주세요",
                    "좀 더 구체적으로 말씀해 주세요",
                ],
                processing_time_ms=processing_time_ms,
                cached=False,
            )

        else:
            # 추천 결과
            return ChatResponse(
                type="recommendation",
                intent=result.get("intent"),
                session_id=session.session_id,
                recommendations=result.get("recommendations"),
                processing_time_ms=processing_time_ms,
                cached=result.get("cached", False),
            )

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        return ChatResponse(
            type="error",
            error_message=f"처리 중 오류가 발생했습니다: {str(e)}",
            fallback_suggestions=[
                "다시 시도해 주세요",
                "문제가 계속되면 새로고침 해주세요",
            ],
            processing_time_ms=processing_time_ms,
            cached=False,
        )


@router.get("/search-results/{session_id}", response_model=CachedSearchResults)
async def get_cached_search_results(
    session_id: str,
    authorization: Optional[str] = Header(None),
) -> CachedSearchResults:
    """
    캐시된 검색 결과 조회

    최근 검색 결과를 가져와서 구매 기록 등록에 사용할 수 있습니다.
    캐시는 1시간 동안 유효합니다.

    Args:
        session_id: 세션 ID

    Returns:
        CachedSearchResults: 캐시된 상품 목록
    """
    # 인증 확인 (선택적)
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            verify_access_token(token)
        except Exception:
            pass  # 토큰 검증 실패해도 계속 진행

    cache = get_cache()
    cache_key = f"search_results:{session_id}"

    logger.info(f"검색 결과 캐시 조회: {cache_key}")
    cached_data = await cache.get(cache_key)

    if cached_data is None:
        logger.warning(f"검색 결과 캐시 없음: {cache_key}")
        raise HTTPException(
            status_code=404,
            detail="캐시된 검색 결과가 없거나 만료되었습니다."
        )

    products = [CachedProduct(**item) for item in cached_data]
    logger.info(f"검색 결과 캐시 조회 성공: {cache_key}, {len(products)}개 상품")

    return CachedSearchResults(
        session_id=session_id,
        products=products,
    )
