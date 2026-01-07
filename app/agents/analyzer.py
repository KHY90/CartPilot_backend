"""
통합 분석 노드
의도 분류 + 요구사항 추출을 단일 LLM 호출로 처리
"""
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.request import (
    BudgetRange,
    Constraints,
    IntentType,
    RecipientInfo,
    Requirements,
)
from app.services.llm_provider import get_llm_provider

# 로깅 설정
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# 불확실한 응답 패턴 (사용자가 선물 종류를 모를 때)
UNCERTAIN_RESPONSE_PATTERNS = [
    "모르겠", "잘 모르", "글쎄", "추천해", "아무거나",
    "알아서", "뭐든", "상관없", "맘대로", "골라줘",
    "아무", "괜찮", "편한대로", "네가 골라", "니가 골라",
    "알아서 해", "추천 해", "추천좀", "뭐가 좋", "뭘 사",
]


def _is_uncertain_response(message: str) -> bool:
    """사용자가 불확실한 응답을 했는지 감지"""
    message_lower = message.lower().strip()
    return any(pattern in message_lower for pattern in UNCERTAIN_RESPONSE_PATTERNS)


ANALYSIS_PROMPT = """당신은 쇼핑 요청을 분석하는 AI입니다.
사용자의 전체 대화 내용을 분석하여 의도와 요구사항을 추출하세요.

## 의도 분류 (5가지 중 하나 선택)

1. **GIFT** - 선물 추천
   - 키워드: "선물", "줄", "드릴", 받는 사람 정보, 기념일/이벤트
   - 예: "30대 남자 동료 퇴사 선물 5만원"

2. **VALUE** - 가성비 제품 비교
   - 키워드: "가성비", "추천", "좋은", 특정 품목
   - 예: "가성비 무선 키보드 추천"

3. **BUNDLE** - 묶음 구매 최적화
   - 키워드: 여러 품목, 총 예산, "맞춰줘", "세트"
   - 예: "노트북+마우스+키보드 100만원"

4. **REVIEW** - 리뷰 기반 검증
   - 키워드: "사도 돼?", "괜찮아?", "단점", "후기"
   - 예: "에어프라이어 사도 돼?"

5. **TREND** - 트렌드 추천
   - 키워드: "요즘", "인기", "핫한", "뭐 사?"
   - 예: "요즘 인기 있는 가전?"

## 요구사항 추출

대화 내용에서 다음 정보를 추출하세요:

- **budget**: 예산 정보 (min_price, max_price, total_budget)
- **items**: 찾는 품목/카테고리 리스트 (구체적 품목으로 확장)
  - "방한용품" → ["목도리", "장갑", "머플러", "핫팩"]
  - "전자기기" → ["노트북", "태블릿", "이어폰"]
- **recipient**: 선물 대상 정보 (GIFT 모드일 때)
  - relation: 관계 (friend, colleague, parent, etc.)
  - gender: 성별 (male, female)
  - age_group: 연령대 (20대, 30대 등)
  - occasion: 상황 (birthday, farewell, wedding 등)
  - gift_style: 선물 스타일 (아래 기준 참조)

## 선물 스타일 (gift_style) 판단 기준

GIFT 모드일 때 상황과 관계에 따라 적절한 gift_style을 추론하세요:

- **formal** (격식있는): 직장 상사, 동료 퇴사/승진, 교수님, 거래처 등 비즈니스/공식적 관계
- **luxury** (고급스러운): 명품, 프리미엄, 브랜드를 원하는 경우
- **practical** (실용적인): 일상에서 쓸 수 있는 실용적인 선물
- **sentimental** (감성적인): 연인, 부모님, 특별한 기념일 등 감정적 의미가 중요한 경우
- **casual** (캐주얼한): 친한 친구, 가벼운 선물, 재미있는 선물

**중요**: 사용자가 명시적으로 스타일을 언급하지 않았더라도 상황에서 유추하세요:
- "동료 퇴사" → formal (직장 관계는 기본적으로 격식)
- "상사 승진" → formal 또는 luxury
- "여자친구 생일" → sentimental 또는 luxury
- "친구 집들이" → practical 또는 casual

## 응답 형식 (JSON만 출력)

```json
{
  "intent": "GIFT|VALUE|BUNDLE|REVIEW|TREND",
  "confidence": 0.0~1.0,
  "budget": {
    "min_price": 숫자 또는 null,
    "max_price": 숫자 또는 null,
    "total_budget": 숫자 또는 null,
    "is_flexible": true/false
  },
  "items": ["품목1", "품목2"],
  "recipient": {
    "relation": "관계 또는 null",
    "gender": "male/female 또는 null",
    "age_group": "연령대 또는 null",
    "occasion": "상황 또는 null",
    "gift_style": "formal/casual/luxury/practical/sentimental 또는 null"
  },
  "search_keywords": ["메인 키워드", "대체 키워드1", "대체 키워드2"],
  "reasoning": "분석 근거"
}
```

중요:
- items는 사용자가 언급한 것뿐 아니라 맥락에서 유추 가능한 구체적 품목도 포함
- **GIFT 모드에서 items가 비어있으면 빈 배열로 두세요** (추후 사용자에게 질문함)
- search_keywords는 **실제 상품 검색에 적합한 품목 기반 키워드**를 생성하세요:
  - **잘못된 예**: "30대 남자 동료 퇴사 선물" (파티용품만 검색됨)
  - **올바른 예**: "남성 가죽지갑", "고급 만년필 선물", "남자 넥타이 선물세트"
  - items에 있는 품목 + 수식어(선물, 남성, 고급 등) 조합으로 생성
  - items가 비어있으면 search_keywords도 빈 배열로
- 정보가 없으면 null로 표시
- GIFT 모드에서 gift_style은 상황과 관계에서 최대한 유추
"""


