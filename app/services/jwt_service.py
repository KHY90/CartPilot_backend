"""
JWT 토큰 서비스
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from pydantic import BaseModel

from app.config import get_settings

settings = get_settings()


class TokenData(BaseModel):
    """토큰 데이터"""

    user_id: str
    provider: str
    exp: datetime


class JWTService:
    """JWT 토큰 서비스"""

    def __init__(self):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.expire_minutes = settings.jwt_expire_minutes

    def create_access_token(
        self,
        user_id: str,
        provider: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """액세스 토큰 생성"""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.expire_minutes)

        payload = {
            "sub": user_id,
            "provider": provider,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        provider: str,
    ) -> str:
        """리프레시 토큰 생성 (7일)"""
        expire = datetime.utcnow() + timedelta(days=7)

        payload = {
            "sub": user_id,
            "provider": provider,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[TokenData]:
        """토큰 검증 및 디코딩"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("sub")
            provider: str = payload.get("provider")
            exp: int = payload.get("exp")

            if user_id is None:
                return None

            return TokenData(
                user_id=user_id,
                provider=provider,
                exp=datetime.fromtimestamp(exp),
            )
        except JWTError:
            return None

    def is_token_expired(self, token: str) -> bool:
        """토큰 만료 여부 확인"""
        token_data = self.verify_token(token)
        if token_data is None:
            return True
        return datetime.utcnow() > token_data.exp


# 싱글톤 인스턴스
jwt_service = JWTService()
