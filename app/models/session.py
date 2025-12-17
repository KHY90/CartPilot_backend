"""
세션 모델 정의
대화 세션 관리 관련 모델
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.product import ProductCandidate
from app.models.request import IntentType, Requirements


class ConversationMessage(BaseModel):
    """대화 메시지"""

    role: Literal["user", "assistant", "system"] = Field(..., description="역할")
    content: str = Field(..., description="내용")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionState(BaseModel):
    """세션 상태"""

    session_id: str = Field(..., description="세션 ID")

    # 대화 기록
    messages: List[ConversationMessage] = Field(default_factory=list)

    # 현재 상태
    current_intent: Optional[IntentType] = Field(None)
    current_requirements: Optional[Requirements] = Field(None)

    # 캐시된 결과
    cached_products: Dict[str, List[ProductCandidate]] = Field(default_factory=dict)
    cached_recommendations: Optional[Dict[str, Any]] = Field(None)

    # 메타데이터
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    turn_count: int = Field(default=0, description="대화 턴 수")

    def add_user_message(self, content: str) -> None:
        """사용자 메시지 추가"""
        self.messages.append(ConversationMessage(role="user", content=content))
        self.turn_count += 1
        self.updated_at = datetime.utcnow()

    def add_assistant_message(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """어시스턴트 응답 추가"""
        self.messages.append(
            ConversationMessage(role="assistant", content=content, metadata=metadata or {})
        )
        self.updated_at = datetime.utcnow()

    def get_recent_messages(self, count: int = 6) -> List[ConversationMessage]:
        """최근 N개 메시지 반환"""
        return self.messages[-count:]

    model_config = {"arbitrary_types_allowed": True}
