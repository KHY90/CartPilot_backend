"""
Alembic 환경 설정
"""

from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy import create_engine

from alembic import context

# 애플리케이션 설정 및 모델 임포트
from app.config import get_settings
from app.database import Base

# 모델 임포트 (마이그레이션에서 인식하도록)
from app.models.user import User  # noqa: F401
from app.models.wishlist import WishlistItem, PriceHistory  # noqa: F401
from app.models.rating import ProductRating  # noqa: F401

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 메타데이터 설정 (autogenerate 지원용)
target_metadata = Base.metadata

# 설정에서 DB URL 가져오기
settings = get_settings()


def run_migrations_offline() -> None:
    """
    오프라인 모드에서 마이그레이션 실행
    실제 DB 연결 없이 SQL 스크립트만 생성
    """
    url = settings.database_url_sync
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    온라인 모드에서 마이그레이션 실행
    실제 DB에 연결하여 마이그레이션 적용
    """
    connectable = create_engine(
        settings.database_url_sync,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
