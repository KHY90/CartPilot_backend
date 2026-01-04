"""
별점 API 엔드포인트
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.models.user import User
from app.models.rating import ProductRating
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/ratings", tags=["별점"])


# ==================== Request/Response Models ====================
class RatingCreate(BaseModel):
    """별점 등록/수정 요청"""
    product_id: str
    product_name: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[int] = None
    rating: int = Field(..., ge=1, le=5, description="별점 (1-5)")


class RatingResponse(BaseModel):
    """별점 응답"""
    id: str
    product_id: str
    product_name: Optional[str]
    category: Optional[str]
    brand: Optional[str]
    price: Optional[int]
    rating: int
    created_at: str


class CategoryPreference(BaseModel):
    """카테고리별 선호도"""
    category: str
    avg_rating: float
    count: int


class PreferencesResponse(BaseModel):
    """성향 분석 결과"""
    total_ratings: int
    avg_rating: float
    category_preferences: List[CategoryPreference]
    preferred_price_range: Optional[str]


# ==================== API Endpoints ====================
@router.post("", response_model=RatingResponse)
async def create_or_update_rating(
    request: RatingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """별점 등록 또는 수정 (같은 상품이면 업데이트)"""
    # 기존 별점 확인
    result = await db.execute(
        select(ProductRating).where(
            and_(
                ProductRating.user_id == current_user.id,
                ProductRating.product_id == request.product_id,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 업데이트
        existing.rating = request.rating
        if request.product_name:
            existing.product_name = request.product_name
        if request.category:
            existing.category = request.category
        if request.brand:
            existing.brand = request.brand
        if request.price:
            existing.price = request.price
        await db.commit()
        await db.refresh(existing)
        rating = existing
    else:
        # 신규 생성
        rating = ProductRating(
            user_id=current_user.id,
            product_id=request.product_id,
            product_name=request.product_name,
            category=request.category,
            brand=request.brand,
            price=request.price,
            rating=request.rating,
        )
        db.add(rating)
        await db.commit()
        await db.refresh(rating)

    return RatingResponse(
        id=str(rating.id),
        product_id=rating.product_id,
        product_name=rating.product_name,
        category=rating.category,
        brand=rating.brand,
        price=rating.price,
        rating=rating.rating,
        created_at=rating.created_at.isoformat(),
    )


@router.get("", response_model=List[RatingResponse])
async def get_my_ratings(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 별점 목록 조회"""
    query = select(ProductRating).where(ProductRating.user_id == current_user.id)

    if category:
        query = query.where(ProductRating.category == category)

    query = query.order_by(ProductRating.created_at.desc())

    result = await db.execute(query)
    ratings = result.scalars().all()

    return [
        RatingResponse(
            id=str(r.id),
            product_id=r.product_id,
            product_name=r.product_name,
            category=r.category,
            brand=r.brand,
            price=r.price,
            rating=r.rating,
            created_at=r.created_at.isoformat(),
        )
        for r in ratings
    ]


@router.get("/{product_id}", response_model=RatingResponse)
async def get_rating_for_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 상품의 내 별점 조회"""
    result = await db.execute(
        select(ProductRating).where(
            and_(
                ProductRating.user_id == current_user.id,
                ProductRating.product_id == product_id,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 상품에 대한 별점이 없습니다",
        )

    return RatingResponse(
        id=str(rating.id),
        product_id=rating.product_id,
        product_name=rating.product_name,
        category=rating.category,
        brand=rating.brand,
        price=rating.price,
        rating=rating.rating,
        created_at=rating.created_at.isoformat(),
    )


@router.delete("/{product_id}")
async def delete_rating(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """별점 삭제"""
    result = await db.execute(
        select(ProductRating).where(
            and_(
                ProductRating.user_id == current_user.id,
                ProductRating.product_id == product_id,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 상품에 대한 별점이 없습니다",
        )

    await db.delete(rating)
    await db.commit()

    return {"message": "별점이 삭제되었습니다"}


@router.get("/analysis/preferences", response_model=PreferencesResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 성향 분석 결과 조회"""
    # 전체 통계
    total_result = await db.execute(
        select(
            func.count(ProductRating.id).label("count"),
            func.avg(ProductRating.rating).label("avg"),
        ).where(ProductRating.user_id == current_user.id)
    )
    total_stats = total_result.one()
    total_count = total_stats.count or 0
    avg_rating = float(total_stats.avg) if total_stats.avg else 0.0

    # 카테고리별 선호도
    category_result = await db.execute(
        select(
            ProductRating.category,
            func.avg(ProductRating.rating).label("avg_rating"),
            func.count(ProductRating.id).label("count"),
        )
        .where(
            and_(
                ProductRating.user_id == current_user.id,
                ProductRating.category.isnot(None),
            )
        )
        .group_by(ProductRating.category)
        .order_by(func.avg(ProductRating.rating).desc())
    )
    category_stats = category_result.all()

    category_preferences = [
        CategoryPreference(
            category=stat.category,
            avg_rating=round(float(stat.avg_rating), 1),
            count=stat.count,
        )
        for stat in category_stats
    ]

    # 선호 가격대 분석 (4-5점 준 상품들의 가격대)
    price_result = await db.execute(
        select(func.avg(ProductRating.price)).where(
            and_(
                ProductRating.user_id == current_user.id,
                ProductRating.rating >= 4,
                ProductRating.price.isnot(None),
            )
        )
    )
    avg_preferred_price = price_result.scalar()

    preferred_price_range = None
    if avg_preferred_price:
        price = int(avg_preferred_price)
        if price < 30000:
            preferred_price_range = "3만원 미만"
        elif price < 50000:
            preferred_price_range = "3-5만원"
        elif price < 100000:
            preferred_price_range = "5-10만원"
        else:
            preferred_price_range = "10만원 이상"

    return PreferencesResponse(
        total_ratings=total_count,
        avg_rating=round(avg_rating, 1),
        category_preferences=category_preferences,
        preferred_price_range=preferred_price_range,
    )
