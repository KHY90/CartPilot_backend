"""
카카오톡 "나에게 보내기" 서비스
비즈니스 채널 없이 사용자 본인에게 메시지 전송
https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api#send-me
"""

import json
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class KakaoMessageService:
    """카카오톡 나에게 보내기 서비스 (비즈니스 채널 불필요)"""

    # 나에게 보내기 - 기본 템플릿 API
    SEND_ME_API_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    def __init__(self):
        # 별도 설정 불필요 - 사용자 토큰만 있으면 사용 가능
        pass

    def is_available(self) -> bool:
        """서비스 사용 가능 여부 - 항상 True (사용자 토큰 필요)"""
        return True

    async def send_price_alert(
        self,
        access_token: str,
        product_name: str,
        current_price: int,
        lowest_price: int,
        product_link: str,
    ) -> bool:
        """
        가격 알림 전송 (텍스트 템플릿)

        Args:
            access_token: 사용자의 카카오 액세스 토큰
            product_name: 상품명
            current_price: 현재 가격
            lowest_price: 90일 최저가
            product_link: 상품 링크

        Returns:
            전송 성공 여부
        """
        # 텍스트 메시지 구성
        text = (
            f"🛒 CartPilot 최저가 알림!\n\n"
            f"[{product_name[:50]}{'...' if len(product_name) > 50 else ''}]\n\n"
            f"현재 가격: {current_price:,}원\n"
            f"90일 최저가: {lowest_price:,}원\n\n"
            f"지금이 구매 적기입니다!"
        )

        template_object = {
            "object_type": "text",
            "text": text,
            "link": {
                "web_url": product_link,
                "mobile_web_url": product_link,
            },
            "button_title": "상품 보러가기",
        }

        return await self._send_message(access_token, template_object)

    async def send_feed_alert(
        self,
        access_token: str,
        product_name: str,
        current_price: int,
        lowest_price: int,
        product_link: str,
        product_image: Optional[str] = None,
    ) -> bool:
        """
        가격 알림 전송 (피드 템플릿 - 이미지 포함)

        Args:
            access_token: 사용자의 카카오 액세스 토큰
            product_name: 상품명
            current_price: 현재 가격
            lowest_price: 90일 최저가
            product_link: 상품 링크
            product_image: 상품 이미지 URL

        Returns:
            전송 성공 여부
        """
        template_object = {
            "object_type": "feed",
            "content": {
                "title": "🛒 CartPilot 최저가 알림",
                "description": f"{product_name[:50]}{'...' if len(product_name) > 50 else ''}",
                "image_url": product_image or "https://via.placeholder.com/300x200",
                "image_width": 300,
                "image_height": 200,
                "link": {
                    "web_url": product_link,
                    "mobile_web_url": product_link,
                },
            },
            "item_content": {
                "items": [
                    {"item": "현재 가격", "item_op": f"{current_price:,}원"},
                    {"item": "90일 최저가", "item_op": f"{lowest_price:,}원"},
                ],
            },
            "buttons": [
                {
                    "title": "상품 보러가기",
                    "link": {
                        "web_url": product_link,
                        "mobile_web_url": product_link,
                    },
                }
            ],
        }

        return await self._send_message(access_token, template_object)

    async def send_custom_message(
        self,
        access_token: str,
        message: str,
        link_url: Optional[str] = None,
        button_title: str = "자세히 보기",
    ) -> bool:
        """
        커스텀 텍스트 메시지 전송

        Args:
            access_token: 사용자의 카카오 액세스 토큰
            message: 전송할 메시지
            link_url: 링크 URL (선택)
            button_title: 버튼 제목

        Returns:
            전송 성공 여부
        """
        template_object = {
            "object_type": "text",
            "text": message,
            "link": {
                "web_url": link_url or "",
                "mobile_web_url": link_url or "",
            },
        }

        if link_url:
            template_object["button_title"] = button_title

        return await self._send_message(access_token, template_object)

    async def _send_message(self, access_token: str, template_object: dict) -> bool:
        """실제 메시지 전송"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.SEND_ME_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "template_object": json.dumps(template_object),
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("result_code") == 0:
                        logger.info("카카오톡 메시지 전송 성공")
                        return True
                    else:
                        logger.error(f"카카오톡 메시지 전송 실패: {result}")
                        return False
                else:
                    error_data = response.json() if response.content else {}
                    logger.error(
                        f"카카오톡 메시지 전송 실패: {response.status_code} - {error_data}"
                    )

                    # 토큰 만료 에러 (-401)인 경우 별도 처리 가능
                    if error_data.get("code") == -401:
                        logger.warning("카카오 토큰 만료됨 - 재로그인 필요")

                    return False

        except Exception as e:
            logger.error(f"카카오톡 메시지 전송 중 오류: {e}")
            return False


# 싱글톤 인스턴스
_kakao_message_service: Optional[KakaoMessageService] = None


def get_kakao_message_service() -> KakaoMessageService:
    """카카오 메시지 서비스 싱글톤 반환"""
    global _kakao_message_service
    if _kakao_message_service is None:
        _kakao_message_service = KakaoMessageService()
    return _kakao_message_service
