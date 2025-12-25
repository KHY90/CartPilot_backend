"""
관심상품 API 엔드포인트
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database import get_db
from app.models.user import User
from app.models.wishlist import WishlistItem, PriceHistory
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/wishlist", tags=["관심상품"])


# ==================== Request/Response Models ====================
class WishlistItemCreate(BaseModel):
    """관심상품 등록 요청"""
    product_id: str
    product_name: str
    product_image: Optional[str] = None
    product_link: Optional[str] = None
    mall_name: Optional[str] = None
    category: Optional[str] = None
    current_price: int
    target_price: Optional[int] = None
    notes: Optional[str] = None


class WishlistItemUpdate(BaseModel):
    """관심상품 수정 요청"""
    target_price: Optional[int] = None
    notification_enabled: Optional[bool] = None
    notes: Optional[str] = None


class WishlistItemResponse(BaseModel):
    """관심상품 응답"""
    id: str
    product_id: str
    product_name: str
    product_image: Optional[str]
    product_link: Optional[str]
    mall_name: Optional[str]
    category: Optional[str]
    current_price: int
    target_price: Optional[int]
    lowest_price_90days: Optional[int]
    notification_enabled: bool
    created_at: str


class PriceHistoryResponse(BaseModel):
    """가격 이력 응답"""
    price: int
    recorded_at: str


# ==================== API Endpoints ====================
@router.get("", response_model=List[WishlistItemResponse])
async def get_wishlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 관심상품 목록 조회"""
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.user_id == current_user.id)
        .order_by(WishlistItem.created_at.desc())
    )
    items = result.scalars().all()

    return [
        WishlistItemResponse(
            id=str(item.id),
            product_id=item.product_id,
            product_name=item.product_name,
            product_image=item.product_image,
            product_link=item.product_link,
            mall_name=item.mall_name,
            category=item.category,
            current_price=item.current_price,
            target_price=item.target_price,
            lowest_price_90days=item.lowest_price_90days,
            notification_enabled=item.notification_enabled,
            created_at=item.created_at.isoformat(),
        )
        for item in items
    ]


@router.post("", response_model=WishlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    request: WishlistItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관심상품 등록"""
    # 중복 확인
    existing = await db.execute(
        select(WishlistItem).where(
            and_(
                WishlistItem.user_id == current_user.id,
                WishlistItem.product_id == request.product_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 관심상품입니다",
        )

    # 관심상품 개수 제한 (사용자당 최대 20개)
    count_result = await db.execute(
        select(WishlistItem).where(WishlistItem.user_id == current_user.id)
    )
    if len(count_result.scalars().all()) >= 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="관심상품은 최대 20개까지 등록할 수 있습니다",
        )

    # 생성
    item = WishlistItem(
        user_id=current_user.id,
        product_id=request.product_id,
        product_name=request.product_name,
        product_image=request.product_image,
        product_link=request.product_link,
        mall_name=request.mall_name,
        category=request.category,
        current_price=request.current_price,
        target_price=request.target_price,
        notes=request.notes,
    )
    db.add(item)

    # 초기 가격 이력 추가
    price_history = PriceHistory(
        wishlist_item_id=item.id,
        price=request.current_price,
    )
    db.add(price_history)

    await db.commit()
    await db.refresh(item)

    return WishlistItemResponse(
        id=str(item.id),
        product_id=item.product_id,
        product_name=item.product_name,
        product_image=item.product_image,
        product_link=item.product_link,
        mall_name=item.mall_name,
        category=item.category,
        current_price=item.current_price,
        target_price=item.target_price,
        lowest_price_90days=item.lowest_price_90days,
        notification_enabled=item.notification_enabled,
        created_at=item.created_at.isoformat(),
    )


@router.delete("/{item_id}")
async def remove_from_wishlist(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관심상품 삭제"""
    result = await db.execute(
        select(WishlistItem).where(
            and_(
                WishlistItem.id == item_id,
                WishlistItem.user_id == current_user.id,
            )
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="관심상품을 찾을 수 없습니다",
        )

    await db.delete(item)
    await db.commit()

    return {"message": "관심상품이 삭제되었습니다"}


@router.put("/{item_id}", response_model=WishlistItemResponse)
async def update_wishlist_item(
    item_id: str,
    request: WishlistItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관심상품 수정 (목표가, 알림 설정 등)"""
    result = await db.execute(
        select(WishlistItem).where(
            and_(
                WishlistItem.id == item_id,
                WishlistItem.user_id == current_user.id,
            )
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="관심상품을 찾을 수 없습니다",
        )

    # 업데이트
    if request.target_price is not None:
        item.target_price = request.target_price
    if request.notification_enabled is not None:
        item.notification_enabled = request.notification_enabled
    if request.notes is not None:
        item.notes = request.notes

    await db.commit()
    await db.refresh(item)

    return WishlistItemResponse(
        id=str(item.id),
        product_id=item.product_id,
        product_name=item.product_name,
        product_image=item.product_image,
        product_link=item.product_link,
        mall_name=item.mall_name,
        category=item.category,
        current_price=item.current_price,
        target_price=item.target_price,
        lowest_price_90days=item.lowest_price_90days,
        notification_enabled=item.notification_enabled,
        created_at=item.created_at.isoformat(),
    )


@router.get("/{item_id}/price-history", response_model=List[PriceHistoryResponse])
async def get_price_history(
    item_id: str,
    days: int = 90,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """가격 이력 조회 (기본 90일)"""
    # 소유권 확인
    result = await db.execute(
        select(WishlistItem).where(
            and_(
                WishlistItem.id == item_id,
                WishlistItem.user_id == current_user.id,
            )
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="관심상품을 찾을 수 없습니다",
        )

    # 가격 이력 조회
    since = datetime.utcnow() - timedelta(days=days)
    history_result = await db.execute(
        select(PriceHistory)
        .where(
            and_(
                PriceHistory.wishlist_item_id == item_id,
                PriceHistory.recorded_at >= since,
            )
        )
        .order_by(PriceHistory.recorded_at.asc())
    )
    history = history_result.scalars().all()

    return [
        PriceHistoryResponse(
            price=h.price,
            recorded_at=h.recorded_at.isoformat(),
        )
        for h in history
    ]
