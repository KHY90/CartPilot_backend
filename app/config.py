"""
환경변수 설정 모듈
Pydantic Settings를 사용하여 환경변수를 관리합니다.
"""

from typing import Literal, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM 제공자 설정
    llm_provider: Literal["openai", "gemini"] = "openai"
    openai_api_key: str = ""
    google_api_key: str = ""

    # 네이버 쇼핑 API 설정
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # 세션 설정
    session_ttl_minutes: int = 60

    # 캐시 설정
    cache_ttl_seconds: int = 3600

    # 서버 설정
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # CORS 설정
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins를 리스트로 변환"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """캐싱된 설정 인스턴스 반환"""
    return Settings()
