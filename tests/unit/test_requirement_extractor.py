"""
요구사항 추출기 유닛 테스트
"""
import pytest
from app.utils.text_parser import (
    extract_budget,
    extract_items,
    extract_recipient_info,
    parse_user_input,
)


class TestBudgetExtraction:
    """예산 추출 테스트"""

    def test_extract_korean_currency(self):
        """한국어 금액 표현 추출"""
        budget = extract_budget("5만원")
        assert budget is not None
        assert budget.total_budget == 50000

    def test_extract_korean_currency_with_won(self):
        """'원' 단위 포함 추출"""
        budget = extract_budget("50000원")
        assert budget is not None
        # 5만원 범위 내로 파싱될 것
        assert budget.total_budget is not None

    def test_extract_budget_range(self):
        """예산 범위 추출"""
        budget = extract_budget("3~5만원")
        assert budget is not None
        assert budget.min_price == 30000
        assert budget.max_price == 50000

    def test_extract_flexible_budget(self):
        """유연한 예산 표현"""
        budget = extract_budget("약 5만원 정도")
        assert budget is not None
        assert budget.is_flexible is True

    def test_extract_large_budget(self):
        """큰 금액 추출"""
        budget = extract_budget("100만원")
        assert budget is not None
        assert budget.total_budget == 1000000

    def test_no_budget(self):
        """예산 정보 없음"""
        budget = extract_budget("좋은 키보드 추천해줘")
        assert budget is None


class TestItemExtraction:
    """품목 추출 테스트"""

    def test_extract_single_item(self):
        """단일 품목 추출"""
        items = extract_items("무선 키보드 추천해줘")
        assert "키보드" in items

    def test_extract_multiple_items_with_plus(self):
        """+ 구분자로 여러 품목 추출"""
        items = extract_items("노트북+마우스+키보드")
        assert len(items) >= 3
        assert "노트북" in items
        assert "마우스" in items
        assert "키보드" in items

    def test_extract_common_items(self):
        """일반적인 품목 추출"""
        items = extract_items("에어프라이어 사고 싶어")
        assert "에어프라이어" in items


class TestRecipientExtraction:
    """선물 대상 정보 추출 테스트"""

    def test_extract_colleague_male_30s(self):
        """30대 남자 동료 추출"""
        recipient = extract_recipient_info("30대 남자 동료 퇴사 선물")
        assert recipient is not None
        assert recipient.gender == "male"
        assert recipient.age_group == "30대"
        assert recipient.relation == "colleague"
        assert recipient.occasion == "farewell"

    def test_extract_girlfriend_birthday(self):
        """여자친구 생일 추출"""
        recipient = extract_recipient_info("여자친구 생일 선물")
        assert recipient is not None
        assert recipient.gender == "female"
        assert recipient.relation == "girlfriend"
        assert recipient.occasion == "birthday"

    def test_extract_parents(self):
        """부모님 추출"""
        recipient = extract_recipient_info("부모님 결혼기념일 선물")
        assert recipient is not None
        assert recipient.relation == "parent"
        assert recipient.occasion == "anniversary"

    def test_no_recipient_info(self):
        """대상 정보 없음"""
        recipient = extract_recipient_info("키보드 추천해줘")
        assert recipient is None


class TestGiftContextExtraction:
    """선물 컨텍스트 통합 추출 테스트"""

    def test_full_gift_context(self):
        """전체 선물 컨텍스트 추출"""
        budget, items, recipient = parse_user_input("30대 남자 동료 퇴사 선물 5만원")

        # 예산 확인
        assert budget is not None
        assert budget.total_budget == 50000

        # 대상 정보 확인
        assert recipient is not None
        assert recipient.gender == "male"
        assert recipient.age_group == "30대"
        assert recipient.relation == "colleague"
        assert recipient.occasion == "farewell"

    def test_partial_gift_context(self):
        """부분 선물 컨텍스트 추출"""
        budget, items, recipient = parse_user_input("친구 선물 추천")

        # 대상 정보만 있음
        assert recipient is not None
        assert recipient.relation == "friend"

        # 예산은 없음
        assert budget is None
