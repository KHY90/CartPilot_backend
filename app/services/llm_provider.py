"""
LLM Provider 추상화
OpenAI와 Gemini를 선택적으로 사용할 수 있는 추상화 계층
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from app.config import get_settings


class LLMProvider(ABC):
    """LLM 제공자 추상 기본 클래스"""

    @abstractmethod
    def get_chat_model(self, **kwargs: Any) -> BaseChatModel:
        """채팅 모델 인스턴스 반환"""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: List[BaseMessage],
        **kwargs: Any,
    ) -> str:
        """메시지 생성"""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI LLM 제공자"""

    def __init__(self) -> None:
        from langchain_openai import ChatOpenAI

        settings = get_settings()
        self._api_key = settings.openai_api_key

        if not self._api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")

    def get_chat_model(self, **kwargs: Any) -> BaseChatModel:
        """ChatOpenAI 인스턴스 반환"""
        from langchain_openai import ChatOpenAI

        # model = kwargs.get("model", "gemini-2.0-flash-lite")
        model = kwargs.get("model", "gpt-4o-mini")
        temperature = kwargs.get("temperature", 0.7)

        return ChatOpenAI(
            api_key=self._api_key,
            model=model,
            temperature=temperature,
        )

    async def generate(
        self,
        messages: List[BaseMessage],
        **kwargs: Any,
    ) -> str:
        """메시지 생성"""
        model = self.get_chat_model(**kwargs)
        response = await model.ainvoke(messages)
        return str(response.content)


class GeminiProvider(LLMProvider):
    """Google Gemini LLM 제공자"""

    def __init__(self) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        settings = get_settings()
        self._api_key = settings.google_api_key

        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다")

    def get_chat_model(self, **kwargs: Any) -> BaseChatModel:
        """ChatGoogleGenerativeAI 인스턴스 반환"""
        from langchain_google_genai import ChatGoogleGenerativeAI

        # model = kwargs.get("model", "gemini-2.0-flash-lite")
        model = kwargs.get("model", "gpt-4o-mini")
        temperature = kwargs.get("temperature", 0.7)

        return ChatGoogleGenerativeAI(
            google_api_key=self._api_key,
            model=model,
            temperature=temperature,
        )

    async def generate(
        self,
        messages: List[BaseMessage],
        **kwargs: Any,
    ) -> str:
        """메시지 생성"""
        model = self.get_chat_model(**kwargs)
        response = await model.ainvoke(messages)
        return str(response.content)


# 싱글톤 인스턴스
_llm_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """설정에 따른 LLM 제공자 반환"""
    global _llm_provider

    if _llm_provider is None:
        settings = get_settings()

        if settings.llm_provider == "openai":
            _llm_provider = OpenAIProvider()
        elif settings.llm_provider == "gemini":
            _llm_provider = GeminiProvider()
        else:
            raise ValueError(f"지원하지 않는 LLM 제공자: {settings.llm_provider}")

    return _llm_provider


def create_system_message(content: str) -> SystemMessage:
    """시스템 메시지 생성 헬퍼"""
    return SystemMessage(content=content)


def create_human_message(content: str) -> HumanMessage:
    """사용자 메시지 생성 헬퍼"""
    return HumanMessage(content=content)
