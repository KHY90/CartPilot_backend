"""
메인 오케스트레이터
LangGraph 기반 에이전트 흐름 관리
"""
from typing import Any, Dict, Literal

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.agents.analyzer import analyze_request
from app.agents.gift_agent import gift_agent
from app.agents.state import AgentState
from app.models.request import IntentType


def should_clarify(state: AgentState) -> Literal["clarify", "route_to_agent"]:
    """clarification 필요 여부에 따른 라우팅"""
    if state.get("clarification_needed", False):
        return "clarify"
    return "route_to_agent"


def route_by_intent(state: AgentState) -> str:
    """의도에 따른 에이전트 라우팅"""
    intent = state.get("intent")

    if intent == IntentType.GIFT:
        return "gift_agent"
    elif intent == IntentType.VALUE:
        return "value_agent"
    elif intent == IntentType.BUNDLE:
        return "bundle_agent"
    elif intent == IntentType.REVIEW:
        return "review_agent"
    elif intent == IntentType.TREND:
        return "trend_agent"
    else:
        return "value_agent"  # 기본값


async def clarify_node(state: AgentState) -> Dict[str, Any]:
    """Clarification 노드 - 추가 질문 상태 설정"""
    return {
        "processing_step": "awaiting_clarification",
    }


async def placeholder_agent(state: AgentState) -> Dict[str, Any]:
    """플레이스홀더 에이전트 (Phase 3에서 구현)"""
    return {
        "recommendations": None,
        "processing_step": "agent_placeholder",
        "error": "이 모드는 아직 구현 중입니다.",
    }


def create_orchestrator_graph() -> StateGraph:
    """
    오케스트레이터 그래프 생성

    흐름:
    1. analyze_request: 의도 분류 + 요구사항 추출 (단일 LLM 호출)
    2. should_clarify: clarification 필요 여부 체크
       - clarify: 추가 질문 필요 → END
       - route_to_agent: 에이전트로 라우팅
    3. route_by_intent: 의도별 에이전트 실행
    4. END

    Returns:
        컴파일된 StateGraph
    """
    # 그래프 생성
    graph = StateGraph(AgentState)

    # 노드 추가
    graph.add_node("analyze_request", analyze_request)  # 통합 분석 노드
    graph.add_node("clarify", clarify_node)

    # 에이전트 노드
    graph.add_node("gift_agent", gift_agent)  # GIFT 모드
    graph.add_node("value_agent", placeholder_agent)  # VALUE 모드 - Phase 4
    graph.add_node("bundle_agent", placeholder_agent)  # BUNDLE 모드 - Phase 5
    graph.add_node("review_agent", placeholder_agent)  # REVIEW 모드 - Phase 6
    graph.add_node("trend_agent", placeholder_agent)  # TREND 모드 - Phase 7

    # 엣지 설정
    graph.set_entry_point("analyze_request")

    # Clarification 조건부 라우팅
    graph.add_conditional_edges(
        "analyze_request",
        should_clarify,
        {
            "clarify": "clarify",
            "route_to_agent": "route_by_intent",
        },
    )

    # Clarify는 END로
    graph.add_edge("clarify", END)

    # 의도별 라우팅
    graph.add_conditional_edges(
        "route_by_intent",
        route_by_intent,
        {
            "gift_agent": "gift_agent",
            "value_agent": "value_agent",
            "bundle_agent": "bundle_agent",
            "review_agent": "review_agent",
            "trend_agent": "trend_agent",
        },
    )

    # 모든 에이전트는 END로
    graph.add_edge("gift_agent", END)
    graph.add_edge("value_agent", END)
    graph.add_edge("bundle_agent", END)
    graph.add_edge("review_agent", END)
    graph.add_edge("trend_agent", END)

    return graph


# 더미 노드 (route_by_intent는 조건부 라우팅용)
async def route_by_intent_node(state: AgentState) -> Dict[str, Any]:
    """라우팅 결정만 하는 패스스루 노드"""
    return {}


def build_orchestrator():
    """컴파일된 오케스트레이터 반환"""
    graph = create_orchestrator_graph()

    # route_by_intent를 패스스루 노드로 추가
    graph.add_node("route_by_intent", route_by_intent_node)

    # MemorySaver로 대화 히스토리 유지
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# 싱글톤 인스턴스
_orchestrator = None


def get_orchestrator():
    """오케스트레이터 싱글톤 반환"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator
