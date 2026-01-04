"""
알림 관리자
카카오톡 "나에게 보내기" 우선, 이메일 fallback
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.wishlist import WishlistItem
from app.services.notifications.kakao_message import get_kakao_message_service
from app.services.notifications.email_service import get_email_service

logger = logging.getLogger(__name__)


class NotificationManager:
    """알림 관리자 - 카카오톡 우선, 이메일 fallback"""

    # 같은 상품에 대한 알림 최소 간격 (24시간)
    MIN_NOTIFICATION_INTERVAL = timedelta(hours=24)

    def __init__(self):
        self.kakao_message = get_kakao_message_service()
        self.email = get_email_service()

    async def send_price_alert(
        self,
        db: AsyncSession,
        user: User,
        wishlist_item: WishlistItem,
        current_price: int,
        lowest_price: int,
    ) -> bool:
        """
        가격 알림 전송

        우선순위:
        1. 카카오 알림톡 (사용자가 활성화한 경우)
        2. 이메일 (fallback)

        Args:
            db: 데이터베이스 세션
            user: 사용자
            wishlist_item: 관심상품
            current_price: 현재 가격
            lowest_price: 90일 최저가

        Returns:
            알림 전송 성공 여부
        """
        # 알림 중복 방지 체크
        if not self._should_send_notification(wishlist_item):
            logger.debug(f"알림 스킵 (최근 알림 발송됨): {wishlist_item.product_name}")
            return False

        success = False

        # 1. 카카오 "나에게 보내기" 시도
        if user.kakao_notification_enabled and user.kakao_access_token:
            try:
                success = await self.kakao_message.send_price_alert(
                    access_token=user.kakao_access_token,
                    product_name=wishlist_item.product_name,
                    current_price=current_price,
                    lowest_price=lowest_price,
                    product_link=wishlist_item.product_link or "",
                )
                if success:
                    logger.info(f"카카오톡 메시지 전송 성공: {user.email} - {wishlist_item.product_name}")
            except Exception as e:
                logger.error(f"카카오톡 메시지 전송 실패: {e}")

        # 2. 이메일 fallback
        if not success and user.email_notification_enabled:
            email = user.notification_email or user.email
            if email:
                try:
                    success = await self.email.send_price_alert(
                        to_email=email,
                        product_name=wishlist_item.product_name,
                        current_price=current_price,
                        lowest_price=lowest_price,
                        product_link=wishlist_item.product_link or "",
                        product_image=wishlist_item.product_image,
                    )
                    if success:
                        logger.info(f"이메일 알림 전송 성공: {email} - {wishlist_item.product_name}")
                except Exception as e:
                    logger.error(f"이메일 전송 실패: {e}")

        # 알림 발송 시간 업데이트
        if success:
            wishlist_item.last_notified_at = datetime.utcnow()
            await db.commit()

        return success

    def _should_send_notification(self, wishlist_item: WishlistItem) -> bool:
        """알림 전송 여부 판단"""
        # 알림 비활성화
        if not wishlist_item.notification_enabled:
            return False

        # 마지막 알림 이후 충분한 시간이 지났는지 확인
        if wishlist_item.last_notified_at:
            time_since_last = datetime.utcnow() - wishlist_item.last_notified_at
            if time_since_last < self.MIN_NOTIFICATION_INTERVAL:
                return False

        return True

    async def send_bulk_price_alerts(
        self,
        db: AsyncSession,
        alerts: list[dict],
    ) -> dict:
        """
        다수 알림 일괄 전송

        Args:
            db: 데이터베이스 세션
            alerts: [{"user": User, "item": WishlistItem, "current_price": int, "lowest_price": int}]

        Returns:
            {"sent": int, "failed": int, "skipped": int}
        """
        results = {"sent": 0, "failed": 0, "skipped": 0}

        for alert in alerts:
            try:
                success = await self.send_price_alert(
                    db=db,
                    user=alert["user"],
                    wishlist_item=alert["item"],
                    current_price=alert["current_price"],
                    lowest_price=alert["lowest_price"],
                )
                if success:
                    results["sent"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                logger.error(f"알림 전송 중 오류: {e}")
                results["failed"] += 1

        return results


# 싱글톤 인스턴스
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """알림 관리자 싱글톤 반환"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
