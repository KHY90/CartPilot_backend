"""
감정 분석 서비스
LLM 기반 리뷰 감정 분석 및 인사이트 추출
"""
import json
import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.models.review import (
    CategoryReviewInsights,
    CrawledReview,
    ProductReviewData,
    ReviewSentiment,
)
from app.services.llm_provider import get_llm_provider

logger = logging.getLogger(__name__)

# 배치 분석을 위한 최대 리뷰 수
MAX_REVIEWS_FOR_ANALYSIS = 20

SENTIMENT_ANALYSIS_PROMPT = """당신은 상품 리뷰 감정 분석 전문가입니다.
다음 리뷰들을 분석하여 감정과 핵심 인사이트를 추출하세요.

## 리뷰 목록
{reviews}

## 분석 요청
각 리뷰의 감정(positive/negative/neutral)을 분류하고,
전체 리뷰에서 공통적으로 언급되는 장점과 단점을 추출하세요.

## 응답 형식 (JSON만 출력)
```json
{{
  "sentiments": [
    {{
      "review_id": "리뷰ID",
      "sentiment": "positive|negative|neutral",
      "confidence": 0.0~1.0,
      "key_phrases": ["핵심 문구1", "핵심 문구2"]
    }}
  ],
  "common_praises": ["장점1", "장점2", "장점3"],
  "common_complaints": ["단점1", "단점2", "단점3"],
  "overall_sentiment": "positive|negative|mixed",
  "satisfaction_percentage": 0~100
}}
```

중요:
- 리뷰 내용에 기반하여 객관적으로 분석하세요
- 핵심 문구는 실제 리뷰에서 추출하세요
- 장단점은 2개 이상의 리뷰에서 언급된 것만 포함하세요
"""

CATEGORY_INSIGHTS_PROMPT = """당신은 상품 카테고리 분석 전문가입니다.
"{category}" 카테고리의 실제 리뷰 데이터를 분석하여 구매 인사이트를 제공하세요.

## 분석할 리뷰 데이터
총 {total_reviews}개 리뷰 분석

### 긍정 리뷰 샘플
{positive_samples}

### 부정 리뷰 샘플
{negative_samples}

### 통계 정보
- 평균 만족도: {satisfaction}%
- 주요 장점: {praises}
- 주요 단점: {complaints}

## 응답 형식 (JSON만 출력)
```json
{{
  "category": "{category}",
  "total_reviews_analyzed": {total_reviews},
  "average_satisfaction": 만족도(0~100),
  "common_praises": ["자주 언급되는 장점1", "장점2", "장점3"],
  "common_complaints": ["자주 언급되는 단점1", "단점2", "단점3"],
  "purchase_decision_factors": ["구매 결정 요소1", "요소2", "요소3"],
  "real_user_quotes": [
    {{"quote": "실제 사용자 인용문", "sentiment": "positive|negative"}},
    {{"quote": "다른 인용문", "sentiment": "positive|negative"}}
  ],
  "buyer_tips": ["구매 전 확인할 점1", "확인할 점2"],
  "best_for": ["이런 분에게 추천", "이런 용도에 적합"],
  "not_for": ["이런 분에게 비추천", "이런 상황에 부적합"]
}}
```

중요:
- 실제 리뷰 데이터에 기반하여 분석하세요
- 인용문은 실제 리뷰 내용을 요약/발췌하세요
- 구체적이고 실용적인 인사이트를 제공하세요
"""


class SentimentAnalyzer:
    """LLM 기반 감정 분석 서비스"""

    def __init__(self) -> None:
        self._llm_provider = get_llm_provider()

    async def analyze_reviews(
        self, reviews: List[CrawledReview]
    ) -> tuple[List[ReviewSentiment], dict]:
        """
        리뷰 배치 감정 분석

        Args:
            reviews: 분석할 리뷰 목록

        Returns:
            (감정 분석 결과 리스트, 요약 정보)
        """
        if not reviews:
            return [], {}

        # 분석할 리뷰 수 제한
        reviews_to_analyze = reviews[:MAX_REVIEWS_FOR_ANALYSIS]

        # 리뷰 텍스트 포맷팅
        reviews_text = "\n".join(
            [
                f"[ID: {r.review_id}] (별점: {r.rating or '없음'}) {r.content}"
                for r in reviews_to_analyze
            ]
        )

        prompt = SENTIMENT_ANALYSIS_PROMPT.format(reviews=reviews_text)

        try:
            messages = [
                SystemMessage(
                    content="당신은 리뷰 감정 분석 전문가입니다. JSON 형식으로만 응답하세요."
                ),
                HumanMessage(content=prompt),
            ]

            response = await self._llm_provider.generate(messages, temperature=0.3)

            # JSON 파싱
            response_text = self._extract_json(response)
            result = json.loads(response_text)

            # ReviewSentiment 객체 생성
            sentiments: List[ReviewSentiment] = []
            for s in result.get("sentiments", []):
                sentiments.append(
                    ReviewSentiment(
                        review_id=s.get("review_id", ""),
                        sentiment=s.get("sentiment", "neutral"),
                        confidence=float(s.get("confidence", 0.5)),
                        key_phrases=s.get("key_phrases", []),
                    )
                )

            summary = {
                "common_praises": result.get("common_praises", []),
                "common_complaints": result.get("common_complaints", []),
                "overall_sentiment": result.get("overall_sentiment", "mixed"),
                "satisfaction_percentage": result.get("satisfaction_percentage", 50),
            }

            logger.info(
                f"[SentimentAnalyzer] 분석 완료: {len(sentiments)}개, "
                f"전체 감정: {summary['overall_sentiment']}"
            )

            return sentiments, summary

        except Exception as e:
            logger.error(f"[SentimentAnalyzer] 분석 실패: {e}")
            return [], {}

    async def generate_category_insights(
        self,
        category: str,
        product_reviews: List[ProductReviewData],
    ) -> CategoryReviewInsights:
        """
        카테고리 전체 인사이트 생성

        Args:
            category: 상품 카테고리
            product_reviews: 상품별 리뷰 데이터 리스트

        Returns:
            CategoryReviewInsights
        """
        # 모든 리뷰 수집
        all_reviews: List[CrawledReview] = []
        for pr in product_reviews:
            all_reviews.extend(pr.reviews)

        if not all_reviews:
            return CategoryReviewInsights(
                category=category,
                total_reviews_analyzed=0,
                data_freshness="데이터 없음",
            )

        # 감정 분석 실행
        sentiments, summary = await self.analyze_reviews(all_reviews)

        # 긍정/부정 리뷰 분리
        positive_reviews = [
            r for r, s in zip(all_reviews, sentiments) if s.sentiment == "positive"
        ]
        negative_reviews = [
            r for r, s in zip(all_reviews, sentiments) if s.sentiment == "negative"
        ]

        # 샘플 추출
        positive_samples = "\n".join(
            [f"- {r.content[:100]}..." for r in positive_reviews[:3]]
        ) or "없음"
        negative_samples = "\n".join(
            [f"- {r.content[:100]}..." for r in negative_reviews[:3]]
        ) or "없음"

        # LLM으로 인사이트 생성
        prompt = CATEGORY_INSIGHTS_PROMPT.format(
            category=category,
            total_reviews=len(all_reviews),
            positive_samples=positive_samples,
            negative_samples=negative_samples,
            satisfaction=summary.get("satisfaction_percentage", 50),
            praises=", ".join(summary.get("common_praises", [])[:5]),
            complaints=", ".join(summary.get("common_complaints", [])[:5]),
        )

        try:
            messages = [
                SystemMessage(
                    content="당신은 상품 카테고리 분석 전문가입니다. JSON 형식으로만 응답하세요."
                ),
                HumanMessage(content=prompt),
            ]

            response = await self._llm_provider.generate(messages, temperature=0.4)

            # JSON 파싱
            response_text = self._extract_json(response)
            result = json.loads(response_text)

            # 출처별 리뷰 수 계산
            source_breakdown = {}
            for r in all_reviews:
                source_breakdown[r.source] = source_breakdown.get(r.source, 0) + 1

            insights = CategoryReviewInsights(
                category=result.get("category", category),
                total_reviews_analyzed=len(all_reviews),
                average_satisfaction=result.get("average_satisfaction"),
                common_praises=result.get("common_praises", [])[:5],
                common_complaints=result.get("common_complaints", [])[:5],
                purchase_decision_factors=result.get("purchase_decision_factors", [])[:5],
                real_user_quotes=result.get("real_user_quotes", [])[:4],
                data_freshness="실시간",
                source_breakdown=source_breakdown,
            )

            logger.info(
                f"[SentimentAnalyzer] 카테고리 인사이트 생성 완료: {category}, "
                f"{len(all_reviews)}개 리뷰 분석"
            )

            return insights

        except Exception as e:
            logger.error(f"[SentimentAnalyzer] 인사이트 생성 실패: {e}")
            return CategoryReviewInsights(
                category=category,
                total_reviews_analyzed=len(all_reviews),
                common_praises=summary.get("common_praises", []),
                common_complaints=summary.get("common_complaints", []),
                data_freshness="분석 실패",
            )

    def _extract_json(self, text: str) -> str:
        """응답에서 JSON 추출"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # 첫 줄과 마지막 ``` 제거
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text.strip()


# 싱글톤 인스턴스
_sentiment_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """감정 분석 서비스 싱글톤 반환"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer
