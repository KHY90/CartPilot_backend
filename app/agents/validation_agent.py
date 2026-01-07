"""
검증 에이전트 (Validation Agent)
추천된 상품이 사용자 요청에 실제로 부합하는지 검증
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.request import IntentType
from app.services.llm_provider import get_llm_provider

logger = logging.getLogger(__name__)

# 의도 컨텍스트별 카테고리 매핑
CATEGORY_CONTEXT = {
    "food": {
        "keywords": ["먹", "식사", "음식", "간식", "아침", "점심", "저녁", "식품", "음료", "마시", "대용", "영양"],
        "allowed_categories": ["식품", "건강식품", "신선식품", "가공식품", "출산/육아"],
        "exclude_keywords": ["케이스", "보관", "용기", "그릇", "컵홀더", "거치대", "박스", "포장", "수납"],
    },
    "electronics": {
        "keywords": ["전자", "디지털", "가전", "컴퓨터", "노트북", "핸드폰", "휴대폰", "태블릿", "모니터"],
        "allowed_categories": ["디지털/가전", "PC주변기기", "휴대폰/태블릿", "가전"],
        "exclude_keywords": ["케이스", "파우치", "가방", "커버"],
    },
    "clothing": {
        "keywords": ["옷", "의류", "패션", "입", "신발", "가방", "모자", "액세서리"],
        "allowed_categories": ["패션의류", "패션잡화", "스포츠/레저"],
        "exclude_keywords": ["세제", "세탁"],
    },
    "beauty": {
        "keywords": ["화장", "뷰티", "스킨", "케어", "향수", "미용"],
        "allowed_categories": ["화장품/미용", "헬스/건강"],
        "exclude_keywords": ["파우치", "케이스", "거울"],
    },
    "gift": {
        "keywords": ["선물", "퇴사", "승진", "생일", "기념일", "송별"],
        "allowed_categories": [],  # 선물은 카테고리 제한 없음
        "exclude_keywords": [
            # 파티용품/장식품 제외
            "배너", "현수막", "가랜드", "풍선", "파티", "장식",
            "방명록", "서명판", "표지판", "포토존", "이벤트용",
            # 포장재 제외
            "포장지", "리본", "쇼핑백", "선물상자만",
            # 기타 부적절한 것
            "은퇴", "파티장식", "글리터", "스트랜드",
        ],
    },
}

# GIFT 모드용 기본 선물 품목 (재검색시 사용)
GIFT_DEFAULT_ITEMS = {
    "formal": ["지갑", "만년필", "넥타이", "명함지갑", "벨트", "스카프"],
    "luxury": ["브랜드 지갑", "프리미엄 선물세트", "고급 펜"],
    "practical": ["텀블러", "보조배터리", "무선이어폰", "손목시계"],
    "casual": ["머그컵", "키링", "캐릭터 굿즈", "에코백"],
    "sentimental": ["포토북", "각인 선물", "커스텀 굿즈"],
}

# 검증 프롬프트
VALIDATION_PROMPT = """당신은 상품 적합성 검증 전문가입니다.

사용자 요청: {user_query}
추출된 의도: {intent}

추천된 상품 목록:
{product_list}

각 상품이 사용자 요청에 적합한지 판단하세요.

## 판단 기준
1. **카테고리 적합성**: 요청한 품목 유형과 일치하는가?
   - 예: "식사 대용품" 요청 → 식품/건강식품 카테고리만 적합
2. **용도 적합성**: 사용자의 실제 목적에 부합하는가?
   - 예: "아침 식사" → 간편하게 먹을 수 있는 음식
3. **의미적 일치**: 키워드가 사용자 의도와 같은 의미로 사용되었는가?
   - 예: "가벼운 식사" → 칼로리/소화가 가벼운 음식 (물리적 무게가 아님)
   - 예: "가벼운 운동" → 강도가 낮은 운동

