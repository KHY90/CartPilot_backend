"""
BUNDLE 에이전트
묶음 구매 최적화 모드 구현
"""
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.product import ProductCandidate
from app.models.recommendation import BundleCombination, BundleItem, BundleRecommendation, RecommendationCard
from app.services.cache import get_cache
from app.services.llm_provider import get_llm_provider
from app.services.naver_shopping import NaverShoppingError, get_naver_client

logger = logging.getLogger(__name__)

BUNDLE_RECOMMENDATION_PROMPT = """당신은 묶음 구매 최적화 전문가입니다.
사용자가 여러 품목을 총 예산 내에서 구매하려고 합니다.
주어진 상품 목록에서 최적의 조합을 만들어주세요.

품목 목록: {items}
총 예산: {budget}

각 품목별 검색된 상품:
{products_by_category}

다음 형식으로 2-3개의 조합을 추천하세요 (JSON만 출력):
{{
  "combinations": [
    {{
      "combination_id": "A",
      "description": "이 조합의 특징 설명",
      "items": [
        {{
          "item_category": "품목명",
          "selected_product_id": "선택한 상품 ID",
          "reason": "이 상품을 선택한 이유"
        }}
      ],
      "budget_fit": true/false,
      "adjustment_note": "예산 초과 시 조정 방법 (optional)"
    }}
  ]
}}

조합 기준:
1. 조합 A: 예산 최적화 (가장 저렴하게)
2. 조합 B: 균형 (가성비 중심)
3. 조합 C: 프리미엄 (품질 우선, 예산 약간 초과 가능)

각 조합에서 모든 품목이 포함되어야 합니다.
"""


def _format_price(price: int) -> str:
    """가격을 한국어 형식으로 포맷"""
    return f"{price:,}원"


def _create_recommendation_card(product: ProductCandidate, reason: str = "") -> RecommendationCard:
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
        warnings=[],
    )