async def analyze_request(state: AgentState) -> Dict[str, Any]:
    """
    통합 분석 노드 - 의도 분류 + 요구사항 추출

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 상태 딕셔너리
    """
    # 누적된 모든 메시지에서 전체 컨텍스트 구성
    state_messages = state.get("messages", [])
    logger.info(f"[Analyzer] 받은 메시지 수: {len(state_messages)}")
    logger.info(f"[Analyzer] 메시지 내용: {state_messages}")

    all_user_texts = [msg.content for msg in state_messages if hasattr(msg, "content")]
    full_context = " ".join(all_user_texts) if all_user_texts else state["raw_query"]

    logger.info(f"[Analyzer] 전체 컨텍스트: {full_context}")

    # 현재 메시지가 불확실한 응답인지 확인 (clarification에 대한 "모르겠어요" 답변)
    current_message = state.get("raw_query", "")
    is_uncertain = _is_uncertain_response(current_message)

    # 이전 상태에서 clarification이 진행 중이었는지 확인
    previous_clarification = state.get("clarification_needed", False)

    if is_uncertain and previous_clarification:
        logger.info(f"[Analyzer] 불확실 응답 감지: '{current_message}' -> 다양한 카테고리 믹스 추천 모드")
        return {
            "intent": IntentType.GIFT,
            "intent_confidence": 0.8,
            "secondary_intents": [],
            "requirements": state.get("requirements"),
            "search_keywords": [],
            "clarification_needed": False,
            "clarification_question": None,
            "clarification_field": None,
            "processing_step": "analyzed",
            "uncertain_response": True,  # 불확실 응답 플래그
        }

    try:
        llm_provider = get_llm_provider()

        messages = [
            SystemMessage(content=ANALYSIS_PROMPT),
            HumanMessage(content=f"사용자 대화 내용:\n{full_context}"),
        ]

        response = await llm_provider.generate(messages, temperature=0.1)
        logger.info(f"[Analyzer] LLM 응답 원본:\n{response}")

        # JSON 파싱 (코드 블록 제거)
        response_text = response.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        response_text = response_text.strip()

        logger.info(f"[Analyzer] 파싱할 JSON: {response_text}")

        result = json.loads(response_text)
        logger.info(f"[Analyzer] 파싱된 결과: {result}")

        # Intent 파싱
        intent_str = result.get("intent", "VALUE")
        confidence = float(result.get("confidence", 0.5))

        try:
            intent = IntentType(intent_str)
        except ValueError:
            intent = IntentType.VALUE
            confidence = 0.5

        # Budget 파싱
        budget_data = result.get("budget", {})
        budget = None
        if budget_data and any(budget_data.get(k) for k in ["min_price", "max_price", "total_budget"]):
            budget = BudgetRange(
                min_price=budget_data.get("min_price"),
                max_price=budget_data.get("max_price"),
                total_budget=budget_data.get("total_budget"),
                is_flexible=budget_data.get("is_flexible", True),
            )

        # Items 파싱
        items = result.get("items", [])
        search_keywords = result.get("search_keywords", items)

        # Recipient 파싱
        recipient_data = result.get("recipient", {})
        recipient = None
        if recipient_data and any(recipient_data.values()):
            recipient = RecipientInfo(
                relation=recipient_data.get("relation"),
                gender=recipient_data.get("gender"),
                age_group=recipient_data.get("age_group"),
                occasion=recipient_data.get("occasion"),
                gift_style=recipient_data.get("gift_style"),
            )

        # Requirements 구성
        constraints = Constraints(
            exclude_used=True,
            exclude_rental=True,
            exclude_overseas=True,
        )

        requirements = Requirements(
            budget=budget,
            items=items,
            recipient=recipient,
            constraints=constraints,
        )

        # 필수 필드 누락 확인
        missing_fields = _get_missing_fields(requirements, intent_str)
        requirements.missing_fields = missing_fields

        logger.info(f"[Analyzer] Intent: {intent_str}, Items: {items}, Missing: {missing_fields}")

        # Clarification 필요 여부
        clarification_needed = len(missing_fields) > 0 and requirements.clarify_count < 2
        clarification_question = None
        clarification_field = None

        if clarification_needed and missing_fields:
            clarification_field, clarification_question = _get_clarification_question(
                missing_fields[0], intent_str
            )

        logger.info(f"[Analyzer] Clarification needed: {clarification_needed}, Question: {clarification_question}")

        return {
            "intent": intent,
            "intent_confidence": confidence,
            "secondary_intents": [],
            "requirements": requirements,
            "search_keywords": search_keywords,
            "clarification_needed": clarification_needed,
            "clarification_question": clarification_question,
            "clarification_field": clarification_field,
            "processing_step": "analyzed",
        }

    except Exception as e:
        # 에러 시 기본값 반환
        logger.error(f"[Analyzer] 분석 실패: {str(e)}", exc_info=True)
        return {
            "intent": IntentType.VALUE,
            "intent_confidence": 0.3,
            "secondary_intents": [],
            "requirements": Requirements(
                constraints=Constraints(
                    exclude_used=True,
                    exclude_rental=True,
                    exclude_overseas=True,
                )
            ),
            "search_keywords": [],
            "clarification_needed": True,
            "clarification_question": "어떤 제품을 찾으시나요?",
            "clarification_field": "items",
            "processing_step": "analyzed",
            "error": f"분석 실패: {str(e)}",
        }


