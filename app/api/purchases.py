"""
구매 기록 API
수동 입력 기반 구매 이력 관리
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.purchase import PurchaseRecord

router = APIRouter()


# ========== Schemas ==========


class PurchaseCreate(BaseModel):
    """구매 기록 생성"""

    product_name: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    mall_name: Optional[str] = Field(None, max_length=100)
    price: int = Field(..., ge=0)
    quantity: int = Field(default=1, ge=1)
    purchased_at: datetime
    notes: Optional[str] = None


class PurchaseUpdate(BaseModel):
    """구매 기록 수정"""

    product_name: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    mall_name: Optional[str] = Field(None, max_length=100)
    price: Optional[int] = Field(None, ge=0)
    quantity: Optional[int] = Field(None, ge=1)
    purchased_at: Optional[datetime] = None
    notes: Optional[str] = None


class PurchaseResponse(BaseModel):
    """구매 기록 응답"""

    id: str
    product_name: str
    category: Optional[str]
    mall_name: Optional[str]
    price: int
    quantity: int
    purchased_at: datetime
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PurchaseStats(BaseModel):
    """구매 통계"""

    total_purchases: int
    total_spent: int
    average_price: float
    categories: dict[str, int]
    monthly_spending: dict[str, int]


# ========== Endpoints ==========


@router.get("/purchases", response_model=list[PurchaseResponse])
async def get_purchases(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    구매 기록 목록 조회

    - limit: 조회 개수 (최대 100)
    - offset: 시작 위치
    - category: 카테고리 필터
    """
    stmt = select(PurchaseRecord).where(PurchaseRecord.user_id == current_user.id)

    if category:
        stmt = stmt.where(PurchaseRecord.category == category)

    stmt = stmt.order_by(PurchaseRecord.purchased_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    records = result.scalars().all()

    return [PurchaseResponse(**r.to_dict()) for r in records]


@router.post("/purchases", response_model=PurchaseResponse, status_code=201)
async def create_purchase(
    data: PurchaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """구매 기록 생성"""
    record = PurchaseRecord(
        user_id=current_user.id,
        product_name=data.product_name,
        category=data.category,
        mall_name=data.mall_name,
        price=data.price,
        quantity=data.quantity,
        purchased_at=data.purchased_at,
        notes=data.notes,
    )

    db.add(record)
    await db.commit()
    await db.refresh(record)

    return PurchaseResponse(**record.to_dict())


@router.get("/purchases/{purchase_id}", response_model=PurchaseResponse)
async def get_purchase(
    purchase_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """구매 기록 상세 조회"""
    stmt = select(PurchaseRecord).where(
        PurchaseRecord.id == purchase_id,
        PurchaseRecord.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="구매 기록을 찾을 수 없습니다")

    return PurchaseResponse(**record.to_dict())


@router.put("/purchases/{purchase_id}", response_model=PurchaseResponse)
async def update_purchase(
    purchase_id: UUID,
    data: PurchaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """구매 기록 수정"""
    stmt = select(PurchaseRecord).where(
        PurchaseRecord.id == purchase_id,
        PurchaseRecord.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="구매 기록을 찾을 수 없습니다")

    # 업데이트
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)

    await db.commit()
    await db.refresh(record)

    return PurchaseResponse(**record.to_dict())


@router.delete("/purchases/{purchase_id}", status_code=204)
async def delete_purchase(
    purchase_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """구매 기록 삭제"""
    stmt = select(PurchaseRecord).where(
        PurchaseRecord.id == purchase_id,
        PurchaseRecord.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="구매 기록을 찾을 수 없습니다")

    await db.delete(record)
    await db.commit()


@router.get("/purchases/stats/summary", response_model=PurchaseStats)
async def get_purchase_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """구매 통계 조회"""
    # 전체 통계
    stmt = select(
        func.count(PurchaseRecord.id),
        func.sum(PurchaseRecord.price * PurchaseRecord.quantity),
        func.avg(PurchaseRecord.price),
    ).where(PurchaseRecord.user_id == current_user.id)

    result = await db.execute(stmt)
    row = result.one()
    total_purchases = row[0] or 0
    total_spent = row[1] or 0
    average_price = float(row[2] or 0)

    # 카테고리별 통계
    cat_stmt = select(
        PurchaseRecord.category,
        func.sum(PurchaseRecord.price * PurchaseRecord.quantity),
    ).where(
        PurchaseRecord.user_id == current_user.id,
        PurchaseRecord.category.isnot(None),
    ).group_by(PurchaseRecord.category)

    cat_result = await db.execute(cat_stmt)
    categories = {row[0]: row[1] for row in cat_result.all()}

    # 월별 지출
    monthly_stmt = select(
        func.date_trunc("month", PurchaseRecord.purchased_at),
        func.sum(PurchaseRecord.price * PurchaseRecord.quantity),
    ).where(PurchaseRecord.user_id == current_user.id).group_by(
        func.date_trunc("month", PurchaseRecord.purchased_at)
    ).order_by(func.date_trunc("month", PurchaseRecord.purchased_at).desc()).limit(12)

    monthly_result = await db.execute(monthly_stmt)
    monthly_spending = {
        row[0].strftime("%Y-%m"): row[1] for row in monthly_result.all() if row[0]
    }

    return PurchaseStats(
        total_purchases=total_purchases,
        total_spent=total_spent,
        average_price=average_price,
        categories=categories,
        monthly_spending=monthly_spending,
    )


@router.get("/purchases/categories", response_model=list[str])
async def get_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """사용자의 구매 카테고리 목록 조회"""
    stmt = (
        select(PurchaseRecord.category)
        .where(
            PurchaseRecord.user_id == current_user.id,
            PurchaseRecord.category.isnot(None),
        )
        .distinct()
    )

    result = await db.execute(stmt)
    categories = [row[0] for row in result.all()]

    return categories
