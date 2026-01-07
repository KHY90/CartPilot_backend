"""
GIFT 에이전트
선물 추천 모드 구현
"""
import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.product import ProductCandidate
from app.models.recommendation import GiftRecommendation, RecommendationCard
from app.services.cache import get_cache
from app.services.llm_provider import get_llm_provider
from app.services.naver_shopping import NaverShoppingError, get_naver_client

logger = logging.getLogger(__name__)

# 다양한 카테고리 믹스 추천용 키워드 (불확실 응답 시 사용)
MIXED_CATEGORY_KEYWORDS = {
    "fashion": ["남성 지갑 선물", "가죽 벨트 선물", "넥타이 선물세트", "머플러 선물"],
    "office": ["고급 만년필", "명함지갑 선물", "다이어리 선물", "탁상시계"],
    "tech": ["무선이어폰", "보조배터리 선물", "스마트워치", "블루투스 스피커"],
    "beauty": ["남성 향수 선물", "디퓨저 선물세트", "핸드크림 세트"],
    "living": ["텀블러 선물", "머그컵 세트", "인테리어 소품"],
}

# 선물 추천 프롬프트
GIFT_RECOMMENDATION_PROMPT = """당신은 선물 추천 전문가입니다.
주어진 상품 목록에서 선물로 적합한 상품을 선택하고 추천 이유를 작성하세요.

받는 사람 정보:
{recipient_info}

예산: {budget_info}

선물 스타일: {gift_style_info}

{user_preferences}

상품 목록:
{products}

다음 형식으로 3~10개 상품을 추천하세요 (JSON만 출력):
{{
  "recommendations": [
    {{
      "product_id": "상품 ID",
      "recommendation_reason": "이 상품을 추천하는 2-3문장 이유 (받는 사람 특성과 선물 스타일에 맞게 설명)",
      "warnings": ["주의사항 (있으면)"]
    }}
  ],
  "recipient_summary": "받는 분 요약 (예: 30대 남성 동료 (퇴사))",
  "occasion": "상황 (생일, 퇴사 등)"
}}

## 선물 스타일별 선택 기준

**격식있는 선물 (formal)**:
- 직장 동료, 상사, 거래처 등 비즈니스 관계에 적합
- 고급스러운 포장이 가능한 브랜드 제품 우선
- 만년필, 명함지갑, 고급 차/커피 세트, 디퓨저, 고급 수건세트, 와인/위스키, 골프용품 등
- 너무 개인적이거나 저렴해 보이는 상품 제외 (과자, 쿠키, 캐릭터 상품 등)
- 품격과 센스가 느껴지는 선물 선택

**고급스러운 선물 (luxury)**:
- 프리미엄 브랜드, 명품 위주
- 품질과 브랜드 가치가 중요
- 가격대가 높더라도 퀄리티 우선

**실용적인 선물 (practical)**:
- 일상에서 자주 사용할 수 있는 제품
- 가성비와 실용성 균형
- 가전, 생활용품, 주방용품 등

**감성적인 선물 (sentimental)**:
- 마음을 담은 의미있는 선물
- 커스텀/각인 가능한 제품
- 기념이 되는 특별한 아이템

**캐주얼한 선물 (casual)**:
- 부담없이 주고받을 수 있는 선물
- 재미있고 트렌디한 아이템
- 가격보다 센스가 중요

## 공통 선택 기준
1. 받는 사람의 특성(나이, 성별, 관계)에 맞는 상품
2. 예산 범위 내 상품 (단, 스타일에 따라 예산 상한에 가까운 상품도 고려)
3. 해당 상황(occasion)에 적합한 상품
4. 선물 스타일에 맞는 품격/분위기
5. 사용자의 구매 성향과 선호도 반영 (해당되는 경우)

**중요**: 선물 스타일이 'formal'이면 저렴하거나 캐주얼한 상품은 절대 추천하지 마세요.
"""


def _format_price(price: int) -> str:
    """가격을 한국어 형식으로 포맷"""
    return f"{price:,}원"


