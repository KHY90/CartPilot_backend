"""
가격 모니터링 서비스
관심상품의 가격을 주기적으로 확인하고 최저가 알림 발송
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.user import User
from app.models.wishlist import WishlistItem, PriceHistory
from app.services.naver_shopping import get_naver_client, NaverShoppingError
from app.services.notifications import get_notification_manager

logger = logging.getLogger(__name__)


class PriceMonitorService:
    """가격 모니터링 서비스"""

    def __init__(self):
        self.naver_client = get_naver_client()
        self.notification_manager = get_notification_manager()

    async def check_all_wishlist_prices(self) -> dict:
        """
        모든 관심상품의 가격 확인 및 알림 발송

        Returns:
            {"checked": int, "updated": int, "alerts_sent": int, "errors": int}
        """
        results = {"checked": 0, "updated": 0, "alerts_sent": 0, "errors": 0}

        async with async_session_maker() as db:
            try:
                # 알림이 활성화된 모든 관심상품 조회
                stmt = (
                    select(WishlistItem)
                    .options(selectinload(WishlistItem.user))
                    .where(WishlistItem.notification_enabled == True)
                )
                result = await db.execute(stmt)
                items = result.scalars().all()

                logger.info(f"가격 확인 시작: {len(items)}개 상품")

                for item in items:
                    try:
                        updated, alert_sent = await self._check_item_price(db, item)
                        results["checked"] += 1
                        if updated:
                            results["updated"] += 1
                        if alert_sent:
                            results["alerts_sent"] += 1
                    except Exception as e:
                        logger.error(f"상품 가격 확인 실패 ({item.product_id}): {e}")
                        results["errors"] += 1

                await db.commit()
                logger.info(f"가격 확인 완료: {results}")

            except Exception as e:
                logger.error(f"가격 모니터링 중 오류: {e}")
                await db.rollback()
                raise

        return results

    async def _check_item_price(
        self,
        db: AsyncSession,
        item: WishlistItem,
    ) -> tuple[bool, bool]:
        """
        단일 상품 가격 확인

        Args:
            db: 데이터베이스 세션
            item: 관심상품

        Returns:
            (가격 업데이트 여부, 알림 발송 여부)
        """
        updated = False
        alert_sent = False

        try:
            # 네이버 쇼핑에서 현재 가격 조회
            search_result = await self.naver_client.search(
                query=item.product_name,
                display=5,
            )

            if not search_result.items:
                logger.warning(f"상품 검색 결과 없음: {item.product_name}")
                return updated, alert_sent

            # 가장 유사한 상품의 가격 사용 (첫 번째 결과)
            current_price = search_result.items[0].price

            # 가격이 변경된 경우에만 업데이트
            if current_price != item.current_price:
                # 가격 이력 추가
                price_history = PriceHistory(
                    wishlist_item_id=item.id,
                    price=current_price,
                    recorded_at=datetime.utcnow(),
                )
                db.add(price_history)

                # 현재 가격 업데이트
                item.current_price = current_price
                updated = True

                # 90일 최저가 계산
                lowest_90 = await self._calculate_lowest_90days(db, item.id, current_price)
                item.lowest_price_90days = lowest_90

                # 최저가 알림 조건 확인
                if self._should_send_alert(item, current_price, lowest_90):
                    user = item.user
                    if user and user.is_active:
                        success = await self.notification_manager.send_price_alert(
                            db=db,
                            user=user,
                            wishlist_item=item,
                            current_price=current_price,
                            lowest_price=lowest_90,
                        )
                        alert_sent = success

        except NaverShoppingError as e:
            logger.error(f"네이버 쇼핑 API 오류: {e}")
        except Exception as e:
            logger.error(f"가격 확인 중 오류: {e}")
            raise

        return updated, alert_sent

    async def _calculate_lowest_90days(
        self,
        db: AsyncSession,
        wishlist_item_id,
        current_price: int,
    ) -> int:
        """90일 최저가 계산"""
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)

        stmt = select(PriceHistory.price).where(
            and_(
                PriceHistory.wishlist_item_id == wishlist_item_id,
                PriceHistory.recorded_at >= ninety_days_ago,
            )
        )
        result = await db.execute(stmt)
        prices = result.scalars().all()

        if prices:
            return min(min(prices), current_price)
        return current_price

    def _should_send_alert(
        self,
        item: WishlistItem,
        current_price: int,
        lowest_90days: int,
    ) -> bool:
        """
        알림 발송 조건 확인

        조건:
        1. 현재 가격이 90일 최저가와 같거나 낮음
        2. 또는 목표 가격 이하로 떨어짐
        """
        # 현재 가격이 90일 최저가 이하
        if current_price <= lowest_90days:
            return True

        # 목표 가격이 설정되어 있고, 현재 가격이 목표 이하
        if item.target_price and current_price <= item.target_price:
            return True

        return False

    async def check_single_product(
        self,
        db: AsyncSession,
        wishlist_item_id: str,
    ) -> Optional[dict]:
        """
        단일 상품 가격 확인 (수동 요청용)

        Args:
            db: 데이터베이스 세션
            wishlist_item_id: 관심상품 ID

        Returns:
            {"current_price": int, "lowest_90days": int, "updated": bool}
        """
        stmt = (
            select(WishlistItem)
            .options(selectinload(WishlistItem.user))
            .where(WishlistItem.id == wishlist_item_id)
        )
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()

        if not item:
            return None

        updated, _ = await self._check_item_price(db, item)
        await db.commit()

        return {
            "current_price": item.current_price,
            "lowest_90days": item.lowest_price_90days,
            "updated": updated,
        }


# 싱글톤 인스턴스
_price_monitor: Optional[PriceMonitorService] = None


def get_price_monitor() -> PriceMonitorService:
    """가격 모니터 싱글톤 반환"""
    global _price_monitor
    if _price_monitor is None:
        _price_monitor = PriceMonitorService()
    return _price_monitor
