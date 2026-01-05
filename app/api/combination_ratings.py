"""
조합 별점 API 엔드포인트
묶음 구매 조합에 대한 평가 관리
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import json

from app.database import get_db
from app.models.user import User
from app.models.combination_rating import CombinationRating
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/combination-ratings", tags=["조합 별점"])


# ==================== Request/Response Models ====================
class CombinationRatingCreate(BaseModel):
    """조합 별점 등록/수정 요청"""
    combination_id: str = Field(..., description="조합 ID (A, B, C)")
    product_ids: List[str] = Field(..., min_length=1, description="조합 내 상품 ID 목록")
    product_names: Optional[List[str]] = Field(None, description="조합 내 상품명 목록")
    total_price: Optional[int] = Field(None, description="조합 총 가격")
    item_categories: Optional[List[str]] = Field(None, description="품목 카테고리 목록")
    rating: int = Field(..., ge=1, le=5, description="별점 (1-5)")


class CombinationRatingResponse(BaseModel):
    """조합 별점 응답"""
    id: str
    combination_hash: str
    combination_id: str
    product_ids: List[str]
    product_names: List[str]
    total_price: Optional[int]
    item_categories: List[str]
    rating: int
    created_at: str


# ==================== API Endpoints ====================
@router.post("", response_model=CombinationRatingResponse)
async def create_or_update_combination_rating(
    request: CombinationRatingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """조합 별점 등록 또는 수정 (같은 조합이면 업데이트)"""
    # 조합 해시 생성
    combination_hash = CombinationRating.generate_hash(request.product_ids)

    # 기존 별점 확인
    result = await db.execute(
        select(CombinationRating).where(
            and_(
                CombinationRating.user_id == current_user.id,
                CombinationRating.combination_hash == combination_hash,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 업데이트
        existing.rating = request.rating
        existing.combination_id = request.combination_id
        if request.product_names:
            existing.product_names = json.dumps(request.product_names, ensure_ascii=False)
        if request.total_price:
            existing.total_price = request.total_price
        if request.item_categories:
            existing.item_categories = json.dumps(request.item_categories, ensure_ascii=False)
        await db.commit()
        await db.refresh(existing)
        rating = existing
    else:
        # 신규 생성
        rating = CombinationRating(
            user_id=current_user.id,
            combination_hash=combination_hash,
            combination_id=request.combination_id,
            product_ids=json.dumps(request.product_ids),
            product_names=json.dumps(request.product_names or [], ensure_ascii=False),
            total_price=request.total_price,
            item_categories=json.dumps(request.item_categories or [], ensure_ascii=False),
            rating=request.rating,
        )
        db.add(rating)
        await db.commit()
        await db.refresh(rating)

    return CombinationRatingResponse(
        id=str(rating.id),
        combination_hash=rating.combination_hash,
        combination_id=rating.combination_id,
        product_ids=json.loads(rating.product_ids) if rating.product_ids else [],
        product_names=json.loads(rating.product_names) if rating.product_names else [],
        total_price=rating.total_price,
        item_categories=json.loads(rating.item_categories) if rating.item_categories else [],
        rating=rating.rating,
        created_at=rating.created_at.isoformat(),
    )


@router.get("", response_model=List[CombinationRatingResponse])
async def get_my_combination_ratings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 조합 별점 목록 조회"""
    query = select(CombinationRating).where(
        CombinationRating.user_id == current_user.id
    ).order_by(CombinationRating.created_at.desc())

    result = await db.execute(query)
    ratings = result.scalars().all()

    return [
        CombinationRatingResponse(
            id=str(r.id),
            combination_hash=r.combination_hash,
            combination_id=r.combination_id,
            product_ids=json.loads(r.product_ids) if r.product_ids else [],
            product_names=json.loads(r.product_names) if r.product_names else [],
            total_price=r.total_price,
            item_categories=json.loads(r.item_categories) if r.item_categories else [],
            rating=r.rating,
            created_at=r.created_at.isoformat(),
        )
        for r in ratings
    ]


@router.get("/by-hash/{combination_hash}", response_model=CombinationRatingResponse)
async def get_combination_rating_by_hash(
    combination_hash: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 조합의 내 별점 조회 (해시로)"""
    result = await db.execute(
        select(CombinationRating).where(
            and_(
                CombinationRating.user_id == current_user.id,
                CombinationRating.combination_hash == combination_hash,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 조합에 대한 별점이 없습니다",
        )

    return CombinationRatingResponse(
        id=str(rating.id),
        combination_hash=rating.combination_hash,
        combination_id=rating.combination_id,
        product_ids=json.loads(rating.product_ids) if rating.product_ids else [],
        product_names=json.loads(rating.product_names) if rating.product_names else [],
        total_price=rating.total_price,
        item_categories=json.loads(rating.item_categories) if rating.item_categories else [],
        rating=rating.rating,
        created_at=rating.created_at.isoformat(),
    )


@router.post("/by-products", response_model=Optional[CombinationRatingResponse])
async def get_combination_rating_by_products(
    product_ids: List[str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 조합의 내 별점 조회 (상품 ID 목록으로)"""
    combination_hash = CombinationRating.generate_hash(product_ids)

    result = await db.execute(
        select(CombinationRating).where(
            and_(
                CombinationRating.user_id == current_user.id,
                CombinationRating.combination_hash == combination_hash,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        return None

    return CombinationRatingResponse(
        id=str(rating.id),
        combination_hash=rating.combination_hash,
        combination_id=rating.combination_id,
        product_ids=json.loads(rating.product_ids) if rating.product_ids else [],
        product_names=json.loads(rating.product_names) if rating.product_names else [],
        total_price=rating.total_price,
        item_categories=json.loads(rating.item_categories) if rating.item_categories else [],
        rating=rating.rating,
        created_at=rating.created_at.isoformat(),
    )


@router.delete("/by-hash/{combination_hash}")
async def delete_combination_rating(
    combination_hash: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """조합 별점 삭제"""
    result = await db.execute(
        select(CombinationRating).where(
            and_(
                CombinationRating.user_id == current_user.id,
                CombinationRating.combination_hash == combination_hash,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 조합에 대한 별점이 없습니다",
        )

    await db.delete(rating)
    await db.commit()

    return {"message": "조합 별점이 삭제되었습니다"}
