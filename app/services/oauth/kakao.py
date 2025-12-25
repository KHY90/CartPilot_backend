"""
카카오 OAuth 서비스
https://developers.kakao.com/docs/latest/ko/kakaologin/rest-api
"""

from typing import Optional
from urllib.parse import urlencode
import httpx

from app.config import get_settings
from app.services.oauth.base import BaseOAuthService, OAuthUserInfo

settings = get_settings()


class KakaoOAuthService(BaseOAuthService):
    """카카오 OAuth 서비스"""

    AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"

    @property
    def provider_name(self) -> str:
        return "kakao"

    def get_authorization_url(self, state: str) -> str:
        """카카오 로그인 인증 URL 생성"""
        params = {
            "client_id": settings.kakao_client_id,
            "redirect_uri": settings.kakao_redirect_uri,
            "response_type": "code",
            "state": state,
            # talk_message 스코프 추가: "나에게 보내기" 기능 사용
            "scope": "profile_nickname profile_image account_email talk_message",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def get_access_token(self, code: str) -> dict:
        """
        인증 코드로 액세스 토큰 교환

        Returns:
            dict: {
                "access_token": str,
                "refresh_token": str (optional),
                "expires_in": int (기본 21599초 = 약 6시간)
            }
        """
        # 기본 요청 데이터
        request_data = {
            "grant_type": "authorization_code",
            "client_id": settings.kakao_client_id,
            "redirect_uri": settings.kakao_redirect_uri,
            "code": code,
        }

        # client_secret은 선택적 (카카오에서 더 이상 필수 아님)
        if settings.kakao_client_secret:
            request_data["client_secret"] = settings.kakao_client_secret

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data=request_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 21599),
            }

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """액세스 토큰으로 사용자 정보 조회"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        kakao_account = data.get("kakao_account", {})
        profile = kakao_account.get("profile", {})

        return OAuthUserInfo(
            provider="kakao",
            provider_id=str(data["id"]),
            email=kakao_account.get("email"),
            name=profile.get("nickname"),
            profile_image=profile.get("profile_image_url"),
            kakao_id=str(data["id"]),  # 알림톡용
        )


# 싱글톤 인스턴스
kakao_oauth_service = KakaoOAuthService()
