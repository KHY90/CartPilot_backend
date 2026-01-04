"""
캐시 서비스
Redis 기반 캐싱 (Redis 사용 불가 시 인메모리 폴백)
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Generic, Optional, TypeVar

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """캐시 엔트리 (인메모리 폴백용)"""

    def __init__(self, value: T, ttl_seconds: int) -> None:
        self.value = value
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        """만료 여부 확인"""
        return datetime.utcnow() > self.expires_at


class RedisCache:
    """Redis 기반 캐시"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: Optional[Any] = None
        self._fallback_cache: Dict[str, CacheEntry[Any]] = {}
        self._fallback_lock = asyncio.Lock()
        self._use_fallback = False

    async def _get_redis(self):
        """Redis 연결 가져오기 (lazy initialization)"""
        if self._use_fallback:
            return None

        if self._redis is None:
            if not self._settings.redis_host:
                logger.warning("Redis 호스트가 설정되지 않음. 인메모리 캐시 사용")
                self._use_fallback = True
                return None

            try:
                import redis.asyncio as redis
                self._redis = redis.Redis(
                    host=self._settings.redis_host,
                    port=self._settings.redis_port,
                    db=self._settings.redis_db,
                    decode_responses=True,
                )
                # 연결 테스트
                await self._redis.ping()
                logger.info(f"Redis 연결 성공: {self._settings.redis_host}:{self._settings.redis_port}")
            except Exception as e:
                logger.warning(f"Redis 연결 실패, 인메모리 캐시 사용: {e}")
                self._use_fallback = True
                self._redis = None
                return None

        return self._redis

    @staticmethod
    def _make_key(prefix: str, params: Dict[str, Any]) -> str:
        """캐시 키 생성"""
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)
        hash_val = hashlib.md5(sorted_params.encode()).hexdigest()[:12]
        return f"{prefix}:{hash_val}"

    async def get(self, key: str) -> Optional[Any]:
        """캐시 조회"""
        redis = await self._get_redis()

        if redis:
            try:
                value = await redis.get(key)
                if value:
                    return json.loads(value)
                return None
            except Exception as e:
                logger.error(f"Redis get 오류: {e}")
                # Redis 오류 시 폴백으로 전환
                self._use_fallback = True

        # 인메모리 폴백
        async with self._fallback_lock:
            entry = self._fallback_cache.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._fallback_cache[key]
                return None
            return entry.value

    async def set(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> None:
        """캐시 저장"""
        ttl = ttl_seconds or self._settings.cache_ttl_seconds
        redis = await self._get_redis()

        if redis:
            try:
                await redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
                return
            except Exception as e:
                logger.error(f"Redis set 오류: {e}")
                self._use_fallback = True

        # 인메모리 폴백
        async with self._fallback_lock:
            self._fallback_cache[key] = CacheEntry(value, ttl)

    async def delete(self, key: str) -> bool:
        """캐시 삭제"""
        redis = await self._get_redis()

        if redis:
            try:
                result = await redis.delete(key)
                return result > 0
            except Exception as e:
                logger.error(f"Redis delete 오류: {e}")
                self._use_fallback = True

        # 인메모리 폴백
        async with self._fallback_lock:
            if key in self._fallback_cache:
                del self._fallback_cache[key]
                return True
            return False

    async def clear(self) -> int:
        """전체 캐시 삭제 (주의: Redis에서는 cartpilot 관련 키만 삭제)"""
        redis = await self._get_redis()

        if redis:
            try:
                # cartpilot 관련 키만 삭제
                keys = []
                async for key in redis.scan_iter("search_results:*"):
                    keys.append(key)
                async for key in redis.scan_iter("chat_state:*"):
                    keys.append(key)
                if keys:
                    await redis.delete(*keys)
                return len(keys)
            except Exception as e:
                logger.error(f"Redis clear 오류: {e}")
                self._use_fallback = True

        # 인메모리 폴백
        async with self._fallback_lock:
            count = len(self._fallback_cache)
            self._fallback_cache.clear()
            return count

    async def clear_expired(self) -> int:
        """만료된 캐시 정리 (인메모리 폴백 전용)"""
        expired_count = 0

        async with self._fallback_lock:
            expired_keys = [
                key for key, entry in self._fallback_cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._fallback_cache[key]
                expired_count += 1

        return expired_count

    async def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        """캐시 조회 또는 생성"""
        value = await self.get(key)
        if value is not None:
            return value

        value = await factory()
        await self.set(key, value, ttl_seconds)
        return value

    def make_search_key(self, query: str, **params: Any) -> str:
        """검색 캐시 키 생성"""
        return self._make_key("search", {"query": query, **params})

    def make_recommendation_key(self, intent: str, session_id: str, **params: Any) -> str:
        """추천 캐시 키 생성"""
        return self._make_key("rec", {"intent": intent, "session": session_id, **params})

    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._redis:
            await self._redis.close()
            self._redis = None


# 하위 호환성을 위한 별칭
InMemoryCache = RedisCache


# 싱글톤 인스턴스
_cache: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    """캐시 싱글톤 반환"""
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache
