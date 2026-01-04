"""
LangGraph 에이전트 상태 정의
에이전트 간 공유되는 상태 구조
"""
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage

from app.models.request import IntentType, Requirements
from app.models.product import ProductCandidate


def add_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """메시지 리스트 병합 (reducer)"""
    return left + right


class AgentState(TypedDict):
    """LangGraph 에이전트 상태"""

    # 입력
    raw_query: str
    session_id: str

    # 의도 분류 결과
    intent: Optional[IntentType]
    intent_confidence: float
    secondary_intents: List[IntentType]

    # 요구사항 추출 결과
    requirements: Optional[Requirements]
    search_keywords: List[str]  # LLM이 생성한 검색 키워드

    # 검색 결과
    search_results: List[ProductCandidate]

    # 추천 결과 (모드별로 다른 타입)
    recommendations: Optional[Dict[str, Any]]

    # 추가 질문 (clarification 필요 시)
    clarification_needed: bool
    clarification_question: Optional[str]
    clarification_field: Optional[str]

    # 에러 상태
    error: Optional[str]

    # LangGraph 메시지 (대화 이력)
    messages: Annotated[List[BaseMessage], add_messages]

    # 메타데이터
    processing_step: str
    cached: bool

    # 개인화 (Phase 4)
    user_id: Optional[str]  # 로그인한 사용자 ID
    user_preferences: Optional[str]  # 성향 컨텍스트 문자열