def _build_recipient_info(requirements: Any) -> str:
    """수신자 정보 문자열 생성"""
    if not requirements or not requirements.recipient:
        return "정보 없음"

    r = requirements.recipient
    parts = []

    if r.age_group:
        parts.append(r.age_group)
    if r.gender:
        gender_kr = {"male": "남성", "female": "여성"}.get(r.gender, "")
        parts.append(gender_kr)
    if r.relation:
        relation_kr = {
            "friend": "친구",
            "colleague": "동료",
            "boss": "상사",
            "parent": "부모님",
            "mother": "어머니",
            "father": "아버지",
            "girlfriend": "여자친구",
            "boyfriend": "남자친구",
            "wife": "아내",
            "husband": "남편",
            "child": "자녀",
            "son": "아들",
            "daughter": "딸",
            "teacher": "선생님",
            "professor": "교수님",
        }.get(r.relation, r.relation)
        parts.append(relation_kr)
    if r.occasion:
        occasion_kr = {
            "birthday": "생일",
            "farewell": "퇴사",
            "welcome": "입사",
            "promotion": "승진",
            "wedding": "결혼",
            "anniversary": "기념일",
            "christmas": "크리스마스",
            "valentine": "발렌타인데이",
            "whiteday": "화이트데이",
            "parents_day": "어버이날",
            "teachers_day": "스승의날",
            "graduation": "졸업",
            "enrollment": "입학",
        }.get(r.occasion, r.occasion)
        parts.append(f"({occasion_kr})")

    return " ".join(parts) if parts else "정보 없음"


def _build_budget_info(requirements: Any) -> str:
    """예산 정보 문자열 생성"""
    if not requirements or not requirements.budget:
        return "지정되지 않음"

    b = requirements.budget
    if b.min_price and b.max_price:
        return f"{_format_price(b.min_price)} ~ {_format_price(b.max_price)}"
    elif b.total_budget:
        return f"약 {_format_price(b.total_budget)}"
    elif b.max_price:
        return f"최대 {_format_price(b.max_price)}"

    return "지정되지 않음"


def _build_gift_style_info(requirements: Any) -> str:
    """선물 스타일 정보 문자열 생성"""
    if not requirements or not requirements.recipient:
        return "지정되지 않음 (기본: 상황에 맞게 판단)"

    r = requirements.recipient
    style = r.gift_style if hasattr(r, 'gift_style') and r.gift_style else None

    if style:
        style_descriptions = {
            "formal": "격식있는 선물 (formal) - 품격있고 세련된 선물",
            "luxury": "고급스러운 선물 (luxury) - 프리미엄/브랜드 위주",
            "practical": "실용적인 선물 (practical) - 일상에서 활용 가능한",
            "sentimental": "감성적인 선물 (sentimental) - 마음을 담은 의미있는",
            "casual": "캐주얼한 선물 (casual) - 부담없이 주고받는",
        }
        return style_descriptions.get(style, style)

    # 스타일이 없으면 상황에서 추론
    occasion = r.occasion
    relation = r.relation

    # 직장 관련이면 기본적으로 formal 권장
    formal_occasions = {"farewell", "promotion", "welcome", "retirement"}
    formal_relations = {"colleague", "boss", "professor", "teacher", "client"}

    if occasion in formal_occasions or relation in formal_relations:
        return "격식있는 선물 권장 (직장/공식 관계)"

    return "지정되지 않음 (상황에 맞게 판단)"


def _build_product_list(products: List[ProductCandidate]) -> str:
    """상품 목록 문자열 생성"""
    lines = []
    for i, p in enumerate(products[:20], 1):  # 최대 20개만
        lines.append(f"{i}. [{p.product_id}] {p.title} - {_format_price(p.price)} ({p.mall_name})")
    return "\n".join(lines)


def _create_recommendation_card(
    product: ProductCandidate, reason: str, warnings: List[str]
) -> RecommendationCard:
    """ProductCandidate를 RecommendationCard로 변환"""
    return RecommendationCard(
        product_id=product.product_id,
        title=product.title,
        image=product.image,
        price=product.price,
        price_display=_format_price(product.price),
        mall_name=product.mall_name,
        link=product.link,
        recommendation_reason=reason,
        warnings=warnings,
    )


