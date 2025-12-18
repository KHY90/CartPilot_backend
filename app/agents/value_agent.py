"""
VALUE 에이전트
가성비 추천 모드 구현 - 가격대별 티어 분류 및 추천
"""
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.product import ProductCandidate
from app.models.recommendation import RecommendationCard, ValueRecommendation
from app.services.cache import get_cache
from app.services.llm_provider import get_llm_provider
from app.services.naver_shopping import NaverShoppingError, get_naver_client

logger = logging.getLogger(__name__)

# 가성비 추천 프롬프트
VALUE_RECOMMENDATION_PROMPT = """당신은 가성비 분석 전문가입니다.
주어진 상품 목록을 분석하여 가격대별로 분류하고 추천 이유를 작성하세요.

상품 카테고리: {category}
검색 키워드: {search_keywords}

상품 목록:
{products}

다음 형식으로 가격대별 추천을 작성하세요 (JSON만 출력):
{{
  "budget_tier": [
    {{
      "product_id": "상품 ID",
      "recommendation_reason": "이 가격대에서 이 상품을 추천하는 이유 (2-3문장)",
      "tier_benefits": "이 가격대에서 얻는 것",
      "tier_tradeoffs": "이 가격대에서 포기하는 것",
      "warnings": ["주의사항 (있으면)"]
    }}
  ],
  "standard_tier": [...],
  "premium_tier": [...]
}}

분류 기준:
1. budget_tier (저가): 가격 하위 33% - 가성비 최우선, 기본 기능 충실
2. standard_tier (표준): 가격 중위 34-66% - 가격 대비 성능 균형
3. premium_tier (프리미엄): 가격 상위 67% 이상 - 최고 품질/기능

각 티어별로 1-2개 상품을 추천하세요. 총 3-6개 상품.

선택 기준:
1. 해당 가격대에서 가장 가성비가 좋은 상품
2. 리뷰/평점이 좋은 상품 우선
3. 유명 브랜드 vs 가성비 브랜드 균형
4. 실용성과 내구성 고려
"""


def _format_price(price: int) -> str:
    """가격을 한국어 형식으로 포맷"""
    return f"{price:,}원"


def _build_product_list(products: List[ProductCandidate]) -> str:
    """상품 목록 문자열 생성"""
    lines = []
    for i, p in enumerate(products[:30], 1):  # 최대 30개
        brand_info = f" [{p.brand}]" if p.brand else ""
        lines.append(
            f"{i}. [{p.product_id}] {p.title}{brand_info} - {_format_price(p.price)} ({p.mall_name})"
        )
    return "\n".join(lines)


def _classify_by_price_tier(
    products: List[ProductCandidate],
) -> Dict[str, List[ProductCandidate]]:
    """상품을 가격대별로 분류"""
    if not products:
        return {"budget": [], "standard": [], "premium": []}

    # 가격으로 정렬
    sorted_products = sorted(products, key=lambda x: x.price)
    total = len(sorted_products)

    # 33%, 66% 기준으로 분류
    budget_end = total // 3
    standard_end = (total * 2) // 3

    return {
        "budget": sorted_products[:budget_end] if budget_end > 0 else sorted_products[:1],
        "standard": sorted_products[budget_end:standard_end]
        if standard_end > budget_end
        else sorted_products[budget_end : budget_end + 1],
        "premium": sorted_products[standard_end:] if standard_end < total else sorted_products[-1:],
    }


def _create_recommendation_card(
    product: ProductCandidate,
    reason: str,
    warnings: List[str],
    tier: str,
    tier_benefits: Optional[str] = None,
    tier_tradeoffs: Optional[str] = None,
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
        tier=tier,
        tier_benefits=tier_benefits,
        tier_tradeoffs=tier_tradeoffs,
    )


def _extract_category(requirements: Any, search_keywords: List[str]) -> str:
    """카테고리 추출"""
    if requirements and requirements.items:
        return requirements.items[0]
    if search_keywords:
        # 검색 키워드에서 카테고리 추출
        return search_keywords[0].replace("가성비", "").replace("추천", "").strip()
    return "상품"


