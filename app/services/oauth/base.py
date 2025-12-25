"""
OAuth 베이스 클래스
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class OAuthUserInfo:
    """OAuth 사용자 정보"""

    provider: str
    provider_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    profile_image: Optional[str] = None
    kakao_id: Optional[str] = None  # 카카오 알림톡용


class BaseOAuthService(ABC):
    """OAuth 서비스 베이스 클래스"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """제공자 이름"""
        pass

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """인증 URL 생성"""
        pass

    @abstractmethod
    async def get_access_token(self, code: str) -> str:
        """인증 코드로 액세스 토큰 교환"""
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """액세스 토큰으로 사용자 정보 조회"""
        pass