## 응답 형식 (JSON만 출력)
{{
  "validated_products": [
    {{
      "product_id": "상품ID",
      "suitable": true 또는 false,
      "reason": "적합/부적합 판단 이유 (1문장)"
    }}
  ],
  "suggested_keywords": ["더 적합한 검색 키워드 (부적합 상품이 많을 경우 2-3개)"]
}}
"""


def _extract_intent_context(raw_query: str, intent: Optional[IntentType] = None) -> Dict[str, Any]:
    """사용자 요청에서 의도 컨텍스트 추출"""
    context = {
        "type": None,
        "allowed_categories": [],
        "exclude_keywords": [],
    }

    raw_query_lower = raw_query.lower()

    # GIFT 의도면 gift 컨텍스트 강제 적용
    if intent == IntentType.GIFT:
        gift_config = CATEGORY_CONTEXT["gift"]
        context["type"] = "gift"
        context["allowed_categories"] = gift_config["allowed_categories"]
        context["exclude_keywords"] = gift_config["exclude_keywords"]
        return context

    for context_type, config in CATEGORY_CONTEXT.items():
        if any(kw in raw_query_lower for kw in config["keywords"]):
            context["type"] = context_type
            context["allowed_categories"] = config["allowed_categories"]
            context["exclude_keywords"] = config["exclude_keywords"]
            break

    return context


def _extract_products_from_recommendations(
    recommendations: Optional[Dict[str, Any]], intent: Optional[IntentType]
) -> List[Dict[str, Any]]:
    """모드별 추천 결과에서 상품 목록 추출"""
    if not recommendations:
        return []

    products = []

    if intent == IntentType.VALUE:
        # VALUE: budget_tier, standard_tier, premium_tier
        for tier in ["budget_tier", "standard_tier", "premium_tier"]:
            tier_products = recommendations.get(tier, [])
            for p in tier_products:
                p["_tier"] = tier  # 원본 티어 정보 보존
                products.append(p)

    elif intent == IntentType.GIFT:
        # GIFT: cards
        products = recommendations.get("cards", [])

    elif intent == IntentType.BUNDLE:
        # BUNDLE: combinations[].items[].product
        for combo in recommendations.get("combinations", []):
            for item in combo.get("items", []):
                product = item.get("product")
                if product:
                    product["_combo_id"] = combo.get("combination_id")
                    product["_item_category"] = item.get("item_category")
                    products.append(product)

    elif intent == IntentType.TREND:
        # TREND: trending_items[].products
        for trend_item in recommendations.get("trending_items", []):
            for p in trend_item.get("products", []):
                p["_trend_category"] = trend_item.get("category")
                products.append(p)

    return products


def _rule_based_filter(
    products: List[Dict[str, Any]], intent_context: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """규칙 기반 1차 필터링"""
    if not intent_context.get("type"):
        # 컨텍스트가 없으면 전부 통과
        return products, []

    suitable = []
    excluded = []
    allowed_categories = intent_context.get("allowed_categories", [])
    exclude_keywords = intent_context.get("exclude_keywords", [])

    for product in products:
        is_suitable = True
        title = product.get("title", "").lower()

        # 제목에 부적합 키워드 포함 여부
        if any(kw in title for kw in exclude_keywords):
            is_suitable = False

        if is_suitable:
            suitable.append(product)
        else:
            excluded.append(product)
            logger.debug(f"[ValidationAgent] 규칙 필터 제외: {product.get('title', '')[:30]}...")

    return suitable, excluded


def _build_product_list_for_validation(products: List[Dict[str, Any]]) -> str:
    """검증용 상품 목록 문자열 생성"""
    lines = []
    for i, p in enumerate(products[:20], 1):  # 최대 20개
        title = p.get("title", "알 수 없음")
        price = p.get("price", 0)
        product_id = p.get("product_id", f"unknown_{i}")
        lines.append(f"{i}. [{product_id}] {title} - {price:,}원")
    return "\n".join(lines)


def _rebuild_recommendations(
    original: Dict[str, Any],
    validated_product_ids: set,
    intent: Optional[IntentType],
) -> Dict[str, Any]:
    """검증된 상품만으로 추천 결과 재구성"""
    if intent == IntentType.VALUE:
        return {
            "budget_tier": [
                p for p in original.get("budget_tier", [])
                if p.get("product_id") in validated_product_ids
            ],
            "standard_tier": [
                p for p in original.get("standard_tier", [])
                if p.get("product_id") in validated_product_ids
            ],
            "premium_tier": [
                p for p in original.get("premium_tier", [])
                if p.get("product_id") in validated_product_ids
            ],
            "category": original.get("category", ""),
        }

    elif intent == IntentType.GIFT:
        return {
            "cards": [
                p for p in original.get("cards", [])
                if p.get("product_id") in validated_product_ids
            ],
            "recipient_summary": original.get("recipient_summary", ""),
            "occasion": original.get("occasion"),
            "budget_range": original.get("budget_range", ""),
        }

    elif intent == IntentType.BUNDLE:
        new_combinations = []
        for combo in original.get("combinations", []):
            new_items = []
            for item in combo.get("items", []):
                product = item.get("product")
                if product and product.get("product_id") in validated_product_ids:
                    new_items.append(item)
            if new_items:
                new_combo = combo.copy()
                new_combo["items"] = new_items
                new_combinations.append(new_combo)
        return {
            "combinations": new_combinations,
            "total_budget": original.get("total_budget"),
            "items_count": original.get("items_count"),
        }

    elif intent == IntentType.TREND:
        new_trending = []
        for trend_item in original.get("trending_items", []):
            new_products = [
                p for p in trend_item.get("products", [])
                if p.get("product_id") in validated_product_ids
            ]
            if new_products:
                new_item = trend_item.copy()
                new_item["products"] = new_products
                new_trending.append(new_item)
        return {
            "trending_items": new_trending,
            "data_source": original.get("data_source"),
            "generated_at": original.get("generated_at"),
            "disclaimer": original.get("disclaimer"),
        }

    return original


async def validation_agent(state: AgentState) -> Dict[str, Any]:
    """
    검증 에이전트 노드

    1. 추천 결과에서 상품 목록 추출
    2. 규칙 기반 1차 필터링
    3. LLM 기반 2차 검증
    4. 결과에 따른 분기 처리 (5개 기준)

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 상태 딕셔너리
    """
    recommendations = state.get("recommendations")
    raw_query = state.get("raw_query", "")
    intent = state.get("intent")
    retry_count = state.get("retry_count", 0)
    search_keywords = state.get("search_keywords", [])

    logger.info(f"[ValidationAgent] 시작 - intent: {intent}, retry: {retry_count}")

    # 추천 결과가 없거나 에러 상태면 스킵
    if not recommendations or state.get("error"):
        logger.info("[ValidationAgent] 검증할 추천 결과 없음, 스킵")
        return {
            "validation_passed": True,
            "processing_step": "validation_skipped",
        }

    # 1. 상품 목록 추출
    products = _extract_products_from_recommendations(recommendations, intent)
    logger.info(f"[ValidationAgent] 추출된 상품 수: {len(products)}")

    if not products:
        return {
            "validation_passed": True,
            "processing_step": "validation_skipped",
        }

    # 2. 의도 컨텍스트 추출 (intent 전달하여 GIFT 처리)
    intent_context = _extract_intent_context(raw_query, intent)
    logger.info(f"[ValidationAgent] 의도 컨텍스트: {intent_context.get('type')}")

    # 3. 규칙 기반 1차 필터링
    rule_filtered, rule_excluded = _rule_based_filter(products, intent_context)
    logger.info(f"[ValidationAgent] 규칙 필터 후: 통과 {len(rule_filtered)}, 제외 {len(rule_excluded)}")

    # 규칙 필터만으로 충분하면 LLM 생략
    if len(rule_filtered) >= 5 and len(rule_excluded) == 0:
        logger.info("[ValidationAgent] 규칙 필터만으로 충분, LLM 검증 생략")
        return {
            "validation_passed": True,
            "processing_step": "validation_passed_rule_only",
        }

    # 4. LLM 기반 2차 검증
    validated_product_ids = set()
    suggested_keywords = []

    if rule_filtered:
        try:
            llm_provider = get_llm_provider()
            product_list_str = _build_product_list_for_validation(rule_filtered)

            prompt = VALIDATION_PROMPT.format(
                user_query=raw_query,
                intent=intent.value if intent else "unknown",
                product_list=product_list_str,
            )

            messages = [
                SystemMessage(content="당신은 상품 적합성 검증 전문가입니다. 정확한 JSON 형식으로만 응답하세요."),
                HumanMessage(content=prompt),
            ]

            logger.info("[ValidationAgent] LLM 검증 호출 중...")
            response = await llm_provider.generate(messages, temperature=0.3)

            # JSON 파싱
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            llm_result = json.loads(response_text)

            # 적합 상품 ID 추출
            for item in llm_result.get("validated_products", []):
                if item.get("suitable", False):
                    validated_product_ids.add(item.get("product_id"))
                else:
                    logger.debug(f"[ValidationAgent] LLM 제외: {item.get('product_id')} - {item.get('reason')}")

            suggested_keywords = llm_result.get("suggested_keywords", [])
            logger.info(f"[ValidationAgent] LLM 검증 결과: 적합 {len(validated_product_ids)}/{len(rule_filtered)}")

        except json.JSONDecodeError as e:
            logger.warning(f"[ValidationAgent] LLM 응답 파싱 실패: {e}")
            # 파싱 실패 시 규칙 필터 결과 사용
            validated_product_ids = {p.get("product_id") for p in rule_filtered}
        except Exception as e:
            logger.error(f"[ValidationAgent] LLM 검증 오류: {e}")
            validated_product_ids = {p.get("product_id") for p in rule_filtered}
    else:
        logger.info("[ValidationAgent] 규칙 필터 통과 상품 없음")

    # 5. 결과 처리
    suitable_count = len(validated_product_ids)
    total_count = len(products)

    # 적합 비율 계산 (절반 이상 또는 3개 이상이면 충분)
    is_sufficient = suitable_count >= 3 or (total_count > 0 and suitable_count / total_count >= 0.5)

    if is_sufficient:
        # 충분함 → 필터링된 결과 반환
        filtered_recs = _rebuild_recommendations(recommendations, validated_product_ids, intent)
        logger.info(f"[ValidationAgent] 검증 통과 - 적합 상품 {suitable_count}/{total_count}개")
        return {
            "validation_passed": True,
            "recommendations": filtered_recs,
            "processing_step": "validation_passed",
        }

    elif suitable_count > 0:
        # 적합 상품이 있지만 부족 → 있는 것만 반환 (재검색 생략)
        filtered_recs = _rebuild_recommendations(recommendations, validated_product_ids, intent)
        logger.info(f"[ValidationAgent] 부분 통과 - 적합 상품 {suitable_count}/{total_count}개로 반환")
        return {
            "validation_passed": True,
            "recommendations": filtered_recs,
            "validation_feedback": f"요청에 맞는 상품이 {suitable_count}개로 제한적입니다.",
            "processing_step": "validation_partial",
        }

    elif retry_count < 1:
        # 적합 상품 0개 → 재검색 트리거
        # GIFT 의도면 품목 기반 키워드로 재검색
        if intent == IntentType.GIFT:
            new_keywords = _generate_gift_retry_keywords(state)
        elif suggested_keywords:
            new_keywords = suggested_keywords
        else:
            new_keywords = search_keywords

        logger.info(f"[ValidationAgent] 재검색 필요 (적합 0개) - 새 키워드: {new_keywords}")
        return {
            "validation_passed": False,
            "retry_count": retry_count + 1,
            "search_keywords": new_keywords,
            "original_search_keywords": search_keywords,
            "processing_step": "validation_retry",
        }

    else:
        # 재검색 실패 → 에러 메시지
        logger.warning("[ValidationAgent] 재검색 후에도 적합 상품 없음")
        return {
            "validation_passed": True,
            "recommendations": None,
            "error": "요청에 맞는 상품을 찾지 못했습니다. 다른 키워드로 검색해 주세요.",
            "validation_feedback": "검색 결과가 요청과 일치하지 않습니다.",
            "processing_step": "validation_failed",
        }


def _generate_gift_retry_keywords(state: AgentState) -> List[str]:
    """GIFT 의도용 재검색 키워드 생성 - 품목 기반"""
    requirements = state.get("requirements")
    keywords = []

    # 성별 수식어
    gender_prefix = ""
    if requirements and requirements.recipient and requirements.recipient.gender:
        gender_prefix = {"male": "남성", "female": "여성"}.get(
            requirements.recipient.gender, ""
        )

    # gift_style에 따른 기본 품목 선택
    gift_style = "formal"  # 기본값
    if requirements and requirements.recipient:
        gift_style = getattr(requirements.recipient, 'gift_style', 'formal') or 'formal'

    default_items = GIFT_DEFAULT_ITEMS.get(gift_style, GIFT_DEFAULT_ITEMS["formal"])

    # 품목 기반 키워드 생성
    for item in default_items[:4]:
        if gender_prefix:
            keywords.append(f"{gender_prefix} {item} 선물")
        else:
            keywords.append(f"{item} 선물")

    logger.info(f"[ValidationAgent] GIFT 재검색 키워드 생성: {keywords}")
    return keywords
