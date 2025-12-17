"""
의도 분류 노드
사용자 입력에서 의도(GIFT, VALUE, BUNDLE, REVIEW, TREND)를 분류
"""
import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.request import IntentType
from app.services.llm_provider import get_llm_provider

# 의도 분류 시스템 프롬프트
INTENT_CLASSIFICATION_PROMPT = """당신은 쇼핑 요청을 분류하는 AI입니다.
사용자의 메시지를 분석하여 다음 5가지 의도 중 하나를 선택하세요:

1. GIFT - 선물 추천 요청
   - 특징: "선물", "줄", "드릴", 받는 사람 정보(관계, 성별, 나이), 상황(생일, 퇴사 등)
   - 예시: "30대 남자 동료 퇴사 선물 5만원", "여자친구 생일 선물 추천"

2. VALUE - 가성비 제품 비교 요청
   - 특징: "가성비", "추천", "좋은", 특정 품목 언급
   - 예시: "가성비 무선 키보드 추천", "좋은 마우스 뭐 있어?"

3. BUNDLE - 묶음 구매 최적화 요청
   - 특징: 여러 품목(+, 와, 랑), 총 예산, "맞춰줘", "세트"
   - 예시: "노트북+마우스+키보드 100만원에 맞춰줘", "사무용품 세트 구성"

4. REVIEW - 리뷰 기반 검증 요청
   - 특징: "사도 돼?", "괜찮아?", "단점", "후기", 구매 망설임
   - 예시: "에어프라이어 사도 돼?", "이 제품 단점이 뭐야?"

5. TREND - 트렌드 추천 요청
   - 특징: "요즘", "인기", "핫한", "뭐 사?", 시기 언급 없이 막연한 질문
   - 예시: "요즘 뭐 사?", "인기 있는 가전제품?"

응답 형식 (JSON만 출력):
{
  "intent": "GIFT|VALUE|BUNDLE|REVIEW|TREND",
  "confidence": 0.0~1.0,
  "secondary_intents": [],
  "reasoning": "판단 근거 (한국어)"
}
"""


async def classify_intent(state: AgentState) -> Dict[str, Any]:
    """
    의도 분류 노드

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 상태 딕셔너리
    """
    # 누적된 모든 메시지에서 전체 컨텍스트 구성
    state_messages = state.get("messages", [])
    all_user_texts = [msg.content for msg in state_messages if hasattr(msg, "content")]
    full_context = " ".join(all_user_texts) if all_user_texts else state["raw_query"]

    try:
        llm_provider = get_llm_provider()

        messages = [
            SystemMessage(content=INTENT_CLASSIFICATION_PROMPT),
            HumanMessage(content=f"사용자 메시지: {full_context}"),
        ]

        response = await llm_provider.generate(messages, temperature=0.1)

        # JSON 파싱
        # 코드 블록이 있으면 제거
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        result = json.loads(response_text)

        intent_str = result.get("intent", "VALUE")
        confidence = float(result.get("confidence", 0.5))
        secondary = result.get("secondary_intents", [])

        # IntentType으로 변환
        try:
            intent = IntentType(intent_str)
        except ValueError:
            intent = IntentType.VALUE
            confidence = 0.5

        # secondary_intents도 IntentType으로 변환
        secondary_intents = []
        for s in secondary:
            try:
                secondary_intents.append(IntentType(s))
            except ValueError:
                pass

        return {
            "intent": intent,
            "intent_confidence": confidence,
            "secondary_intents": secondary_intents,
            "processing_step": "intent_classified",
        }

    except Exception as e:
        # 에러 시 기본값 반환
        return {
            "intent": IntentType.VALUE,
            "intent_confidence": 0.3,
            "secondary_intents": [],
            "processing_step": "intent_classified",
            "error": f"의도 분류 실패: {str(e)}",
        }
