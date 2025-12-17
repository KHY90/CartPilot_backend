"""
요구사항 추출 노드
사용자 입력에서 예산, 품목, 수신자 정보 등을 추출
"""
from typing import Any, Dict, List

from app.agents.state import AgentState
from app.models.request import Constraints, Requirements
from app.utils.text_parser import parse_user_input


def get_missing_fields(requirements: Requirements, intent_str: str) -> List[str]:
    """의도에 따라 필수 필드 누락 여부 확인"""
    missing = []

    if intent_str == "GIFT":
        # GIFT 모드: 수신자 정보와 예산 필요
        if not requirements.recipient:
            missing.append("recipient")
        elif not requirements.recipient.relation:
            missing.append("recipient.relation")
        if not requirements.budget:
            missing.append("budget")

    elif intent_str == "VALUE":
        # VALUE 모드: 품목 필요
        if not requirements.items:
            missing.append("items")

    elif intent_str == "BUNDLE":
        # BUNDLE 모드: 여러 품목과 총 예산 필요
        if not requirements.items or len(requirements.items) < 2:
            missing.append("items")
        if not requirements.budget or not requirements.budget.total_budget:
            missing.append("budget.total_budget")

    elif intent_str == "REVIEW":
        # REVIEW 모드: 품목 필요
        if not requirements.items:
            missing.append("items")

    # TREND는 특별한 필수 필드 없음

    return missing


async def extract_requirements(state: AgentState) -> Dict[str, Any]:
    """
    요구사항 추출 노드

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 상태 딕셔너리
    """
    # 누적된 모든 메시지에서 컨텍스트 추출
    messages = state.get("messages", [])
    all_user_texts = [msg.content for msg in messages if hasattr(msg, "content")]
    full_context = " ".join(all_user_texts) if all_user_texts else state["raw_query"]

    intent = state.get("intent")

    # 전체 대화 컨텍스트로 파싱
    budget, items, recipient = parse_user_input(full_context)

    # 기본 제약조건 (중고/렌탈/해외직구 제외)
    constraints = Constraints(
        exclude_used=True,
        exclude_rental=True,
        exclude_overseas=True,
    )

    # Requirements 생성
    requirements = Requirements(
        budget=budget,
        items=items,
        recipient=recipient,
        constraints=constraints,
    )

    # 필수 필드 누락 확인
    intent_str = intent.value if intent else "VALUE"
    missing_fields = get_missing_fields(requirements, intent_str)
    requirements.missing_fields = missing_fields

    # clarification 필요 여부 결정
    clarification_needed = len(missing_fields) > 0 and requirements.clarify_count < 2

    clarification_question = None
    clarification_field = None

    if clarification_needed and missing_fields:
        field = missing_fields[0]
        clarification_field = field

        # 필드별 질문 생성
        if field == "recipient":
            clarification_question = "선물 받으실 분이 누구인가요? (예: 친구, 동료, 부모님)"
        elif field == "recipient.relation":
            clarification_question = "받는 분과의 관계가 어떻게 되나요?"
        elif field == "budget":
            clarification_question = "예산이 어느 정도인가요? (예: 5만원, 10만원)"
        elif field == "budget.total_budget":
            clarification_question = "총 예산이 얼마인가요?"
        elif field == "items":
            if intent_str == "BUNDLE":
                clarification_question = "어떤 품목들을 함께 구매하실 건가요? (예: 노트북, 마우스, 키보드)"
            else:
                clarification_question = "어떤 종류의 제품을 찾으시나요?"

    return {
        "requirements": requirements,
        "clarification_needed": clarification_needed,
        "clarification_question": clarification_question,
        "clarification_field": clarification_field,
        "processing_step": "requirements_extracted",
    }
