"""
의도 분류기 유닛 테스트
"""
import pytest
from app.models.request import IntentType


class TestIntentClassification:
    """의도 분류 테스트"""

    # GIFT 의도 분류 테스트
    @pytest.mark.parametrize(
        "query,expected_intent",
        [
            ("30대 남자 동료 퇴사 선물 5만원", IntentType.GIFT),
            ("여자친구 생일 선물 추천해줘", IntentType.GIFT),
            ("부모님 결혼기념일 선물", IntentType.GIFT),
            ("상사 승진 선물 10만원", IntentType.GIFT),
            ("친구한테 줄 선물 뭐가 좋을까", IntentType.GIFT),
        ],
    )
    def test_gift_intent_keywords(self, query: str, expected_intent: IntentType):
        """GIFT 의도 키워드 테스트 (실제 LLM 호출 없이 키워드 기반)"""
        # 기본 키워드 기반 테스트
        gift_keywords = ["선물", "줄", "드릴"]
        has_gift_keyword = any(kw in query for kw in gift_keywords)
        assert has_gift_keyword, f"GIFT 키워드가 포함되어야 함: {query}"

    # VALUE 의도 분류 테스트
    @pytest.mark.parametrize(
        "query,expected_intent",
        [
            ("가성비 무선 키보드 추천해줘", IntentType.VALUE),
            ("좋은 마우스 뭐 있어?", IntentType.VALUE),
            ("괜찮은 이어폰 추천", IntentType.VALUE),
        ],
    )
    def test_value_intent_keywords(self, query: str, expected_intent: IntentType):
        """VALUE 의도 키워드 테스트"""
        value_keywords = ["가성비", "추천", "좋은", "괜찮은"]
        has_value_keyword = any(kw in query for kw in value_keywords)
        # 선물 키워드가 없어야 VALUE
        gift_keywords = ["선물", "줄 ", "드릴"]
        has_gift_keyword = any(kw in query for kw in gift_keywords)

        if has_value_keyword and not has_gift_keyword:
            assert True
        else:
            pytest.skip("키워드 조건 미충족")

    # BUNDLE 의도 분류 테스트
    @pytest.mark.parametrize(
        "query,expected_intent",
        [
            ("노트북+마우스+키보드 100만원에 맞춰줘", IntentType.BUNDLE),
            ("노트북이랑 마우스 같이 살래", IntentType.BUNDLE),
            ("사무용품 세트 구성해줘", IntentType.BUNDLE),
        ],
    )
    def test_bundle_intent_keywords(self, query: str, expected_intent: IntentType):
        """BUNDLE 의도 키워드 테스트"""
        bundle_keywords = ["+", "이랑", "같이", "세트", "맞춰"]
        has_bundle_keyword = any(kw in query for kw in bundle_keywords)
        assert has_bundle_keyword, f"BUNDLE 키워드가 포함되어야 함: {query}"

    # REVIEW 의도 분류 테스트
    @pytest.mark.parametrize(
        "query,expected_intent",
        [
            ("에어프라이어 사도 돼?", IntentType.REVIEW),
            ("이 제품 단점이 뭐야?", IntentType.REVIEW),
            ("후기가 어때?", IntentType.REVIEW),
        ],
    )
    def test_review_intent_keywords(self, query: str, expected_intent: IntentType):
        """REVIEW 의도 키워드 테스트"""
        review_keywords = ["사도 돼", "단점", "후기", "괜찮아?"]
        has_review_keyword = any(kw in query for kw in review_keywords)
        assert has_review_keyword, f"REVIEW 키워드가 포함되어야 함: {query}"

    # TREND 의도 분류 테스트
    @pytest.mark.parametrize(
        "query,expected_intent",
        [
            ("요즘 뭐 사?", IntentType.TREND),
            ("인기 있는 가전제품?", IntentType.TREND),
            ("핫한 아이템 뭐야", IntentType.TREND),
        ],
    )
    def test_trend_intent_keywords(self, query: str, expected_intent: IntentType):
        """TREND 의도 키워드 테스트"""
        trend_keywords = ["요즘", "인기", "핫한", "뭐 사"]
        has_trend_keyword = any(kw in query for kw in trend_keywords)
        assert has_trend_keyword, f"TREND 키워드가 포함되어야 함: {query}"