async def gift_agent(state: AgentState) -> Dict[str, Any]:
    """
    GIFT 에이전트 노드

    1. 검색어 생성 (선물 + 대상 특성)
    2. 네이버 쇼핑 API로 상품 검색
    3. LLM으로 추천 상품 선택 및 이유 생성
    4. GiftRecommendation 반환

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 상태 딕셔너리
    """
    requirements = state.get("requirements")
    session_id = state.get("session_id", "")

    # 캐시 확인
    cache = get_cache()
    cache_key = cache.make_recommendation_key("GIFT", session_id, query=state.get("raw_query", ""))

    cached_result = await cache.get(cache_key)
    if cached_result:
        return {
            "recommendations": cached_result,
            "cached": True,
            "processing_step": "gift_completed",
        }

    try:
        # 1. 검색어 생성
        search_keywords = state.get("search_keywords", [])
        items = requirements.items if requirements else []
        is_uncertain = state.get("uncertain_response", False)

        # 불확실 응답("잘 모르겠어")인 경우 다양한 카테고리에서 믹스 추천
        if is_uncertain:
            logger.info("[GiftAgent] 불확실 응답 -> 다양한 카테고리 믹스 추천 모드")
            search_queries = _generate_mixed_category_queries(requirements)
        # items가 있으면 items 기반 검색어 생성
        elif items and len(items) > 0:
            search_queries = _generate_item_based_search_queries(items, requirements)
        elif search_keywords:
            search_queries = search_keywords
        else:
            search_queries = _generate_gift_search_queries(requirements)

        # 2. 상품 검색
        naver_client = get_naver_client()
        all_products: List[ProductCandidate] = []

        # 예산 범위 설정
        min_price = None
        max_price = None
        if requirements and requirements.budget:
            min_price = requirements.budget.min_price
            max_price = requirements.budget.max_price

        for query in search_queries[:3]:  # 최대 3개 검색어
            try:
                result = await naver_client.search(
                    query=query,
                    display=10,
                    sort="sim",
                    min_price=min_price,
                    max_price=max_price,
                )
                all_products.extend(result.items)
            except NaverShoppingError as e:
                print(f"검색 실패: {query} - {e}")
                continue

        if not all_products:
            return {
                "recommendations": None,
                "error": "검색 결과가 없습니다. 다른 키워드로 시도해 주세요.",
                "processing_step": "gift_failed",
            }

        # 중복 제거
        seen_ids = set()
        unique_products = []
        for p in all_products:
            if p.product_id not in seen_ids:
                seen_ids.add(p.product_id)
                unique_products.append(p)

        state["search_results"] = unique_products

        # 3. LLM으로 추천 생성
        llm_provider = get_llm_provider()

        # 사용자 성향 컨텍스트 가져오기
        user_prefs = state.get("user_preferences", "")

        prompt = GIFT_RECOMMENDATION_PROMPT.format(
            recipient_info=_build_recipient_info(requirements),
            budget_info=_build_budget_info(requirements),
            gift_style_info=_build_gift_style_info(requirements),
            user_preferences=user_prefs if user_prefs else "",
            products=_build_product_list(unique_products),
        )

        messages = [
            SystemMessage(content="당신은 친절한 선물 추천 전문가입니다."),
            HumanMessage(content=prompt),
        ]

        response = await llm_provider.generate(messages, temperature=0.7)

        # JSON 파싱
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        llm_result = json.loads(response_text)

        # 4. GiftRecommendation 생성
        product_map = {p.product_id: p for p in unique_products}
        cards: List[RecommendationCard] = []

        for rec in llm_result.get("recommendations", [])[:10]:
            product_id = rec.get("product_id")
            if product_id in product_map:
                card = _create_recommendation_card(
                    product=product_map[product_id],
                    reason=rec.get("recommendation_reason", "좋은 선물이 될 것 같습니다."),
                    warnings=rec.get("warnings", []),
                )
                cards.append(card)

        # 카드가 3개 미만이면 상위 상품으로 채우기
        if len(cards) < 3:
            for p in unique_products:
                if p.product_id not in {c.product_id for c in cards}:
                    cards.append(
                        _create_recommendation_card(
                            product=p,
                            reason="인기 있는 선물 상품입니다.",
                            warnings=[],
                        )
                    )
                    if len(cards) >= 3:
                        break

        gift_recommendation = GiftRecommendation(
            cards=cards[:10],  # 최대 10개 (프론트에서 5개씩 표시)
            recipient_summary=llm_result.get("recipient_summary", _build_recipient_info(requirements)),
            occasion=llm_result.get("occasion"),
            budget_range=_build_budget_info(requirements),
        )

        # 캐시 저장 (mode='json'으로 HttpUrl을 문자열로 변환)
        await cache.set(cache_key, gift_recommendation.model_dump(mode='json'))

        return {
            "recommendations": gift_recommendation.model_dump(mode='json'),
            "cached": False,
            "processing_step": "gift_completed",
        }

    except Exception as e:
        return {
            "recommendations": None,
            "error": f"선물 추천 생성 중 오류: {str(e)}",
            "processing_step": "gift_failed",
        }