def _get_missing_fields(requirements: Requirements, intent_str: str) -> List[str]:
    """의도에 따라 필수 필드 누락 여부 확인"""
    missing = []

    if intent_str == "GIFT":
        if not requirements.recipient or not requirements.recipient.relation:
            missing.append("recipient")
        if not requirements.budget:
            missing.append("budget")
        # recipient와 budget이 있을 때, 구체적인 선물 카테고리가 없으면 질문
        # items가 비어있거나 너무 추상적이면 gift_category 질문
        if (requirements.recipient and requirements.recipient.relation and
            requirements.budget):
            # items가 없거나 구체적이지 않으면 선물 종류 질문
            if not requirements.items or len(requirements.items) == 0:
                missing.append("gift_category")
            # gift_style이 없으면 선물 분위기 질문은 생략 (자동 유추로 충분)

    elif intent_str == "VALUE":
        if not requirements.items:
            missing.append("items")

    elif intent_str == "BUNDLE":
        if not requirements.items or len(requirements.items) < 2:
            missing.append("items")
        if not requirements.budget or not requirements.budget.total_budget:
            missing.append("budget")

    elif intent_str == "REVIEW":
        if not requirements.items:
            missing.append("items")

    # TREND는 필수 필드 없음

    return missing


def _get_clarification_question(field: str, intent_str: str) -> tuple[str, str]:
    """필드별 추가 질문 생성"""
    questions = {
        "recipient": ("recipient", "선물 받으실 분이 누구인가요? (예: 친구, 동료, 부모님)"),
        "budget": ("budget", "예산이 어느 정도인가요? (예: 5만원, 10만원)"),
        "items": (
            "items",
            "어떤 품목들을 함께 구매하실 건가요?" if intent_str == "BUNDLE"
            else "어떤 종류의 제품을 찾으시나요?"
        ),
        "gift_category": (
            "gift_category",
            "어떤 종류의 선물을 찾으시나요?\n"
            "• 패션/액세서리 (지갑, 벨트, 넥타이, 목도리 등)\n"
            "• 뷰티/향수 (스킨케어, 향수, 디퓨저 등)\n"
            "• 테크/가전 (이어폰, 스마트워치, 미니가전 등)\n"
            "• 리빙/인테리어 (머그컵, 텀블러, 인테리어소품 등)\n"
            "• 식품/건강 (건강식품, 차, 커피 등)\n"
            "• 문구/오피스 (만년필, 다이어리, 명함지갑 등)\n"
            "• 잘 모르겠어요 (추천해 주세요)"
        ),
        "gift_style": (
            "gift_style",
            "어떤 느낌의 선물을 원하시나요?\n"
            "• 격식있는 선물 (직장, 공식적인 자리)\n"
            "• 고급스러운 선물 (프리미엄, 브랜드)\n"
            "• 실용적인 선물 (일상에서 쓸 수 있는)\n"
            "• 감성적인 선물 (마음을 담은)\n"
            "• 캐주얼한 선물 (가볍고 재미있는)"
        ),
    }
    return questions.get(field, ("unknown", "추가 정보가 필요합니다."))
