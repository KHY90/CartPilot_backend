"""
TREND 에이전트
트렌드 추천 모드 구현
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.product import ProductCandidate
from app.models.recommendation import RecommendationCard, TrendingItem, TrendSignal
from app.services.cache import get_cache
from app.services.llm_provider import get_llm_provider
from app.services.naver_shopping import NaverShoppingError, get_naver_client

logger = logging.getLogger(__name__)

TREND_ANALYSIS_PROMPT = """당신은 쇼핑 트렌드 분석 전문가입니다.
사용자가 요즘 인기 있는 상품을 알고 싶어합니다.

카테고리: {category}
현재 날짜: {current_date}

검색된 인기 상품:
{products}

다음 형식으로 트렌드 분석을 작성하세요 (JSON만 출력):
{{
  "trending_items": [
    {{
      "category": "세부 카테고리",
      "keyword": "트렌드 키워드",
      "growth_rate": "+50%" 또는 "급상승" 등,
      "period": "최근 1개월",
      "target_segment": "주요 구매층 (예: 20-30대 직장인)",
      "why_trending": "인기 이유 설명",
      "recommended_products": ["추천 상품 ID 1", "추천 상품 ID 2"]
    }}
  ]
}}

분석 기준:
1. 최근 검색량 증가 추세
2. 시즌 트렌드 (계절, 연말 등)
3. 특정 연령대/성별 인기
4. SNS/유튜브 등 바이럴 트렌드

