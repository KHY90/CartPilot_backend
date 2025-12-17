"""
채팅 엔드포인트
사용자 메시지 처리 및 추천 응답 반환
"""
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.orchestrator import get_orchestrator
from app.models.request import IntentType
from app.models.response import ChatResponse, ClarificationQuestion
from app.services.session_store import get_session_store

router = APIRouter()


class ChatRequest(BaseModel):
    """채팅 요청"""

    message: str = Field(..., min_length=1, max_length=500, description="사용자 메시지")
    session_id: Optional[str] = Field(None, description="세션 ID (없으면 자동 생성)")


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(request: ChatRequest) -> ChatResponse:
    """
    채팅 메시지 처리

    사용자 메시지를 받아 의도를 분류하고 적절한 추천을 반환합니다.
    - 8초 이내 응답 목표
    - 캐시 히트 시 1초 이내 응답

    Args:
        request: 채팅 요청 (메시지, 세션 ID)

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

        # 오케스트레이터 실행
        orchestrator = get_orchestrator()

        initial_state = {
            "raw_query": request.message,
            "session_id": session.session_id,
            "intent": None,
            "intent_confidence": 0.0,
            "secondary_intents": [],
            "requirements": None,
            "search_results": [],
            "recommendations": None,
            "clarification_needed": False,
            "clarification_question": None,
            "clarification_field": None,
            "error": None,
            "messages": [],
            "processing_step": "started",
            "cached": False,
        }

        # 그래프 실행
        result = await orchestrator.ainvoke(initial_state)

        # 처리 시간 계산
        processing_time_ms = int((time.time() - start_time) * 1000)

        # 응답 생성
        if result.get("clarification_needed"):
            # 추가 질문 필요
            return ChatResponse(
                type="clarification",
                intent=result.get("intent"),
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
