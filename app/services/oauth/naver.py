"""
네이버 OAuth 서비스
https://developers.naver.com/docs/login/api/api.md
"""

from urllib.parse import urlencode
import httpx

from app.config import get_settings
from app.services.oauth.base import BaseOAuthService, OAuthUserInfo

settings = get_settings()


class NaverOAuthService(BaseOAuthService):
    """네이버 OAuth 서비스"""

    AUTHORIZE_URL = "https://nid.naver.com/oauth2.0/authorize"
    TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
    USER_INFO_URL = "https://openapi.naver.com/v1/nid/me"

    @property
    def provider_name(self) -> str:
        return "naver"

    def get_authorization_url(self, state: str) -> str:
        """네이버 로그인 인증 URL 생성"""
        params = {
            "client_id": settings.naver_oauth_client_id,
            "redirect_uri": settings.naver_oauth_redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def get_access_token(self, code: str) -> str:
        """인증 코드로 액세스 토큰 교환"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.naver_oauth_client_id,
                    "client_secret": settings.naver_oauth_client_secret,
                    "code": code,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["access_token"]

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """액세스 토큰으로 사용자 정보 조회"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        user_data = data.get("response", {})

        return OAuthUserInfo(
            provider="naver",
            provider_id=user_data["id"],
            email=user_data.get("email"),
            name=user_data.get("name"),
            profile_image=user_data.get("profile_image"),
        )


# 싱글톤 인스턴스
naver_oauth_service = NaverOAuthService()
