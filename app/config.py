"""
환경변수 설정 모듈
Pydantic Settings를 사용하여 환경변수를 관리합니다.
모든 설정은 .env 파일에서 가져옵니다.
"""

from typing import Literal, List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ========== LLM 제공자 설정 ==========
    llm_provider: Literal["openai", "gemini"] = "openai"
    openai_api_key: str = ""
    google_api_key: str = ""

    # ========== 네이버 쇼핑 API 설정 ==========
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # ========== 세션/캐시 설정 ==========
    session_ttl_minutes: int = 60
    cache_ttl_seconds: int = 3600

    # ========== 서버 설정 ==========
    api_host: str = ""
    port: int = 8000
    api_port: int = 8000
    debug: bool = False

    @property
    def server_port(self) -> int:
        """Railway PORT 환경변수 우선 사용"""
        return self.port

    # ========== CORS 설정 ==========
    cors_origins: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins를 리스트로 변환"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ========== 데이터베이스 설정 ==========
    # Railway DATABASE_URL 직접 사용 (우선)
    database_url_raw: Optional[str] = None

    # 개별 설정 (로컬 개발용)
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_db: str = ""

    @field_validator("database_url_raw", mode="before")
    @classmethod
    def get_database_url_from_env(cls, v):
        """DATABASE_URL 환경변수 읽기"""
        import os
        return v or os.environ.get("DATABASE_URL")

    @property
    def database_url(self) -> str:
        """PostgreSQL 비동기 연결 URL"""
        if self.database_url_raw:
            # Railway DATABASE_URL 사용 (postgresql:// -> postgresql+asyncpg://)
            url = self.database_url_raw
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """PostgreSQL 동기 연결 URL (Alembic용)"""
        if self.database_url_raw:
            # Railway DATABASE_URL 그대로 사용
            url = self.database_url_raw
            if url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
            return url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ========== JWT 인증 설정 ==========
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15  # Access Token 15분

    # ========== OAuth 소셜 로그인 설정 ==========
    # 카카오
    kakao_client_id: str = ""
    kakao_client_secret: Optional[str] = None
    kakao_redirect_uri: str = ""

    # 네이버
    naver_oauth_client_id: str = ""
    naver_oauth_client_secret: str = ""
    naver_oauth_redirect_uri: str = ""

    # ========== 알림 설정 ==========
    # 카카오톡 "나에게 보내기"는 별도 설정 불필요 (사용자 로그인 시 토큰 자동 저장)

    # 이메일 (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None

    # ========== Redis 설정 ==========
    # Railway REDIS_URL 직접 사용 (우선)
    redis_url_raw: Optional[str] = None

    # 개별 설정 (로컬 개발용)
    redis_host: str = ""
    redis_port: int = 6379
    redis_db: int = 0

    # 빈 문자열을 기본값으로 변환하는 validator
    @field_validator("postgres_port", "redis_port", "smtp_port", mode="before")
    @classmethod
    def empty_string_to_default(cls, v, info):
        """빈 문자열이면 기본값 사용"""
        if v == "" or v is None:
            defaults = {"postgres_port": 5432, "redis_port": 6379, "smtp_port": 587}
            return defaults.get(info.field_name, v)
        return v

    @field_validator("redis_url_raw", mode="before")
    @classmethod
    def get_redis_url_from_env(cls, v):
        """REDIS_URL 환경변수 읽기"""
        import os
        return v or os.environ.get("REDIS_URL")

    @property
    def redis_url(self) -> str:
        """Redis 연결 URL"""
        if self.redis_url_raw:
            return self.redis_url_raw
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache()
def get_settings() -> Settings:
    """캐싱된 설정 인스턴스 반환"""
    return Settings()
