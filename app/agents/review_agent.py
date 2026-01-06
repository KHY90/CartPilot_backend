"""
REVIEW 에이전트
리뷰 기반 검증 모드 구현 - 실제 리뷰 데이터 크롤링 및 분석
"""
import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.models.product import ProductCandidate
from app.models.recommendation import ReviewAnalysis, ReviewComplaint
from app.models.review import CategoryReviewInsights
from app.services.cache import get_cache
from app.services.llm_provider import get_llm_provider
from app.services.naver_shopping import NaverShoppingError, get_naver_client
from app.services.review_crawler import get_review_crawler
from app.services.sentiment_analyzer import get_sentiment_analyzer

logger = logging.getLogger(__name__)

REVIEW_ANALYSIS_PROMPT = """당신은 제품 리뷰 분석 전문가입니다.
사용자가 "{product_category}" 구매를 고민하고 있습니다.
이 제품군의 일반적인 장단점과 구매 전 고려사항을 분석해주세요.

검색된 상품 목록 (참고용):
{products}

다음 형식으로 분석 결과를 작성하세요 (JSON만 출력):
{{
  "product_category": "제품 카테고리명",
  "top_complaints": [
    {{
      "rank": 1,
      "issue": "가장 흔한 불만/단점",
      "frequency": "많음/보통/적음",
      "severity": "high/medium/low"
    }},
    {{
      "rank": 2,
      "issue": "두 번째 불만/단점",
      "frequency": "많음/보통/적음",
      "severity": "high/medium/low"
    }},
    {{
      "rank": 3,
      "issue": "세 번째 불만/단점",
      "frequency": "많음/보통/적음",
      "severity": "high/medium/low"
    }}
  ],
  "not_recommended_conditions": [
    "이런 경우에는 구매 비추천 1",
    "이런 경우에는 구매 비추천 2"
  ],
  "management_tips": [
    "관리/사용 팁 1",
    "관리/사용 팁 2"
  ],
  "overall_sentiment": "positive/mixed/negative",
  "purchase_recommendation": "구매 추천 여부와 이유 (2-3문장)"
}}

분석 기준:
1. 해당 제품군의 일반적인 장단점
2. 자주 언급되는 불만 사항
3. 특정 상황에서의 적합성
4. 구매 후 관리 팁
"""


def _format_price(price: int) -> str:
    """가격을 한국어 형식으로 포맷"""
    return f"{price:,}원"


def _build_product_list(products: List[ProductCandidate]) -> str:
    """상품 목록 문자열 생성"""
    lines = []
    for i, p in enumerate(products[:15], 1):
        brand = f" [{p.brand}]" if p.brand else ""
        lines.append(f"{i}. {p.title}{brand} - {_format_price(p.price)} ({p.mall_name})")
    return "\n".join(lines)


