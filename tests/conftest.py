"""
pytest 공통 fixture
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """테스트 클라이언트"""
    return TestClient(app)


@pytest.fixture
def sample_gift_query():
    """GIFT 모드 샘플 쿼리"""
    return "30대 남자 동료 퇴사 선물 5만원"


@pytest.fixture
def sample_value_query():
    """VALUE 모드 샘플 쿼리"""
    return "가성비 무선 키보드 추천해줘"


@pytest.fixture
def sample_bundle_query():
    """BUNDLE 모드 샘플 쿼리"""
    return "노트북+마우스+키보드 100만원에 맞춰줘"


@pytest.fixture
def sample_review_query():
    """REVIEW 모드 샘플 쿼리"""
    return "에어프라이어 사도 돼?"


@pytest.fixture
def sample_trend_query():
    """TREND 모드 샘플 쿼리"""
    return "요즘 뭐 사?"
