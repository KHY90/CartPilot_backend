"""
네이버 쇼핑 API 클라이언트
상품 검색 및 필터링 기능 제공
"""
import asyncio
import html
import logging
import re
from datetime import datetime
from typing import List, Optional, Set

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models.product import ProductCandidate, ProductSearchResult

logger = logging.getLogger(__name__)


class NaverShoppingError(Exception):
    """네이버 쇼핑 API 에러"""

    pass


class NaverShoppingClient:
    """네이버 쇼핑 API 클라이언트"""

    BASE_URL = "https://openapi.naver.com/v1/search/shop.json"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.naver_client_id
        self._client_secret = settings.naver_client_secret

        if not self._client_id or not self._client_secret:
            raise ValueError("NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 필요합니다")

    def _get_headers(self) -> dict:
        """API 헤더 반환"""
        return {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }

    @staticmethod
    def _clean_html(text: str) -> str:
        """HTML 태그 및 엔티티 제거"""
        # HTML 태그 제거
        clean = re.sub(r"<[^>]+>", "", text)
        # HTML 엔티티 디코딩
        clean = html.unescape(clean)
        return clean.strip()

    def _parse_product(self, item: dict) -> ProductCandidate:
        """API 응답을 ProductCandidate로 변환"""
        return ProductCandidate(
            product_id=item.get("productId", ""),
            title=self._clean_html(item.get("title", "")),
            link=item.get("link", ""),
            image=item.get("image") or None,
            price=int(item.get("lprice", 0)),
            high_price=int(item.get("hprice", 0)) if item.get("hprice") else None,
            mall_name=item.get("mallName", ""),
            brand=item.get("brand") or None,
            maker=item.get("maker") or None,
            category1=item.get("category1") or None,
            category2=item.get("category2") or None,
            category3=item.get("category3") or None,
            category4=item.get("category4") or None,
            fetched_at=datetime.utcnow().isoformat() + "Z",
        )

    def _should_exclude(self, item: dict, exclude_used: bool, exclude_rental: bool) -> bool:
        """상품 제외 여부 판단"""
        title = item.get("title", "").lower()
        mall_name = item.get("mallName", "").lower()

        # 중고 제외
        if exclude_used:
            used_keywords = ["중고", "리퍼", "반품", "재고", "전시"]
            if any(kw in title for kw in used_keywords):
                return True

        # 렌탈 제외
        if exclude_rental:
            rental_keywords = ["렌탈", "렌트", "대여", "월납"]
            if any(kw in title for kw in rental_keywords):
                return True

        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def search(
        self,
        query: str,
        display: int = 20,
        start: int = 1,
        sort: str = "sim",
        exclude_used: bool = True,
        exclude_rental: bool = True,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
    ) -> ProductSearchResult:
        """
        상품 검색

        Args:
            query: 검색어
            display: 결과 개수 (최대 100)
            start: 시작 위치 (최대 1000)
            sort: 정렬 방식 (sim: 정확도, date: 날짜, asc: 가격오름차순, dsc: 가격내림차순)
            exclude_used: 중고 제외 여부
            exclude_rental: 렌탈 제외 여부
            min_price: 최소 가격
            max_price: 최대 가격

        Returns:
            ProductSearchResult
        """
        params = {
            "query": query,
            "display": min(display * 2, 100),  # 필터링을 위해 더 많이 요청
            "start": start,
            "sort": sort,
        }

        # 가격 필터 (해외직구 제외 옵션과 함께 사용)
        if min_price:
            params["filter"] = "exclude_cbshop"  # 해외직구 제외

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.BASE_URL,
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code == 429:
                raise NaverShoppingError("API 호출 한도 초과")
            elif response.status_code == 401:
                raise NaverShoppingError("API 인증 실패")
            elif response.status_code != 200:
                raise NaverShoppingError(f"API 오류: {response.status_code}")

            data = response.json()

        # 상품 파싱 및 필터링
        items: List[ProductCandidate] = []
        for item in data.get("items", []):
            # 제외 필터
            if self._should_exclude(item, exclude_used, exclude_rental):
                continue

            # 가격 필터
            price = int(item.get("lprice", 0))
            if min_price and price < min_price:
                continue
            if max_price and price > max_price:
                continue

            items.append(self._parse_product(item))

            # 요청된 개수만큼만 반환
            if len(items) >= display:
                break

        return ProductSearchResult(
            total=data.get("total", 0),
            items=items,
            query=query,
            sort=sort,
            cached=False,
        )

    async def search_with_fallback(
        self,
        queries: List[str],
        display: int = 20,
        sort: str = "sim",
        exclude_used: bool = True,
        exclude_rental: bool = True,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_results: int = 5,
    ) -> ProductSearchResult:
        """
        다중 키워드 검색 및 결과 병합

        Args:
            queries: 검색어 리스트 (우선순위 순)
            display: 최종 결과 개수
            sort: 정렬 방식
            exclude_used: 중고 제외
            exclude_rental: 렌탈 제외
            min_price: 최소 가격
            max_price: 최대 가격
            min_results: 최소 결과 개수 (이 이하면 다음 키워드로 검색)

        Returns:
            ProductSearchResult (병합된 결과)
        """
        all_items: List[ProductCandidate] = []
        seen_ids: Set[str] = set()
        used_queries: List[str] = []

        for query in queries:
            if len(all_items) >= display:
                break

            try:
                result = await self.search(
                    query=query,
                    display=display - len(all_items),
                    sort=sort,
                    exclude_used=exclude_used,
                    exclude_rental=exclude_rental,
                    min_price=min_price,
                    max_price=max_price,
                )

                # 중복 제거하며 추가
                for item in result.items:
                    if item.product_id not in seen_ids:
                        seen_ids.add(item.product_id)
                        all_items.append(item)

                used_queries.append(query)
                logger.info(
                    f"검색 '{query}': {len(result.items)}개 결과, 총 {len(all_items)}개"
                )

                # 충분한 결과가 있으면 중단
                if len(all_items) >= min_results:
                    break

            except NaverShoppingError as e:
                logger.warning(f"검색 실패 '{query}': {e}")
                continue
            except Exception as e:
                logger.error(f"예상치 못한 오류 '{query}': {e}")
                continue

        return ProductSearchResult(
            total=len(all_items),
            items=all_items[:display],
            query=", ".join(used_queries) if used_queries else queries[0],
            sort=sort,
            cached=False,
        )

    async def search_multiple(
        self,
        queries: List[str],
        display_per_query: int = 10,
        max_total: int = 30,
        sort: str = "sim",
        exclude_used: bool = True,
        exclude_rental: bool = True,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
    ) -> ProductSearchResult:
        """
        여러 키워드 병렬 검색 및 결과 병합

        Args:
            queries: 검색어 리스트
            display_per_query: 키워드당 결과 개수
            max_total: 최대 총 결과 개수
            sort: 정렬 방식
            exclude_used: 중고 제외
            exclude_rental: 렌탈 제외
            min_price: 최소 가격
            max_price: 최대 가격

        Returns:
            ProductSearchResult (병합된 결과)
        """
        # 병렬 검색 태스크 생성
        tasks = [
            self.search(
                query=query,
                display=display_per_query,
                sort=sort,
                exclude_used=exclude_used,
                exclude_rental=exclude_rental,
                min_price=min_price,
                max_price=max_price,
            )
            for query in queries[:5]  # 최대 5개 키워드
        ]

        # 병렬 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 병합 및 중복 제거
        all_items: List[ProductCandidate] = []
        seen_ids: Set[str] = set()

        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"검색 실패: {result}")
                continue

            for item in result.items:
                if item.product_id not in seen_ids:
                    seen_ids.add(item.product_id)
                    all_items.append(item)

        # 가격순 또는 관련도순 정렬
        if sort == "asc":
            all_items.sort(key=lambda x: x.price)
        elif sort == "dsc":
            all_items.sort(key=lambda x: x.price, reverse=True)

        return ProductSearchResult(
            total=len(all_items),
            items=all_items[:max_total],
            query=", ".join(queries),
            sort=sort,
            cached=False,
        )


# 싱글톤 인스턴스
_naver_client: Optional[NaverShoppingClient] = None


def get_naver_client() -> NaverShoppingClient:
    """네이버 쇼핑 클라이언트 싱글톤 반환"""
    global _naver_client
    if _naver_client is None:
        _naver_client = NaverShoppingClient()
    return _naver_client