async def bundle_agent(state: AgentState) -> Dict[str, Any]:
    """
    BUNDLE 에이전트 노드

    1. 각 품목별로 상품 검색
    2. LLM으로 최적 조합 생성
    3. BundleRecommendation 반환
    """
    requirements = state.get("requirements")
    session_id = state.get("session_id", "")
    search_keywords = state.get("search_keywords", [])

    logger.info(f"[BundleAgent] 시작 - keywords: {search_keywords}")

    # 캐시 확인
    cache = get_cache()
    cache_key = cache.make_recommendation_key("BUNDLE", session_id, query=state.get("raw_query", ""))

    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info("[BundleAgent] 캐시 히트")
        return {
            "recommendations": cached_result,
            "cached": True,
            "processing_step": "bundle_completed",
        }

    try:
        # 품목 목록 추출
        items = []
        if requirements and requirements.items:
            items = requirements.items
        elif search_keywords:
            # 검색 키워드에서 품목 추출
            items = [kw.replace("추천", "").replace("가성비", "").strip() for kw in search_keywords]

        if not items:
            return {
                "recommendations": None,
                "error": "구매할 품목을 알려주세요. 예: 노트북+마우스+키보드 100만원",
                "processing_step": "bundle_failed",
            }

        # 예산 추출
        total_budget = None
        if requirements and requirements.budget:
            total_budget = requirements.budget.total_budget or requirements.budget.max_price

        if not total_budget:
            total_budget = 1000000  # 기본 100만원

        logger.info(f"[BundleAgent] 품목: {items}, 예산: {total_budget}")

        # 2. 각 품목별 상품 검색
        naver_client = get_naver_client()
        products_by_category: Dict[str, List[ProductCandidate]] = {}

        for item in items[:5]:  # 최대 5개 품목
            try:
                result = await naver_client.search(
                    query=item,
                    display=10,
                    sort="sim",
                )
                products_by_category[item] = result.items
                logger.info(f"[BundleAgent] 검색 완료: {item} - {len(result.items)}개")
            except NaverShoppingError as e:
                logger.warning(f"[BundleAgent] 검색 실패: {item} - {e}")
                products_by_category[item] = []

        # 검색 결과가 없는 경우
        if not any(products_by_category.values()):
            return {
                "recommendations": None,
                "error": "검색 결과가 없습니다. 다른 품목명으로 시도해 주세요.",
                "processing_step": "bundle_failed",
            }

        # 3. LLM으로 조합 생성
        llm_provider = get_llm_provider()

        # 품목별 상품 목록 문자열 생성
        products_str = ""
        for category, products in products_by_category.items():
            products_str += f"\n[{category}]\n"
            for i, p in enumerate(products[:10], 1):
                products_str += f"  {i}. [{p.product_id}] {p.title} - {_format_price(p.price)}\n"

        prompt = BUNDLE_RECOMMENDATION_PROMPT.format(
            items=", ".join(items),
            budget=_format_price(total_budget),
            products_by_category=products_str,
        )

        messages = [
            SystemMessage(content="당신은 묶음 구매 최적화 전문가입니다. 정확한 JSON 형식으로만 응답하세요."),
            HumanMessage(content=prompt),
        ]

        logger.info("[BundleAgent] LLM 호출 중...")
        response = await llm_provider.generate(messages, temperature=0.5)

        # JSON 파싱
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        llm_result = json.loads(response_text)

        # 4. BundleRecommendation 생성
        # 모든 상품을 하나의 맵으로
        all_products: Dict[str, ProductCandidate] = {}
        for products in products_by_category.values():
            for p in products:
                all_products[p.product_id] = p

        combinations: List[BundleCombination] = []

        for combo_data in llm_result.get("combinations", [])[:3]:
            bundle_items: List[BundleItem] = []
            total_price = 0

            for item_data in combo_data.get("items", []):
                category = item_data.get("item_category", "")
                product_id = item_data.get("selected_product_id", "")
                reason = item_data.get("reason", "")

                if product_id in all_products:
                    product = all_products[product_id]
                    total_price += product.price

                    # 대체 상품 (같은 카테고리에서 다른 상품)
                    alternatives = []
                    if category in products_by_category:
                        for alt in products_by_category[category]:
                            if alt.product_id != product_id and len(alternatives) < 2:
                                alternatives.append(_create_recommendation_card(alt))

                    bundle_item = BundleItem(
                        item_category=category,
                        product=_create_recommendation_card(product, reason),
                        alternatives=alternatives,
                    )
                    bundle_items.append(bundle_item)

            if bundle_items:
                combination = BundleCombination(
                    combination_id=combo_data.get("combination_id", "A"),
                    items=bundle_items,
                    total_price=total_price,
                    total_display=_format_price(total_price),
                    budget_fit=total_price <= total_budget,
                    adjustment_note=combo_data.get("adjustment_note"),
                )
                combinations.append(combination)

        # 조합이 없으면 기본 조합 생성
        if not combinations:
            bundle_items = []
            total_price = 0
            for category, products in products_by_category.items():
                if products:
                    product = products[0]
                    total_price += product.price
                    bundle_items.append(BundleItem(
                        item_category=category,
                        product=_create_recommendation_card(product, "기본 추천 상품"),
                        alternatives=[_create_recommendation_card(p) for p in products[1:3]],
                    ))

            if bundle_items:
                combinations.append(BundleCombination(
                    combination_id="A",
                    items=bundle_items,
                    total_price=total_price,
                    total_display=_format_price(total_price),
                    budget_fit=total_price <= total_budget,
                ))

        bundle_recommendation = BundleRecommendation(
            combinations=combinations,
            total_budget=total_budget,
            items_count=len(items),
        )

        logger.info(f"[BundleAgent] 완료 - {len(combinations)}개 조합 생성")

        # 캐시 저장
        await cache.set(cache_key, bundle_recommendation.model_dump(mode='json'))

        return {
            "recommendations": bundle_recommendation.model_dump(mode='json'),
            "cached": False,
            "processing_step": "bundle_completed",
        }

    except json.JSONDecodeError as e:
        logger.error(f"[BundleAgent] JSON 파싱 실패: {e}")
        return {
            "recommendations": None,
            "error": f"응답 파싱 중 오류가 발생했습니다: {str(e)}",
            "processing_step": "bundle_failed",
        }
    except Exception as e:
        logger.error(f"[BundleAgent] 오류 발생: {e}", exc_info=True)
        return {
            "recommendations": None,
            "error": f"묶음 추천 생성 중 오류: {str(e)}",
            "processing_step": "bundle_failed",
        }
