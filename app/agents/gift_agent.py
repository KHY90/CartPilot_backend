"""
GIFT 에이전트
선물 추천 모드 구현
"""
import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.product import ProductCandidate
from app.models.recommendation import GiftRecommendation, RecommendationCard
from app.services.cache import get_cache
from app.services.llm_provider import get_llm_provider
from app.services.naver_shopping import NaverShoppingError, get_naver_client

# 선물 추천 프롬프트
GIFT_RECOMMENDATION_PROMPT = """당신은 선물 추천 전문가입니다.
주어진 상품 목록에서 선물로 적합한 상품을 선택하고 추천 이유를 작성하세요.

받는 사람 정보:
{recipient_info}

예산: {budget_info}

상품 목록:
{products}

다음 형식으로 3~6개 상품을 추천하세요 (JSON만 출력):
{{
  "recommendations": [
    {{
      "product_id": "상품 ID",
      "recommendation_reason": "이 상품을 추천하는 2-3문장 이유 (받는 사람 특성과 연결)",
      "warnings": ["주의사항 (있으면)"]
    }}
  ],
  "recipient_summary": "받는 분 요약 (예: 30대 남성 동료 (퇴사))",
  "occasion": "상황 (생일, 퇴사 등)"
}}

선택 기준:
1. 받는 사람의 특성(나이, 성별, 관계)에 맞는 상품
2. 예산 범위 내 상품 우선
3. 해당 상황(occasion)에 적합한 상품
4. 실용적이면서도 의미 있는 선물
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

        prompt = GIFT_RECOMMENDATION_PROMPT.format(
            recipient_info=_build_recipient_info(requirements),
            budget_info=_build_budget_info(requirements),
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

        for rec in llm_result.get("recommendations", [])[:6]:
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
            cards=cards[:6],
            recipient_summary=llm_result.get("recipient_summary", _build_recipient_info(requirements)),
            occasion=llm_result.get("occasion"),
            budget_range=_build_budget_info(requirements),
        )

        # 캐시 저장
        await cache.set(cache_key, gift_recommendation.model_dump())

        return {
            "recommendations": gift_recommendation.model_dump(),
            "cached": False,
            "processing_step": "gift_completed",
        }

    except Exception as e:
        return {
            "recommendations": None,
            "error": f"선물 추천 생성 중 오류: {str(e)}",
            "processing_step": "gift_failed",
        }


def _generate_gift_search_queries(requirements: Any) -> List[str]:
    """선물 검색어 생성"""
    queries = []

    if requirements and requirements.recipient:
        r = requirements.recipient

        # 기본 선물 검색어
        base = "선물"

        # 성별 + 나이대 조합
        if r.gender and r.age_group:
            gender_kr = {"male": "남자", "female": "여자"}.get(r.gender, "")
            queries.append(f"{r.age_group} {gender_kr} {base}")

        # 상황별 검색어
        if r.occasion:
            occasion_kr = {
                "birthday": "생일선물",
                "farewell": "퇴사선물",
                "welcome": "입사선물",
                "promotion": "승진선물",
                "wedding": "결혼선물",
                "anniversary": "기념일선물",
                "christmas": "크리스마스선물",
                "parents_day": "어버이날선물",
            }.get(r.occasion, f"{r.occasion}선물")
            queries.append(occasion_kr)

        # 관계별 검색어
        if r.relation:
            relation_kr = {
                "colleague": "직장동료선물",
                "boss": "상사선물",
                "friend": "친구선물",
                "girlfriend": "여자친구선물",
                "boyfriend": "남자친구선물",
                "parent": "부모님선물",
            }.get(r.relation)
            if relation_kr:
                queries.append(relation_kr)

    # 기본 검색어 추가
    if not queries:
        queries = ["인기선물", "베스트선물", "추천선물"]

    return queries[:5]  # 최대 5개
