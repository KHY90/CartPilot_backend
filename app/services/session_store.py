"""
세션 저장소
인메모리 세션 관리 (asyncio.Lock 사용)
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from app.config import get_settings
from app.models.session import SessionState


class InMemorySessionStore:
    """인메모리 세션 저장소"""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._settings = get_settings()

    async def create_session(self) -> SessionState:
        """새 세션 생성"""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session = SessionState(session_id=session_id)

        async with self._lock:
            self._sessions[session_id] = session

        return session

    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """세션 조회"""
        async with self._lock:
            session = self._sessions.get(session_id)

            if session:
                # TTL 체크
                ttl = timedelta(minutes=self._settings.session_ttl_minutes)
                if datetime.utcnow() - session.created_at > ttl:
                    del self._sessions[session_id]
                    return None

            return session

    async def get_or_create_session(self, session_id: Optional[str]) -> SessionState:
        """세션 조회 또는 생성"""
        if session_id:
            session = await self.get_session(session_id)
            if session:
                return session

        return await self.create_session()

    async def update_session(self, session: SessionState) -> None:
        """세션 업데이트"""
        session.updated_at = datetime.utcnow()
        async with self._lock:
            self._sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> bool:
        """세션 삭제"""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def clear_expired(self) -> int:
        """만료된 세션 정리"""
        ttl = timedelta(minutes=self._settings.session_ttl_minutes)
        now = datetime.utcnow()
        expired_count = 0

        async with self._lock:
            expired_ids = [
                sid
                for sid, session in self._sessions.items()
                if now - session.created_at > ttl
            ]
            for sid in expired_ids:
                del self._sessions[sid]
                expired_count += 1

        return expired_count

    async def get_active_count(self) -> int:
        """활성 세션 수 반환"""
        async with self._lock:
            return len(self._sessions)


# 싱글톤 인스턴스
_session_store: Optional[InMemorySessionStore] = None


def get_session_store() -> InMemorySessionStore:
    """세션 저장소 싱글톤 반환"""
    global _session_store
    if _session_store is None:
        _session_store = InMemorySessionStore()
    return _session_store
