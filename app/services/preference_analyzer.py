"""
사용자 성향 분석 서비스
별점, 구매 기록, 관심상품을 기반으로 개인화 성향 추출
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import Counter

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.rating import ProductRating
from app.models.purchase import PurchaseRecord
from app.models.wishlist import WishlistItem

logger = logging.getLogger(__name__)


class UserPreferences:
    """사용자 성향 데이터"""

    def __init__(self):
        # 가격 성향
        self.avg_purchase_price: Optional[float] = None
        self.price_range_min: Optional[int] = None
        self.price_range_max: Optional[int] = None
        self.price_sensitivity: str = "medium"  # low, medium, high

        # 카테고리 선호
        self.preferred_categories: list[str] = []
        self.category_weights: dict[str, float] = {}

        # 별점 분석
        self.avg_rating: Optional[float] = None
        self.high_rated_keywords: list[str] = []  # 높게 평가한 상품에서 추출한 키워드

        # 구매 패턴
        self.purchase_frequency: str = "medium"  # low, medium, high
        self.recent_purchases: list[str] = []

        # 브랜드/쇼핑몰 선호
        self.preferred_malls: list[str] = []

        # 메타데이터
        self.data_points: int = 0  # 분석에 사용된 데이터 수
        self.analyzed_at: Optional[datetime] = None

    def to_prompt_context(self) -> str:
        """LLM 프롬프트에 포함할 성향 문자열 생성"""
        if self.data_points == 0:
            return "사용자 구매/평가 이력이 없습니다."

        lines = []

        # 가격 성향
        if self.avg_purchase_price:
            lines.append(f"- 평균 구매가: {int(self.avg_purchase_price):,}원")
            if self.price_range_min and self.price_range_max:
                lines.append(f"- 선호 가격대: {self.price_range_min:,}원 ~ {self.price_range_max:,}원")
            lines.append(f"- 가격 민감도: {self._kr_sensitivity(self.price_sensitivity)}")

        # 카테고리 선호
        if self.preferred_categories:
            cats = ", ".join(self.preferred_categories[:5])
            lines.append(f"- 선호 카테고리: {cats}")

        # 별점 분석
        if self.avg_rating:
            lines.append(f"- 평균 평점: {self.avg_rating:.1f}점")
        if self.high_rated_keywords:
            keywords = ", ".join(self.high_rated_keywords[:5])
            lines.append(f"- 높게 평가한 상품 유형: {keywords}")

        # 구매 패턴
        lines.append(f"- 구매 빈도: {self._kr_frequency(self.purchase_frequency)}")

        # 쇼핑몰 선호
        if self.preferred_malls:
            malls = ", ".join(self.preferred_malls[:3])
            lines.append(f"- 선호 쇼핑몰: {malls}")

        if not lines:
            return "사용자 성향 데이터 부족"

        return "사용자 성향:\n" + "\n".join(lines)

    def _kr_sensitivity(self, level: str) -> str:
        return {"low": "낮음 (가격보다 품질 중시)", "medium": "보통", "high": "높음 (가성비 중시)"}.get(level, level)

    def _kr_frequency(self, level: str) -> str:
        return {"low": "가끔 구매", "medium": "보통", "high": "자주 구매"}.get(level, level)

    def to_dict(self) -> dict:
        """API 응답용 딕셔너리"""
        return {
            "avg_purchase_price": self.avg_purchase_price,
            "price_range": {
                "min": self.price_range_min,
                "max": self.price_range_max,
            },
            "price_sensitivity": self.price_sensitivity,
            "preferred_categories": self.preferred_categories,
            "avg_rating": self.avg_rating,
            "high_rated_keywords": self.high_rated_keywords,
            "purchase_frequency": self.purchase_frequency,
            "preferred_malls": self.preferred_malls,
            "data_points": self.data_points,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }


class PreferenceAnalyzer:
    """사용자 성향 분석기"""

    # 분석 기간 (일)
    ANALYSIS_PERIOD_DAYS = 180

    async def analyze(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserPreferences:
        """
        사용자 성향 분석

        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID

        Returns:
            UserPreferences 객체
        """
        prefs = UserPreferences()
        cutoff_date = datetime.utcnow() - timedelta(days=self.ANALYSIS_PERIOD_DAYS)

        try:
            # 1. 구매 기록 분석
            await self._analyze_purchases(db, user_id, cutoff_date, prefs)

            # 2. 별점 분석
            await self._analyze_ratings(db, user_id, prefs)

            # 3. 관심상품 분석
            await self._analyze_wishlist(db, user_id, prefs)

            # 4. 가격 민감도 계산
            self._calculate_price_sensitivity(prefs)

            prefs.analyzed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"성향 분석 실패: {e}")

        return prefs

    async def _analyze_purchases(
        self,
        db: AsyncSession,
        user_id: str,
        cutoff_date: datetime,
        prefs: UserPreferences,
    ) -> None:
        """구매 기록 분석"""
        # 구매 통계
        stmt = select(
            func.count(PurchaseRecord.id),
            func.avg(PurchaseRecord.price),
            func.min(PurchaseRecord.price),
            func.max(PurchaseRecord.price),
        ).where(
            and_(
                PurchaseRecord.user_id == user_id,
                PurchaseRecord.purchased_at >= cutoff_date,
            )
        )
        result = await db.execute(stmt)
        row = result.one()

        purchase_count = row[0] or 0
        if purchase_count > 0:
            prefs.avg_purchase_price = float(row[1])
            prefs.price_range_min = int(row[2])
            prefs.price_range_max = int(row[3])
            prefs.data_points += purchase_count

            # 구매 빈도 계산
            if purchase_count >= 10:
                prefs.purchase_frequency = "high"
            elif purchase_count >= 3:
                prefs.purchase_frequency = "medium"
            else:
                prefs.purchase_frequency = "low"

        # 카테고리 분석
        cat_stmt = select(
            PurchaseRecord.category,
            func.count(PurchaseRecord.id).label("count"),
        ).where(
            and_(
                PurchaseRecord.user_id == user_id,
                PurchaseRecord.category.isnot(None),
            )
        ).group_by(PurchaseRecord.category).order_by(func.count(PurchaseRecord.id).desc()).limit(10)

        cat_result = await db.execute(cat_stmt)
        categories = cat_result.all()

        if categories:
            total = sum(c[1] for c in categories)
            prefs.preferred_categories = [c[0] for c in categories[:5]]
            prefs.category_weights = {c[0]: c[1] / total for c in categories}

        # 쇼핑몰 분석
        mall_stmt = select(
            PurchaseRecord.mall_name,
            func.count(PurchaseRecord.id),
        ).where(
            and_(
                PurchaseRecord.user_id == user_id,
                PurchaseRecord.mall_name.isnot(None),
            )
        ).group_by(PurchaseRecord.mall_name).order_by(func.count(PurchaseRecord.id).desc()).limit(5)

        mall_result = await db.execute(mall_stmt)
        malls = mall_result.all()
        prefs.preferred_malls = [m[0] for m in malls if m[0]]

        # 최근 구매 상품
        recent_stmt = select(PurchaseRecord.product_name).where(
            PurchaseRecord.user_id == user_id
        ).order_by(PurchaseRecord.purchased_at.desc()).limit(5)

        recent_result = await db.execute(recent_stmt)
        prefs.recent_purchases = [r[0] for r in recent_result.all()]

    async def _analyze_ratings(
        self,
        db: AsyncSession,
        user_id: str,
        prefs: UserPreferences,
    ) -> None:
        """별점 분석"""
        # 평균 별점
        avg_stmt = select(func.avg(ProductRating.rating)).where(
            ProductRating.user_id == user_id
        )
        avg_result = await db.execute(avg_stmt)
        avg = avg_result.scalar()
        if avg:
            prefs.avg_rating = float(avg)

        # 높게 평가한 상품 (4점 이상) 분석
        high_rated_stmt = select(ProductRating.product_name).where(
            and_(
                ProductRating.user_id == user_id,
                ProductRating.rating >= 4,
            )
        ).limit(20)

        high_rated_result = await db.execute(high_rated_stmt)
        high_rated_names = [r[0] for r in high_rated_result.all()]

        if high_rated_names:
            prefs.data_points += len(high_rated_names)
            # 상품명에서 키워드 추출 (간단한 단어 빈도 분석)
            keywords = self._extract_keywords(high_rated_names)
            prefs.high_rated_keywords = keywords

    async def _analyze_wishlist(
        self,
        db: AsyncSession,
        user_id: str,
        prefs: UserPreferences,
    ) -> None:
        """관심상품 분석"""
        stmt = select(
            func.count(WishlistItem.id),
            func.avg(WishlistItem.current_price),
        ).where(WishlistItem.user_id == user_id)

        result = await db.execute(stmt)
        row = result.one()

        wishlist_count = row[0] or 0
        if wishlist_count > 0:
            prefs.data_points += wishlist_count

            # 관심상품 평균가로 가격 범위 보정
            wishlist_avg = row[1]
            if wishlist_avg and prefs.avg_purchase_price:
                # 두 평균의 가중치 적용
                prefs.avg_purchase_price = (
                    prefs.avg_purchase_price * 0.7 + float(wishlist_avg) * 0.3
                )
            elif wishlist_avg:
                prefs.avg_purchase_price = float(wishlist_avg)

    def _calculate_price_sensitivity(self, prefs: UserPreferences) -> None:
        """가격 민감도 계산"""
        if not prefs.avg_purchase_price:
            prefs.price_sensitivity = "medium"
            return

        # 평균 구매가 기준 민감도 판단
        avg = prefs.avg_purchase_price

        if avg < 20000:
            prefs.price_sensitivity = "high"
        elif avg > 100000:
            prefs.price_sensitivity = "low"
        else:
            prefs.price_sensitivity = "medium"

    def _extract_keywords(self, product_names: list[str]) -> list[str]:
        """상품명에서 키워드 추출"""
        # 불용어 목록
        stopwords = {
            "세트", "선물", "추천", "인기", "베스트", "특가", "무료배송",
            "증정", "할인", "정품", "국내", "해외", "당일", "무료",
            "한정", "1+1", "2+1", "신상", "사은품", "이벤트",
        }

        word_counts = Counter()
        for name in product_names:
            # 간단한 토큰화 (공백, 특수문자 기준)
            import re
            words = re.findall(r"[가-힣a-zA-Z0-9]+", name)
            for word in words:
                if len(word) >= 2 and word not in stopwords:
                    word_counts[word] += 1

        # 상위 키워드 반환
        common = word_counts.most_common(10)
        return [word for word, count in common if count >= 2]


# 싱글톤 인스턴스
_analyzer: Optional[PreferenceAnalyzer] = None


def get_preference_analyzer() -> PreferenceAnalyzer:
    """성향 분석기 싱글톤 반환"""
    global _analyzer
    if _analyzer is None:
        _analyzer = PreferenceAnalyzer()
    return _analyzer