3-5개의 트렌드 아이템을 분석해주세요.
"""

# 시즌별 트렌드 키워드
SEASONAL_TRENDS = {
    "spring": ["미세먼지 마스크", "공기청정기", "봄옷", "러닝화", "골프용품"],
    "summer": ["선풍기", "에어컨", "여행용품", "수영복", "아이스박스"],
    "fall": ["가을옷", "등산용품", "김장용품", "난방기", "블랭킷"],
    "winter": ["패딩", "난방텐트", "가습기", "전기장판", "크리스마스 선물"],
}


def _get_current_season() -> str:
    """현재 계절 반환"""
    month = datetime.now().month
    if month in [3, 4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "summer"
    elif month in [9, 10, 11]:
        return "fall"
    else:
        return "winter"


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


async def trend_agent(state: AgentState) -> Dict[str, Any]:
    """
    TREND 에이전트 노드

    1. 트렌드 키워드로 상품 검색
    2. LLM으로 트렌드 분석 생성
    3. TrendSignal 반환
    """
    requirements = state.get("requirements")
    session_id = state.get("session_id", "")
    search_keywords = state.get("search_keywords", [])

    logger.info(f"[TrendAgent] 시작 - keywords: {search_keywords}")

    # 캐시 확인
    cache = get_cache()
    cache_key = cache.make_recommendation_key("TREND", session_id, query=state.get("raw_query", ""))

    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info("[TrendAgent] 캐시 히트")
        return {
            "recommendations": cached_result,
            "cached": True,
            "processing_step": "trend_completed",
        }

    try:
        # 1. 카테고리 추출
        category = "전체"
        if requirements and requirements.items:
            category = requirements.items[0]
        elif search_keywords:
            category = search_keywords[0].replace("요즘", "").replace("인기", "").replace("뭐 사", "").strip()
            if not category:
                category = "전체"

        logger.info(f"[TrendAgent] 카테고리: {category}")

        # 2. 트렌드 키워드 검색
        naver_client = get_naver_client()
        all_products: Dict[str, List[ProductCandidate]] = {}

        # 시즌 트렌드 키워드 가져오기
        current_season = _get_current_season()
        trend_keywords = SEASONAL_TRENDS.get(current_season, [])[:3]

        # 카테고리가 있으면 카테고리 기반 검색 추가
        if category != "전체":
            trend_keywords = [f"인기 {category}", f"{category} 추천"] + trend_keywords[:2]

        for keyword in trend_keywords:
            try:
                result = await naver_client.search(
                    query=keyword,
                    display=10,
                    sort="date",  # 최신순으로 트렌드 파악
                )
                all_products[keyword] = result.items
                logger.info(f"[TrendAgent] 검색 완료: {keyword} - {len(result.items)}개")
            except NaverShoppingError as e:
                logger.warning(f"[TrendAgent] 검색 실패: {keyword} - {e}")

        # 3. LLM으로 트렌드 분석
        llm_provider = get_llm_provider()

        # 상품 목록 문자열 생성
        products_str = ""
        for keyword, products in all_products.items():
            products_str += f"\n[{keyword}]\n"
            for i, p in enumerate(products[:5], 1):
                products_str += f"  {i}. [{p.product_id}] {p.title} - {_format_price(p.price)}\n"

        prompt = TREND_ANALYSIS_PROMPT.format(
            category=category,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            products=products_str if products_str else "검색 결과 없음",
        )

        messages = [
            SystemMessage(content="당신은 쇼핑 트렌드 분석 전문가입니다. 정확한 JSON 형식으로만 응답하세요."),
            HumanMessage(content=prompt),
        ]

        logger.info("[TrendAgent] LLM 호출 중...")
        response = await llm_provider.generate(messages, temperature=0.7)

        # JSON 파싱
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        llm_result = json.loads(response_text)

        # 4. TrendSignal 생성
        # 모든 상품을 하나의 맵으로
        product_map: Dict[str, ProductCandidate] = {}
        for products in all_products.values():
            for p in products:
                product_map[p.product_id] = p

        trending_items: List[TrendingItem] = []

        for item_data in llm_result.get("trending_items", [])[:5]:
            # 추천 상품 찾기
            recommended_ids = item_data.get("recommended_products", [])
            products: List[RecommendationCard] = []

            for pid in recommended_ids[:3]:
                if pid in product_map:
                    products.append(_create_recommendation_card(
                        product_map[pid],
                        item_data.get("why_trending", "트렌드 상품")
                    ))

            # 상품이 없으면 해당 키워드 검색 결과에서 가져오기
            if not products:
                keyword = item_data.get("keyword", "")
                for kw, prods in all_products.items():
                    if keyword.lower() in kw.lower() and prods:
                        products = [_create_recommendation_card(p, "트렌드 상품") for p in prods[:2]]
                        break

            trending_item = TrendingItem(
                category=item_data.get("category", category),
                keyword=item_data.get("keyword", ""),
                growth_rate=item_data.get("growth_rate"),
                period=item_data.get("period", "최근 1개월"),
                target_segment=item_data.get("target_segment"),
                products=products,
            )
            trending_items.append(trending_item)

        # 트렌드 아이템이 없으면 기본 생성
        if not trending_items:
            for keyword, products in list(all_products.items())[:3]:
                if products:
                    trending_items.append(TrendingItem(
                        category=category,
                        keyword=keyword,
                        growth_rate="인기",
                        period="최근 1개월",
                        target_segment=None,
                        products=[_create_recommendation_card(p, "인기 상품") for p in products[:2]],
                    ))

        trend_signal = TrendSignal(
            trending_items=trending_items,
            data_source="네이버 쇼핑",
            generated_at=datetime.now().isoformat(),
            disclaimer="트렌드는 빠르게 변할 수 있습니다. 인기 상품 ≠ 최저가입니다.",
        )

        logger.info(f"[TrendAgent] 완료 - {len(trending_items)}개 트렌드 아이템")

        # 캐시 저장
        await cache.set(cache_key, trend_signal.model_dump(mode='json'))

        return {
            "recommendations": trend_signal.model_dump(mode='json'),
            "cached": False,
            "processing_step": "trend_completed",
        }

    except json.JSONDecodeError as e:
        logger.error(f"[TrendAgent] JSON 파싱 실패: {e}")
        return {
            "recommendations": None,
            "error": f"응답 파싱 중 오류가 발생했습니다: {str(e)}",
            "processing_step": "trend_failed",
        }
    except Exception as e:
        logger.error(f"[TrendAgent] 오류 발생: {e}", exc_info=True)
        return {
            "recommendations": None,
            "error": f"트렌드 분석 중 오류: {str(e)}",
            "processing_step": "trend_failed",
        }