def _generate_item_based_search_queries(items: List[str], requirements: Any) -> List[str]:
    """items 기반 검색어 생성 - 실제 상품 검색에 적합한 키워드"""
    queries = []

    # 수식어 결정
    gender_prefix = ""
    style_prefix = ""

    if requirements and requirements.recipient:
        r = requirements.recipient
        if r.gender:
            gender_prefix = {"male": "남성", "female": "여성"}.get(r.gender, "")
        if hasattr(r, 'gift_style') and r.gift_style:
            style_prefix = {
                "formal": "고급",
                "luxury": "프리미엄",
                "practical": "실용적인",
                "casual": "",
                "sentimental": "특별한",
            }.get(r.gift_style, "")

    # 각 item에 대해 검색어 생성
    for item in items[:5]:  # 최대 5개 품목
        # 기본 검색어: 품목 + 선물
        queries.append(f"{item} 선물")

        # 성별 + 품목
        if gender_prefix:
            queries.append(f"{gender_prefix} {item}")

        # 스타일 + 품목 + 선물
        if style_prefix:
            queries.append(f"{style_prefix} {item} 선물")

    # 중복 제거 및 최대 8개 반환
    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return unique_queries[:8]


def _generate_gift_search_queries(requirements: Any) -> List[str]:
    """기본 선물 검색어 생성 (items가 없을 때 fallback)"""
    queries = []

    if requirements and requirements.recipient:
        r = requirements.recipient

        # 성별 + 선물 조합 (더 일반적인 품목으로)
        gender_kr = ""
        if r.gender:
            gender_kr = {"male": "남성", "female": "여성"}.get(r.gender, "")

        # gift_style에 따른 기본 품목 추천
        style_items = {
            "formal": ["지갑 선물", "만년필 선물", "넥타이 선물", "명함지갑"],
            "luxury": ["프리미엄 선물세트", "브랜드 지갑", "명품 소품"],
            "practical": ["텀블러 선물", "보조배터리 선물", "이어폰"],
            "sentimental": ["각인 선물", "커스텀 선물", "포토북"],
            "casual": ["머그컵 선물", "간식 선물세트", "캐릭터 굿즈"],
        }

        gift_style = r.gift_style if hasattr(r, 'gift_style') and r.gift_style else "formal"
        default_items = style_items.get(gift_style, style_items["formal"])

        for item in default_items:
            if gender_kr:
                queries.append(f"{gender_kr} {item}")
            else:
                queries.append(item)

    # 기본 검색어 추가
    if not queries:
        queries = ["선물세트", "인기선물", "베스트선물"]

    return queries[:5]  # 최대 5개


def _generate_mixed_category_queries(requirements: Any) -> List[str]:
    """다양한 카테고리에서 골고루 검색어 생성 (불확실 응답용)"""
    queries = []

    # 성별 수식어
    gender_prefix = ""
    if requirements and requirements.recipient and requirements.recipient.gender:
        gender_prefix = {"male": "남성", "female": "여성"}.get(
            requirements.recipient.gender, ""
        )

    # 각 카테고리에서 1-2개씩 선택
    for category, keywords in MIXED_CATEGORY_KEYWORDS.items():
        for keyword in keywords[:2]:  # 각 카테고리에서 2개
            if gender_prefix and "남성" not in keyword and "여성" not in keyword:
                queries.append(f"{gender_prefix} {keyword}")
            else:
                queries.append(keyword)

    logger.info(f"[GiftAgent] 믹스 카테고리 검색어: {queries[:10]}")
    return queries[:10]  # 최대 10개
