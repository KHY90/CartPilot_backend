"""
스케줄러 서비스
APScheduler를 사용하여 주기적 작업 실행
"""

import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """스케줄러 서비스"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def start(self):
        """스케줄러 시작"""
        if self._is_running:
            logger.warning("스케줄러가 이미 실행 중입니다")
            return

        # 가격 모니터링 작업 등록 (매 6시간마다)
        self.scheduler.add_job(
            self._run_price_monitoring,
            trigger=IntervalTrigger(hours=6),
            id="price_monitoring",
            name="가격 모니터링",
            replace_existing=True,
        )

        # 매일 오전 9시 가격 확인 (한국 시간)
        self.scheduler.add_job(
            self._run_price_monitoring,
            trigger=CronTrigger(hour=0, minute=0),  # UTC 0시 = KST 9시
            id="daily_price_check",
            name="일일 가격 확인",
            replace_existing=True,
        )

        # 오래된 가격 이력 정리 (매일 새벽)
        self.scheduler.add_job(
            self._cleanup_old_price_history,
            trigger=CronTrigger(hour=15, minute=0),  # UTC 15시 = KST 자정
            id="cleanup_price_history",
            name="가격 이력 정리",
            replace_existing=True,
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("스케줄러 시작됨")

    def stop(self):
        """스케줄러 중지"""
        if not self._is_running:
            return

        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("스케줄러 중지됨")

    async def _run_price_monitoring(self):
        """가격 모니터링 실행"""
        try:
            logger.info("가격 모니터링 작업 시작")
            from app.services.price_monitor import get_price_monitor

            monitor = get_price_monitor()
            results = await monitor.check_all_wishlist_prices()
            logger.info(f"가격 모니터링 완료: {results}")
        except Exception as e:
            logger.error(f"가격 모니터링 중 오류: {e}")

    async def _cleanup_old_price_history(self):
        """오래된 가격 이력 정리 (180일 이상)"""
        try:
            logger.info("가격 이력 정리 시작")
            from datetime import datetime, timedelta
            from sqlalchemy import delete
            from app.database import async_session_maker
            from app.models.wishlist import PriceHistory

            cutoff_date = datetime.utcnow() - timedelta(days=180)

            async with async_session_maker() as db:
                stmt = delete(PriceHistory).where(
                    PriceHistory.recorded_at < cutoff_date
                )
                result = await db.execute(stmt)
                await db.commit()
                logger.info(f"가격 이력 정리 완료: {result.rowcount}개 삭제")
        except Exception as e:
            logger.error(f"가격 이력 정리 중 오류: {e}")

    def get_jobs(self) -> list[dict]:
        """등록된 작업 목록 조회"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs

    async def trigger_price_monitoring(self) -> dict:
        """가격 모니터링 수동 실행"""
        await self._run_price_monitoring()
        return {"status": "completed"}


# 싱글톤 인스턴스
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """스케줄러 싱글톤 반환"""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