async def review_agent(state: AgentState) -> Dict[str, Any]:
    """
    REVIEW 에이전트 노드 - 실제 리뷰 데이터 기반 분석

    1. 제품 카테고리 검색
    2. 실제 리뷰 데이터 크롤링 (옵션)
    3. LLM으로 감정 분석 및 인사이트 생성
    4. ReviewAnalysis + 실제 리뷰 인사이트 반환
    """
    requirements = state.get("requirements")
    session_id = state.get("session_id", "")
    search_keywords = state.get("search_keywords", [])

    logger.info(f"[ReviewAgent] 시작 - keywords: {search_keywords}")

    # 캐시 확인
    cache = get_cache()
    cache_key = cache.make_recommendation_key("REVIEW", session_id, query=state.get("raw_query", ""))

    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info("[ReviewAgent] 캐시 히트")
        return {
            "recommendations": cached_result,
            "cached": True,
            "processing_step": "review_completed",
        }

    try:
        # 1. 제품 카테고리 추출
        product_category = ""
        if requirements and requirements.items:
            product_category = requirements.items[0]
        elif search_keywords:
            # 검색 키워드에서 카테고리 추출
            product_category = search_keywords[0].replace("사도 돼", "").replace("괜찮아", "").replace("?", "").strip()

        if not product_category:
            return {
                "recommendations": None,
                "error": "어떤 제품이 궁금하신가요? 예: 에어프라이어 사도 돼?",
                "processing_step": "review_failed",
            }

        logger.info(f"[ReviewAgent] 제품 카테고리: {product_category}")

        # 2. 상품 검색
        naver_client = get_naver_client()
        products: List[ProductCandidate] = []

        try:
            result = await naver_client.search(
                query=product_category,
                display=15,
                sort="sim",
            )
            products = result.items
            logger.info(f"[ReviewAgent] 검색 완료: {len(products)}개")
        except NaverShoppingError as e:
            logger.warning(f"[ReviewAgent] 검색 실패: {e}")

        # 3. 실제 리뷰 크롤링 시도 (선택적)
        real_review_insights: CategoryReviewInsights | None = None
        try:
            if products:
                review_crawler = get_review_crawler()
                sentiment_analyzer = get_sentiment_analyzer()

                # 상위 5개 상품의 리뷰 크롤링
                product_links = [
                    {
                        "id": p.product_id,
                        "title": p.title,
                        "link": str(p.link),
                    }
                    for p in products[:5]
                ]

                logger.info("[ReviewAgent] 리뷰 크롤링 시작...")
                product_reviews = await review_crawler.crawl_category_reviews(
                    category=product_category,
                    product_links=product_links,
                    max_products=3,  # 속도를 위해 3개로 제한
                    max_reviews_per_product=10,
                )

                # 리뷰가 있으면 인사이트 생성
                total_reviews = sum(len(pr.reviews) for pr in product_reviews)
                if total_reviews > 0:
                    logger.info(f"[ReviewAgent] {total_reviews}개 리뷰 분석 중...")
                    real_review_insights = await sentiment_analyzer.generate_category_insights(
                        category=product_category,
                        product_reviews=product_reviews,
                    )
                    logger.info(f"[ReviewAgent] 실제 리뷰 인사이트 생성 완료")
        except Exception as e:
            logger.warning(f"[ReviewAgent] 리뷰 크롤링/분석 실패 (fallback 진행): {e}")

        # 4. LLM으로 기본 리뷰 분석 생성
        llm_provider = get_llm_provider()

        # 실제 리뷰 인사이트가 있으면 프롬프트에 포함
        additional_context = ""
        if real_review_insights and real_review_insights.total_reviews_analyzed > 0:
            additional_context = f"""

실제 크롤링된 리뷰 데이터 ({real_review_insights.total_reviews_analyzed}개):
- 주요 장점: {', '.join(real_review_insights.common_praises[:3])}
- 주요 단점: {', '.join(real_review_insights.common_complaints[:3])}
- 만족도: {real_review_insights.average_satisfaction}%

이 실제 데이터를 반영하여 분석하세요.
"""

        prompt = REVIEW_ANALYSIS_PROMPT.format(
            product_category=product_category,
            products=_build_product_list(products) if products else "검색 결과 없음",
        ) + additional_context

        messages = [
            SystemMessage(content="당신은 제품 리뷰 분석 전문가입니다. 정확한 JSON 형식으로만 응답하세요."),
            HumanMessage(content=prompt),
        ]

        logger.info("[ReviewAgent] LLM 호출 중...")
        response = await llm_provider.generate(messages, temperature=0.5)

        # JSON 파싱
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        llm_result = json.loads(response_text)

        # 5. ReviewAnalysis 생성
        top_complaints = []
        for complaint_data in llm_result.get("top_complaints", [])[:5]:
            complaint = ReviewComplaint(
                rank=complaint_data.get("rank", len(top_complaints) + 1),
                issue=complaint_data.get("issue", ""),
                frequency=complaint_data.get("frequency", "보통"),
                severity=complaint_data.get("severity", "medium"),
            )
            top_complaints.append(complaint)

        # 실제 리뷰 데이터 기반 불만 사항 보강
        if real_review_insights and real_review_insights.common_complaints:
            for idx, complaint in enumerate(real_review_insights.common_complaints[:3]):
                if not any(c.issue == complaint for c in top_complaints):
                    top_complaints.append(
                        ReviewComplaint(
                            rank=len(top_complaints) + 1,
                            issue=complaint,
                            frequency="실제 리뷰 기반",
                            severity="medium",
                        )
                    )

        # 기본 불만 사항 추가 (없는 경우)
        if not top_complaints:
            top_complaints = [
                ReviewComplaint(rank=1, issue="구체적인 리뷰 정보가 부족합니다", frequency="보통", severity="low"),
            ]

        # 면책 조항 생성
        disclaimer = "이 분석은 일반적인 리뷰 정보를 기반으로 합니다."
        if real_review_insights and real_review_insights.total_reviews_analyzed > 0:
            disclaimer = f"이 분석은 실제 {real_review_insights.total_reviews_analyzed}개 리뷰 데이터를 기반으로 합니다."

        review_analysis = ReviewAnalysis(
            product_category=llm_result.get("product_category", product_category),
            top_complaints=top_complaints[:5],  # 최대 5개
            not_recommended_conditions=llm_result.get("not_recommended_conditions", []),
            management_tips=llm_result.get("management_tips", []),
            overall_sentiment=llm_result.get("overall_sentiment", "mixed"),
            disclaimer=disclaimer,
        )

        logger.info(f"[ReviewAgent] 완료 - sentiment: {review_analysis.overall_sentiment}")

        # 6. 결과 구성 (실제 리뷰 인사이트 포함)
        result_data = review_analysis.model_dump(mode='json')

        # 실제 리뷰 인사이트 추가
        if real_review_insights:
            result_data["real_review_insights"] = {
                "total_reviews_analyzed": real_review_insights.total_reviews_analyzed,
                "average_satisfaction": real_review_insights.average_satisfaction,
                "common_praises": real_review_insights.common_praises,
                "common_complaints": real_review_insights.common_complaints,
                "purchase_decision_factors": real_review_insights.purchase_decision_factors,
                "real_user_quotes": real_review_insights.real_user_quotes,
                "data_freshness": real_review_insights.data_freshness,
                "source_breakdown": real_review_insights.source_breakdown,
            }

        # 캐시 저장
        await cache.set(cache_key, result_data)

        return {
            "recommendations": result_data,
            "cached": False,
            "processing_step": "review_completed",
        }

    except json.JSONDecodeError as e:
        logger.error(f"[ReviewAgent] JSON 파싱 실패: {e}")
        return {
            "recommendations": None,
            "error": f"응답 파싱 중 오류가 발생했습니다: {str(e)}",
            "processing_step": "review_failed",
        }
    except Exception as e:
        logger.error(f"[ReviewAgent] 오류 발생: {e}", exc_info=True)
        return {
            "recommendations": None,
            "error": f"리뷰 분석 중 오류: {str(e)}",
            "processing_step": "review_failed",
        }
