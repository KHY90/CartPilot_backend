"""
키워드 확장 서비스
동의어/유사어를 활용한 검색 키워드 다양화
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class KeywordExpander:
    """검색 키워드 확장 서비스"""

    def __init__(self) -> None:
        self._synonyms: dict = {}
        self._load_synonyms()

    def _load_synonyms(self) -> None:
        """동의어 사전 로드"""
        synonyms_path = Path(__file__).parent.parent / "data" / "synonyms.json"

        try:
            if synonyms_path.exists():
                with open(synonyms_path, "r", encoding="utf-8") as f:
                    self._synonyms = json.load(f)
                logger.info(f"동의어 사전 로드 완료: {synonyms_path}")
            else:
                logger.warning(f"동의어 사전 파일 없음: {synonyms_path}")
        except Exception as e:
            logger.error(f"동의어 사전 로드 실패: {e}")
            self._synonyms = {}

    def expand_keyword(self, keyword: str, max_expansions: int = 3) -> List[str]:
        """
        단일 키워드를 확장

        Args:
            keyword: 원본 키워드
            max_expansions: 최대 확장 개수

        Returns:
            확장된 키워드 리스트 (원본 포함)
        """
        expanded: Set[str] = {keyword}

        # 카테고리에서 동의어 찾기
        categories = self._synonyms.get("categories", {})
        for main_word, synonyms in categories.items():
            # 정확히 일치하는 경우
            if keyword == main_word:
                for syn in synonyms[:max_expansions]:
                    expanded.add(syn)
                break
            # 키워드에 포함된 경우
            elif main_word in keyword:
                for syn in synonyms[:max_expansions]:
                    expanded.add(keyword.replace(main_word, syn))
                break
            # 동의어가 키워드인 경우
            elif keyword in synonyms:
                expanded.add(main_word)
                for syn in synonyms[:max_expansions]:
                    if syn != keyword:
                        expanded.add(syn)
                break

        # 속성 확장
        attributes = self._synonyms.get("attributes", {})
        for attr, synonyms in attributes.items():
            if attr in keyword:
                for syn in synonyms[:2]:
                    expanded.add(keyword.replace(attr, syn))

        return list(expanded)[:max_expansions + 1]

    def generate_fallback_keywords(
        self, original_keywords: List[str], category: Optional[str] = None
    ) -> List[str]:
        """
        검색 실패 시 대체 키워드 생성

        Args:
            original_keywords: 원본 키워드 리스트
            category: 상품 카테고리 (옵션)

        Returns:
            대체 키워드 리스트
        """
        fallbacks: List[str] = []

        for keyword in original_keywords:
            # 키워드 단순화 (수식어 제거)
            simplified = self._simplify_keyword(keyword)
            if simplified != keyword:
                fallbacks.append(simplified)

            # 동의어 기반 대체
            expanded = self.expand_keyword(keyword, max_expansions=2)
            for exp in expanded:
                if exp not in original_keywords and exp not in fallbacks:
                    fallbacks.append(exp)

        # 카테고리 기반 일반 키워드
        if category:
            categories = self._synonyms.get("categories", {})
            if category in categories:
                fallbacks.append(f"{category} 추천")
                fallbacks.append(f"인기 {category}")

        return fallbacks[:5]  # 최대 5개

    def _simplify_keyword(self, keyword: str) -> str:
        """키워드 단순화 (수식어 제거)"""
        # 흔한 수식어 제거
        modifiers = [
            "가성비", "추천", "인기", "베스트", "최고", "좋은", "괜찮은",
            "저렴한", "합리적인", "프리미엄", "고급", "선물용"
        ]
        result = keyword
        for mod in modifiers:
            result = result.replace(mod, "").strip()
        return result if result else keyword

    def expand_search_queries(
        self, keywords: List[str], max_total: int = 5
    ) -> List[str]:
        """
        검색어 리스트 확장

        Args:
            keywords: 원본 키워드 리스트
            max_total: 최대 결과 개수

        Returns:
            확장된 검색어 리스트
        """
        all_queries: List[str] = []

        for keyword in keywords:
            if keyword not in all_queries:
                all_queries.append(keyword)

            expanded = self.expand_keyword(keyword, max_expansions=2)
            for exp in expanded:
                if exp not in all_queries:
                    all_queries.append(exp)

        return all_queries[:max_total]


# 싱글톤 인스턴스
_keyword_expander: Optional[KeywordExpander] = None


def get_keyword_expander() -> KeywordExpander:
    """키워드 확장 서비스 싱글톤 반환"""
    global _keyword_expander
    if _keyword_expander is None:
        _keyword_expander = KeywordExpander()
    return _keyword_expander
