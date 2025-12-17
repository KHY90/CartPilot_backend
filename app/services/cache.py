"""
인메모리 캐시
TTL 기반 캐싱 구현
"""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Generic, Optional, TypeVar

from app.config import get_settings

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """캐시 엔트리"""

    def __init__(self, value: T, ttl_seconds: int) -> None:
        self.value = value
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        """만료 여부 확인"""
        return datetime.utcnow() > self.expires_at


class InMemoryCache:
    """인메모리 TTL 캐시"""

    def __init__(self) -> None:
        self._cache: Dict[str, CacheEntry[Any]] = {}
        self._lock = asyncio.Lock()
        self._settings = get_settings()

    @staticmethod
    def _make_key(prefix: str, params: Dict[str, Any]) -> str:
        """캐시 키 생성"""
        # 파라미터를 정렬하여 일관된 키 생성
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)
        hash_val = hashlib.md5(sorted_params.encode()).hexdigest()[:12]
        return f"{prefix}:{hash_val}"

    async def get(self, key: str) -> Optional[Any]:
        """캐시 조회"""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if entry.is_expired():
                del self._cache[key]
                return None

            return entry.value

    async def set(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> None:
        """캐시 저장"""
        ttl = ttl_seconds or self._settings.cache_ttl_seconds

        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl)

    async def delete(self, key: str) -> bool:
        """캐시 삭제"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> int:
        """전체 캐시 삭제"""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    async def clear_expired(self) -> int:
        """만료된 캐시 정리"""
        expired_count = 0

        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                expired_count += 1

        return expired_count

    async def get_or_set(
        self,
        key: str,
        factory: Any,  # Callable that returns awaitable
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        """캐시 조회 또는 생성"""
        value = await self.get(key)
        if value is not None:
            return value

        # 팩토리 함수 실행
        value = await factory()
        await self.set(key, value, ttl_seconds)
        return value

    def make_search_key(self, query: str, **params: Any) -> str:
        """검색 캐시 키 생성"""
        return self._make_key("search", {"query": query, **params})

    def make_recommendation_key(self, intent: str, session_id: str, **params: Any) -> str:
        """추천 캐시 키 생성"""
        return self._make_key("rec", {"intent": intent, "session": session_id, **params})


# 싱글톤 인스턴스
_cache: Optional[InMemoryCache] = None


def get_cache() -> InMemoryCache:
    """캐시 싱글톤 반환"""
    global _cache
    if _cache is None:
        _cache = InMemoryCache()
    return _cache
