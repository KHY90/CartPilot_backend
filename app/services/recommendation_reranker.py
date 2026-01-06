"""
추천 결과 재정렬 서비스
사용자 성향을 기반으로 추천 결과를 개인화 재정렬
"""
import logging
from typing import List, Optional

from app.models.product import ProductCandidate
from app.services.preference_analyzer import UserPreferences

logger = logging.getLogger(__name__)


class RecommendationReranker:
    """추천 결과 개인화 재정렬"""

    def rerank(
        self,
        products: List[ProductCandidate],
        preferences: Optional[UserPreferences],
        intent: str = "VALUE",
        max_results: int = 20,
    ) -> List[ProductCandidate]:
        """
        사용자 성향 기반 결과 재정렬

        Args:
            products: 원본 상품 리스트
            preferences: 사용자 성향 (없으면 원본 순서 유지)
            intent: 의도 유형 (GIFT, VALUE, BUNDLE 등)
            max_results: 최대 반환 개수

        Returns:
            재정렬된 상품 리스트
        """
        if not products:
            return []

        if not preferences or preferences.data_points == 0:
            logger.debug("[Reranker] 성향 데이터 없음, 원본 순서 유지")
            return products[:max_results]

        # 각 상품에 개인화 점수 부여
        scored_products = []
        for product in products:
            score = self._calculate_personalization_score(product, preferences, intent)
            scored_products.append((product, score))

        # 점수 기준 내림차순 정렬
        scored_products.sort(key=lambda x: x[1], reverse=True)

        # 결과 추출
        reranked = [p for p, _ in scored_products[:max_results]]

        logger.info(
            f"[Reranker] {len(products)}개 상품 재정렬 완료, "
            f"intent={intent}, preferences_data_points={preferences.data_points}"
        )

        return reranked

    def _calculate_personalization_score(
        self,
        product: ProductCandidate,
        prefs: UserPreferences,
        intent: str,
    ) -> float:
        """개인화 점수 계산"""
        score = 50.0  # 기본 점수

        # 1. 가격 선호도 점수 (최대 +/- 20점)
        price_score = self._price_preference_score(product.price, prefs)
        score += price_score

        # 2. 카테고리 선호도 점수 (최대 +15점)
        category_score = self._category_preference_score(product, prefs)
        score += category_score

        # 3. 쇼핑몰 선호도 점수 (최대 +10점)
        mall_score = self._mall_preference_score(product.mall_name, prefs)
        score += mall_score

        # 4. 브랜드/키워드 매칭 점수 (최대 +15점)
        keyword_score = self._keyword_matching_score(product.title, prefs)
        score += keyword_score

        # 5. 의도별 추가 가중치
        if intent == "GIFT":
            # 선물용은 가격대 적합성 추가 가중
            if prefs.avg_purchase_price and product.price:
                price_diff_ratio = abs(product.price - prefs.avg_purchase_price) / max(
                    prefs.avg_purchase_price, 1
                )
                if price_diff_ratio < 0.3:  # 평균 가격의 30% 이내
                    score += 5

        elif intent == "VALUE":
            # 가성비는 가격 민감도 고려
            if prefs.price_sensitivity == "high":
                # 가격 민감도 높으면 저가 상품 가중
                if product.price < (prefs.avg_purchase_price or 50000):
                    score += 10
            elif prefs.price_sensitivity == "low":
                # 가격 민감도 낮으면 고가 상품도 허용
                score += 5

        return score

    def _price_preference_score(self, price: int, prefs: UserPreferences) -> float:
        """가격 선호도 점수"""
        if not price or not prefs.avg_purchase_price:
            return 0

        avg = prefs.avg_purchase_price

        # 가격이 선호 범위 내에 있으면 가산점
        if prefs.price_range_min and prefs.price_range_max:
            if prefs.price_range_min <= price <= prefs.price_range_max:
                return 15  # 선호 범위 내

        # 평균 구매가 대비 편차에 따른 점수
        diff_ratio = abs(price - avg) / max(avg, 1)

        if diff_ratio < 0.2:  # 20% 이내
            return 20
        elif diff_ratio < 0.5:  # 50% 이내
            return 10
        elif diff_ratio < 1.0:  # 100% 이내
            return 0
        else:
            return -10  # 크게 벗어남

    def _category_preference_score(
        self, product: ProductCandidate, prefs: UserPreferences
    ) -> float:
        """카테고리 선호도 점수"""
        if not prefs.preferred_categories:
            return 0

        # 상품 카테고리 확인
        product_categories = [
            product.category1,
            product.category2,
            product.category3,
            product.category4,
        ]
        product_categories = [c for c in product_categories if c]

        for cat in product_categories:
            if cat in prefs.preferred_categories:
                # 선호 카테고리 순위에 따른 점수
                idx = prefs.preferred_categories.index(cat)
                return max(15 - idx * 3, 5)  # 1위: 15점, 2위: 12점, ...

            # 부분 일치 확인
            for pref_cat in prefs.preferred_categories:
                if pref_cat in cat or cat in pref_cat:
                    return 8

        return 0

    def _mall_preference_score(self, mall_name: str, prefs: UserPreferences) -> float:
        """쇼핑몰 선호도 점수"""
        if not mall_name or not prefs.preferred_malls:
            return 0

        if mall_name in prefs.preferred_malls:
            idx = prefs.preferred_malls.index(mall_name)
            return max(10 - idx * 2, 4)  # 1위: 10점, 2위: 8점, ...

        return 0

    def _keyword_matching_score(self, title: str, prefs: UserPreferences) -> float:
        """키워드 매칭 점수"""
        if not title or not prefs.high_rated_keywords:
            return 0

        title_lower = title.lower()
        matched = 0

        for keyword in prefs.high_rated_keywords:
            if keyword.lower() in title_lower:
                matched += 1

        # 매칭 키워드 수에 따른 점수
        if matched >= 3:
            return 15
        elif matched >= 2:
            return 10
        elif matched >= 1:
            return 5

        return 0

    def get_personalization_insights(
        self, products: List[ProductCandidate], preferences: Optional[UserPreferences]
    ) -> dict:
        """
        개인화 인사이트 생성 (UI 표시용)

        Returns:
            {
                "personalized": bool,
                "matched_categories": list,
                "matched_malls": list,
                "price_match_count": int,
                "total_products": int,
            }
        """
        if not preferences or preferences.data_points == 0:
            return {
                "personalized": False,
                "matched_categories": [],
                "matched_malls": [],
                "price_match_count": 0,
                "total_products": len(products),
            }

        matched_categories = set()
        matched_malls = set()
        price_match_count = 0

        for product in products:
            # 카테고리 매칭
            for cat in [
                product.category1,
                product.category2,
                product.category3,
                product.category4,
            ]:
                if cat and cat in preferences.preferred_categories:
                    matched_categories.add(cat)

            # 쇼핑몰 매칭
            if product.mall_name and product.mall_name in preferences.preferred_malls:
                matched_malls.add(product.mall_name)

            # 가격 매칭
            if preferences.price_range_min and preferences.price_range_max:
                if preferences.price_range_min <= product.price <= preferences.price_range_max:
                    price_match_count += 1

        return {
            "personalized": True,
            "matched_categories": list(matched_categories),
            "matched_malls": list(matched_malls),
            "price_match_count": price_match_count,
            "total_products": len(products),
        }


# 싱글톤 인스턴스
_reranker: Optional[RecommendationReranker] = None


def get_recommendation_reranker() -> RecommendationReranker:
    """재정렬 서비스 싱글톤 반환"""
    global _reranker
    if _reranker is None:
        _reranker = RecommendationReranker()
    return _reranker
