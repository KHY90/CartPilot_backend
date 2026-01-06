"""
리뷰 크롤러 서비스
네이버 쇼핑 상품 리뷰 크롤링 (httpx + BeautifulSoup)
"""
import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.models.review import CrawledReview, ProductReviewData, ReviewSummary
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

# Rate limiting 설정
RATE_LIMIT_DELAY = 1.0  # 요청 간 최소 대기 시간 (초)
MAX_REVIEWS_PER_PRODUCT = 30  # 상품당 최대 리뷰 수
CACHE_TTL_HOURS = 24  # 캐시 유효 시간 (시간)


class ReviewCrawlerError(Exception):
    """리뷰 크롤러 에러"""
    pass


class ReviewCrawler:
    """네이버 쇼핑 리뷰 크롤러"""

    # 네이버 쇼핑 리뷰 API 엔드포인트 (비공식)
    REVIEW_API_BASE = "https://search.shopping.naver.com/api/review"

    # User-Agent 설정
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        self._last_request_time: float = 0
        self._cache = get_cache()

    def _get_headers(self) -> dict:
        """HTTP 헤더 반환"""
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": "https://search.shopping.naver.com/",
        }

    async def _rate_limit(self) -> None:
        """Rate limiting 적용"""
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            await asyncio.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    def _generate_review_id(self, product_id: str, content: str, date: str) -> str:
        """리뷰 ID 생성 (해시 기반)"""
        unique_str = f"{product_id}:{content[:50]}:{date}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    async def crawl_product_reviews(
        self,
        product_id: str,
        product_title: str,
        product_link: str,
        max_reviews: int = MAX_REVIEWS_PER_PRODUCT,
    ) -> ProductReviewData:
        """
        특정 상품의 리뷰 크롤링

        Args:
            product_id: 상품 ID
            product_title: 상품명
            product_link: 상품 링크
            max_reviews: 최대 크롤링 리뷰 수

        Returns:
            ProductReviewData
        """
        # 캐시 확인
        cache_key = f"reviews:product:{product_id}"
        cached = await self._cache.get(cache_key)
        if cached:
            logger.info(f"[ReviewCrawler] 캐시 히트: {product_id}")
            return ProductReviewData(**cached)

        logger.info(f"[ReviewCrawler] 크롤링 시작: {product_title[:30]}...")

        reviews: List[CrawledReview] = []

        try:
            # Rate limiting 적용
            await self._rate_limit()

            # 네이버 쇼핑 상품 페이지에서 리뷰 데이터 추출
            reviews = await self._fetch_naver_reviews(
                product_id, product_link, max_reviews
            )

            logger.info(f"[ReviewCrawler] 크롤링 완료: {len(reviews)}개 리뷰")

        except Exception as e:
            logger.warning(f"[ReviewCrawler] 크롤링 실패: {e}")
            # 실패해도 빈 데이터 반환 (fallback)

        # 리뷰 요약 생성
        summary = self._generate_summary(product_id, reviews)

        # 결과 생성
        cache_valid_until = (
            datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)
        ).isoformat() + "Z"

        result = ProductReviewData(
            product_id=product_id,
            product_title=product_title,
            reviews=reviews,
            summary=summary,
            sentiments=[],  # 감정 분석은 별도 서비스에서 처리
            cache_valid_until=cache_valid_until,
        )

        # 캐시 저장
        await self._cache.set(
            cache_key, result.model_dump(mode="json"), ttl=CACHE_TTL_HOURS * 3600
        )

        return result

    async def _fetch_naver_reviews(
        self, product_id: str, product_link: str, max_reviews: int
    ) -> List[CrawledReview]:
        """네이버 쇼핑 리뷰 가져오기"""
        reviews: List[CrawledReview] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # 상품 페이지 요청
                response = await client.get(
                    product_link,
                    headers=self._get_headers(),
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    logger.warning(
                        f"[ReviewCrawler] 페이지 요청 실패: {response.status_code}"
                    )
                    return reviews

                # HTML 파싱
                soup = BeautifulSoup(response.text, "html.parser")
                reviews = self._parse_reviews_from_html(soup, product_id, max_reviews)

        except httpx.TimeoutException:
            logger.warning("[ReviewCrawler] 요청 타임아웃")
        except Exception as e:
            logger.warning(f"[ReviewCrawler] 요청 실패: {e}")

        return reviews

    def _parse_reviews_from_html(
        self, soup: BeautifulSoup, product_id: str, max_reviews: int
    ) -> List[CrawledReview]:
        """HTML에서 리뷰 파싱"""
        reviews: List[CrawledReview] = []

        # 네이버 쇼핑 리뷰 컨테이너 찾기 (여러 선택자 시도)
        review_selectors = [
            ".reviewItems_list_review__q3hvH",  # 새로운 UI
            ".review_list",  # 구 UI
            "[class*='review']",  # 일반적인 리뷰 클래스
        ]

        review_elements = []
        for selector in review_selectors:
            review_elements = soup.select(selector)
            if review_elements:
                break

        for idx, elem in enumerate(review_elements[:max_reviews]):
            try:
                # 리뷰 내용 추출
                content_elem = (
                    elem.select_one(".reviewItems_text__XrSSf")
                    or elem.select_one(".review_content")
                    or elem.select_one("[class*='text']")
                )
                content = content_elem.get_text(strip=True) if content_elem else ""

                if not content or len(content) < 5:
                    continue

                # 별점 추출
                rating = None
                rating_elem = elem.select_one("[class*='star']") or elem.select_one(
                    "[class*='rating']"
                )
                if rating_elem:
                    rating_text = rating_elem.get_text()
                    rating_match = re.search(r"(\d)", rating_text)
                    if rating_match:
                        rating = int(rating_match.group(1))

                # 날짜 추출
                date = None
                date_elem = elem.select_one("[class*='date']") or elem.select_one(
                    "time"
                )
                if date_elem:
                    date = date_elem.get_text(strip=True)

                # 작성자 추출 (익명화)
                author = None
                author_elem = elem.select_one("[class*='user']") or elem.select_one(
                    "[class*='author']"
                )
                if author_elem:
                    original_author = author_elem.get_text(strip=True)
                    # 익명화: 첫 글자만 표시
                    if len(original_author) > 0:
                        author = original_author[0] + "***"

                review_id = self._generate_review_id(
                    product_id, content, date or str(idx)
                )

                reviews.append(
                    CrawledReview(
                        review_id=review_id,
                        product_id=product_id,
                        content=content[:500],  # 최대 500자
                        rating=rating,
                        author=author,
                        date=date,
                        helpful_count=0,
                        purchase_verified=True,  # 네이버 쇼핑은 구매자 리뷰만 표시
                        source="naver",
                    )
                )

            except Exception as e:
                logger.debug(f"[ReviewCrawler] 리뷰 파싱 실패: {e}")
                continue

        return reviews

    def _generate_summary(
        self, product_id: str, reviews: List[CrawledReview]
    ) -> ReviewSummary:
        """리뷰 요약 생성"""
        total = len(reviews)

        if total == 0:
            return ReviewSummary(
                product_id=product_id,
                total_reviews=0,
            )

        # 별점 분포 계산
        rating_dist = {str(i): 0 for i in range(1, 6)}
        ratings = []
        for r in reviews:
            if r.rating:
                rating_dist[str(r.rating)] += 1
                ratings.append(r.rating)

        avg_rating = sum(ratings) / len(ratings) if ratings else None

        return ReviewSummary(
            product_id=product_id,
            total_reviews=total,
            average_rating=round(avg_rating, 1) if avg_rating else None,
            rating_distribution=rating_dist,
        )

    async def crawl_category_reviews(
        self,
        category: str,
        product_links: List[dict],
        max_products: int = 5,
        max_reviews_per_product: int = 10,
    ) -> List[ProductReviewData]:
        """
        카테고리 내 여러 상품 리뷰 크롤링

        Args:
            category: 상품 카테고리
            product_links: 상품 정보 리스트 [{'id': ..., 'title': ..., 'link': ...}]
            max_products: 최대 상품 수
            max_reviews_per_product: 상품당 최대 리뷰 수

        Returns:
            List[ProductReviewData]
        """
        results: List[ProductReviewData] = []

        for product in product_links[:max_products]:
            try:
                data = await self.crawl_product_reviews(
                    product_id=product.get("id", ""),
                    product_title=product.get("title", ""),
                    product_link=product.get("link", ""),
                    max_reviews=max_reviews_per_product,
                )
                results.append(data)

                # Rate limiting
                await self._rate_limit()

            except Exception as e:
                logger.warning(f"[ReviewCrawler] 상품 크롤링 실패: {e}")
                continue

        return results


# 싱글톤 인스턴스
_review_crawler: Optional[ReviewCrawler] = None


def get_review_crawler() -> ReviewCrawler:
    """리뷰 크롤러 싱글톤 반환"""
    global _review_crawler
    if _review_crawler is None:
        _review_crawler = ReviewCrawler()
    return _review_crawler
