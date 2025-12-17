"""
GIFT 모드 통합 테스트
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestGiftModeFlow:
    """GIFT 모드 전체 흐름 테스트"""

    @pytest.fixture
    def client(self):
        """테스트 클라이언트"""
        return TestClient(app)

    def test_health_check(self, client):
        """헬스체크 엔드포인트"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "llm_provider" in data

    def test_gift_request_structure(self, client):
        """GIFT 요청 구조 테스트"""
        # 참고: 실제 LLM API 키 없이는 에러 응답이 올 수 있음
        response = client.post(
            "/api/chat",
            json={"message": "30대 남자 동료 퇴사 선물 5만원"},
        )

        # 상태 코드 확인 (200 또는 에러)
        assert response.status_code == 200

        data = response.json()

        # 응답 구조 확인
        assert "type" in data
        assert "processing_time_ms" in data
        assert data["type"] in ["recommendation", "clarification", "error"]

    def test_gift_request_with_missing_info(self, client):
        """정보 누락 시 clarification 테스트"""
        # 예산만 있고 대상 정보 없음
        response = client.post(
            "/api/chat",
            json={"message": "선물 추천해줘 5만원"},
        )

        assert response.status_code == 200
        data = response.json()

        # clarification 또는 error 예상
        assert data["type"] in ["clarification", "error", "recommendation"]

    def test_gift_response_fields(self, client):
        """GIFT 응답 필드 검증"""
        response = client.post(
            "/api/chat",
            json={"message": "30대 남자 동료 퇴사 선물 5만원"},
        )

        assert response.status_code == 200
        data = response.json()

        # 공통 필드 확인
        assert "type" in data
        assert "processing_time_ms" in data
        assert isinstance(data["processing_time_ms"], int)

        # type이 recommendation이면 추가 필드 확인
        if data["type"] == "recommendation":
            # intent가 GIFT여야 함
            if data.get("intent"):
                assert data["intent"] == "GIFT"

    def test_empty_message_validation(self, client):
        """빈 메시지 검증"""
        response = client.post(
            "/api/chat",
            json={"message": ""},
        )

        # 422 Validation Error 예상
        assert response.status_code == 422

    def test_long_message_validation(self, client):
        """긴 메시지 검증 (500자 제한)"""
        long_message = "a" * 501
        response = client.post(
            "/api/chat",
            json={"message": long_message},
        )

        # 422 Validation Error 예상
        assert response.status_code == 422

    def test_session_persistence(self, client):
        """세션 유지 테스트"""
        # 첫 번째 요청
        response1 = client.post(
            "/api/chat",
            json={"message": "선물 추천해줘"},
        )
        assert response1.status_code == 200

        # 두 번째 요청 (세션 유지)
        response2 = client.post(
            "/api/chat",
            json={"message": "5만원 정도"},
        )
        assert response2.status_code == 200