async def value_agent(state: AgentState) -> Dict[str, Any]:
    """
    VALUE 에이전트 노드

    1. 검색어로 상품 검색
    2. 가격대별 티어 분류
    3. LLM으로 각 티어별 추천 상품 선택 및 이유 생성
    4. ValueRecommendation 반환

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 상태 딕셔너리
    """
    requirements = state.get("requirements")
    session_id = state.get("session_id", "")
    search_keywords = state.get("search_keywords", [])

    logger.info(f"[ValueAgent] 시작 - keywords: {search_keywords}")

    # 캐시 확인
    cache = get_cache()
    cache_key = cache.make_recommendation_key("VALUE", session_id, query=state.get("raw_query", ""))

    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info("[ValueAgent] 캐시 히트")
        return {
            "recommendations": cached_result,
            "cached": True,
            "processing_step": "value_completed",
        }

    try:
        # 1. 검색어 생성
        if not search_keywords:
            search_keywords = _generate_value_search_queries(requirements)

        logger.info(f"[ValueAgent] 검색 키워드: {search_keywords}")

        # 2. 상품 검색
        naver_client = get_naver_client()
        all_products: List[ProductCandidate] = []

        # 예산 범위 설정
        min_price = None
        max_price = None
        if requirements and requirements.budget:
            min_price = requirements.budget.min_price
            max_price = requirements.budget.max_price

        for query in search_keywords[:3]:  # 최대 3개 검색어
            try:
                # 가격순, 인기순으로 각각 검색
                for sort in ["sim", "asc"]:  # 정확도순, 가격낮은순
                    result = await naver_client.search(
                        query=query,
                        display=15,
                        sort=sort,
                        min_price=min_price,
                        max_price=max_price,
                    )
                    all_products.extend(result.items)
                    logger.info(f"[ValueAgent] 검색 완료: {query} ({sort}) - {len(result.items)}개")
            except NaverShoppingError as e:
                logger.warning(f"[ValueAgent] 검색 실패: {query} - {e}")
                continue

        if not all_products:
            logger.error("[ValueAgent] 검색 결과 없음")
            return {
                "recommendations": None,
                "error": "검색 결과가 없습니다. 다른 키워드로 시도해 주세요.",
                "processing_step": "value_failed",
            }

        # 중복 제거
        seen_ids = set()
        unique_products = []
        for p in all_products:
            if p.product_id not in seen_ids:
                seen_ids.add(p.product_id)
                unique_products.append(p)

        logger.info(f"[ValueAgent] 중복 제거 후 상품 수: {len(unique_products)}")

        # 3. 가격대별 분류
        tiered_products = _classify_by_price_tier(unique_products)

        # 4. LLM으로 추천 생성
        llm_provider = get_llm_provider()
        category = _extract_category(requirements, search_keywords)

        prompt = VALUE_RECOMMENDATION_PROMPT.format(
            category=category,
            search_keywords=", ".join(search_keywords),
            products=_build_product_list(unique_products),
        )

        messages = [
            SystemMessage(content="당신은 가성비 분석 전문가입니다. 정확한 JSON 형식으로만 응답하세요."),
            HumanMessage(content=prompt),
        ]

        logger.info("[ValueAgent] LLM 호출 중...")
        response = await llm_provider.generate(messages, temperature=0.5)

        # JSON 파싱
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        logger.info(f"[ValueAgent] LLM 응답 파싱 중...")
        llm_result = json.loads(response_text)

        # 5. ValueRecommendation 생성
        product_map = {p.product_id: p for p in unique_products}

        def build_tier_cards(tier_data: List[Dict], tier_name: str) -> List[RecommendationCard]:
            cards = []
            for rec in tier_data[:2]:  # 각 티어 최대 2개
                product_id = rec.get("product_id")
                if product_id in product_map:
                    card = _create_recommendation_card(
                        product=product_map[product_id],
                        reason=rec.get("recommendation_reason", "가성비가 좋은 상품입니다."),
                        warnings=rec.get("warnings", []),
                        tier=tier_name,
                        tier_benefits=rec.get("tier_benefits"),
                        tier_tradeoffs=rec.get("tier_tradeoffs"),
                    )
                    cards.append(card)
            return cards

        budget_cards = build_tier_cards(llm_result.get("budget_tier", []), "budget")
        standard_cards = build_tier_cards(llm_result.get("standard_tier", []), "standard")
        premium_cards = build_tier_cards(llm_result.get("premium_tier", []), "premium")

        # 카드가 부족하면 티어별 상품에서 보충
        def fill_tier_cards(
            cards: List[RecommendationCard],
            tier_products: List[ProductCandidate],
            tier_name: str,
            min_count: int = 1,
        ) -> List[RecommendationCard]:
            existing_ids = {c.product_id for c in cards}
            for p in tier_products:
                if len(cards) >= min_count:
                    break
                if p.product_id not in existing_ids:
                    cards.append(
                        _create_recommendation_card(
                            product=p,
                            reason=f"{tier_name} 가격대의 인기 상품입니다.",
                            warnings=[],
                            tier=tier_name,
                        )
                    )
            return cards

        budget_cards = fill_tier_cards(budget_cards, tiered_products["budget"], "budget")
        standard_cards = fill_tier_cards(standard_cards, tiered_products["standard"], "standard")
        premium_cards = fill_tier_cards(premium_cards, tiered_products["premium"], "premium")

        value_recommendation = ValueRecommendation(
            budget_tier=budget_cards,
            standard_tier=standard_cards,
            premium_tier=premium_cards,
            category=category,
        )

        logger.info(
            f"[ValueAgent] 완료 - budget: {len(budget_cards)}, standard: {len(standard_cards)}, premium: {len(premium_cards)}"
        )

        # 캐시 저장 (mode='json'으로 HttpUrl을 문자열로 변환)
        await cache.set(cache_key, value_recommendation.model_dump(mode='json'))

        return {
            "recommendations": value_recommendation.model_dump(mode='json'),
            "cached": False,
            "processing_step": "value_completed",
        }

    except json.JSONDecodeError as e:
        logger.error(f"[ValueAgent] JSON 파싱 실패: {e}")
        return {
            "recommendations": None,
            "error": f"응답 파싱 중 오류가 발생했습니다: {str(e)}",
            "processing_step": "value_failed",
        }
    except Exception as e:
        logger.error(f"[ValueAgent] 오류 발생: {e}", exc_info=True)
        return {
            "recommendations": None,
            "error": f"가성비 추천 생성 중 오류: {str(e)}",
            "processing_step": "value_failed",
        }


def _generate_value_search_queries(requirements: Any) -> List[str]:
    """가성비 검색어 생성"""
    queries = []

    if requirements and requirements.items:
        for item in requirements.items[:3]:
            queries.append(f"{item} 추천")
            queries.append(f"가성비 {item}")

    if not queries:
        queries = ["가성비 추천", "인기상품"]

    return queries[:5]
