"""
FastAPI 메인 애플리케이션
CartPilot 쇼핑 AI Agent 백엔드
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, graph, health
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """애플리케이션 생명주기 관리"""
    # 시작 시 초기화
    settings = get_settings()
    print(f"🛒 CartPilot 서버 시작 (LLM: {settings.llm_provider})")

    yield

    # 종료 시 정리
    print("🛒 CartPilot 서버 종료")


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리"""
    settings = get_settings()

    app = FastAPI(
        title="CartPilot Shopping AI Agent",
        description="통합 쇼핑/선물 AI Agent API - GIFT, VALUE, BUNDLE, REVIEW, TREND 모드 지원",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    app.include_router(health.router, prefix="/api", tags=["Health"])
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(graph.router, prefix="/api", tags=["Graph"])

    # Docker healthcheck용 루트 레벨 헬스체크
    @app.get("/health")
    async def root_health():
        return {"status": "ok"}

    return app


# 앱 인스턴스
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.server_port,
        reload=settings.debug,
    )
