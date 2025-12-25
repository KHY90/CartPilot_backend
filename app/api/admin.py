"""
관리자 API
스케줄러 관리, 가격 모니터링 수동 실행 등
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.scheduler import get_scheduler
from app.services.price_monitor import get_price_monitor

router = APIRouter()


# ========== Schemas ==========


class SchedulerJobInfo(BaseModel):
    """스케줄러 작업 정보"""

    id: str
    name: str
    next_run: str | None


class SchedulerStatus(BaseModel):
    """스케줄러 상태"""

    running: bool
    jobs: list[SchedulerJobInfo]


class PriceCheckResult(BaseModel):
    """가격 확인 결과"""

    checked: int
    updated: int
    alerts_sent: int
    errors: int


class ManualPriceCheckRequest(BaseModel):
    """수동 가격 확인 요청"""

    wishlist_item_id: str


# ========== Endpoints ==========


@router.get("/scheduler/status", response_model=SchedulerStatus)
async def get_scheduler_status(
    current_user: User = Depends(get_current_user),
):
    """스케줄러 상태 조회"""
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()

    return SchedulerStatus(
        running=scheduler._is_running,
        jobs=[
            SchedulerJobInfo(
                id=job["id"],
                name=job["name"],
                next_run=job["next_run"],
            )
            for job in jobs
        ],
    )


@router.post("/price-check/trigger", response_model=dict)
async def trigger_price_check(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    가격 모니터링 수동 실행

    백그라운드에서 실행되며, 즉시 응답을 반환합니다.
    """
    scheduler = get_scheduler()

    async def run_check():
        await scheduler.trigger_price_monitoring()

    background_tasks.add_task(run_check)

    return {"message": "가격 확인이 백그라운드에서 시작되었습니다"}


@router.post("/price-check/single", response_model=dict)
async def check_single_price(
    request: ManualPriceCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """단일 상품 가격 확인"""
    monitor = get_price_monitor()
    result = await monitor.check_single_product(db, request.wishlist_item_id)

    if not result:
        raise HTTPException(status_code=404, detail="관심상품을 찾을 수 없습니다")

    return result


@router.get("/notifications/status", response_model=dict)
async def get_notification_status(
    current_user: User = Depends(get_current_user),
):
    """알림 서비스 상태 확인"""
    from app.services.notifications import (
        get_alimtalk_service,
        get_email_service,
    )

    alimtalk = get_alimtalk_service()
    email = get_email_service()

    return {
        "kakao_alimtalk": {
            "available": alimtalk.is_available(),
        },
        "email": {
            "available": email.is_available(),
        },
    }
