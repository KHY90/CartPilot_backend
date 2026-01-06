"""
관심상품 API 엔드포인트
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.wishlist import WishlistItem, PriceHistory
from app.dependencies.auth import get_current_user
from app.services.naver_shopping import get_naver_client, NaverShoppingError
from app.services.price_predictor import get_price_predictor
from app.models.price_prediction import PricePrediction, PredictionSummary
from app.services.notifications.email_service import get_email_service

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
    alert_on_lowest: Optional[bool] = None
    alert_on_target: Optional[bool] = None
    alert_on_drop_percent: Optional[int] = None
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
    alert_on_lowest: bool
    alert_on_target: bool
    alert_on_drop_percent: Optional[int]
    created_at: str


class PriceHistoryResponse(BaseModel):
    """가격 이력 응답"""
    price: int
    recorded_at: str


class PriceAnalysisResponse(BaseModel):
    """가격 분석 응답"""
    current_price: int
    lowest_90days: Optional[int]
    highest_90days: Optional[int]
    average_90days: Optional[int]
    price_change_percent: Optional[float]  # 최저가 대비 현재가 변동률
    is_lowest: bool  # 현재가 = 90일 최저가 여부
    recommendation: str  # buy / wait / neutral
    data_points: int  # 수집된 가격 데이터 수


class PriceCheckResponse(BaseModel):
    """가격 체크 응답"""
    previous_price: int
    current_price: int
    price_changed: bool
    change_amount: int
    change_percent: float
    is_lowest: bool
    lowest_90days: Optional[int]


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
            alert_on_lowest=item.alert_on_lowest,
            alert_on_target=item.alert_on_target,
            alert_on_drop_percent=item.alert_on_drop_percent,
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

    # flush하여 item.id를 먼저 할당받음
    await db.flush()

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
        alert_on_lowest=item.alert_on_lowest,
        alert_on_target=item.alert_on_target,
        alert_on_drop_percent=item.alert_on_drop_percent,
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
    if request.alert_on_lowest is not None:
        item.alert_on_lowest = request.alert_on_lowest
    if request.alert_on_target is not None:
        item.alert_on_target = request.alert_on_target
    if request.alert_on_drop_percent is not None:
        item.alert_on_drop_percent = request.alert_on_drop_percent
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
        alert_on_lowest=item.alert_on_lowest,
        alert_on_target=item.alert_on_target,
        alert_on_drop_percent=item.alert_on_drop_percent,
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


@router.get("/{item_id}/price-analysis", response_model=PriceAnalysisResponse)
async def get_price_analysis(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    가격 분석 데이터 조회
    - 90일 최저가/최고가/평균가
    - 현재가 대비 변동률
    - 구매 추천 여부
    """
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

    # 90일 가격 이력 조회
    since = datetime.utcnow() - timedelta(days=90)
    history_result = await db.execute(
        select(PriceHistory.price)
        .where(
            and_(
                PriceHistory.wishlist_item_id == item_id,
                PriceHistory.recorded_at >= since,
            )
        )
    )
    prices = [row[0] for row in history_result.fetchall()]

    # 통계 계산
    if prices:
        lowest = min(prices)
        highest = max(prices)
        average = round(sum(prices) / len(prices))

        # 현재가 대비 최저가 변동률
        if lowest > 0:
            change_percent = round(((item.current_price - lowest) / lowest) * 100, 1)
        else:
            change_percent = 0.0

        is_lowest = item.current_price <= lowest

        # 구매 추천 로직
        if is_lowest:
            recommendation = "buy"
        elif change_percent <= 5:
            recommendation = "neutral"
        else:
            recommendation = "wait"
    else:
        lowest = None
        highest = None
        average = None
        change_percent = None
        is_lowest = False
        recommendation = "neutral"

    return PriceAnalysisResponse(
        current_price=item.current_price,
        lowest_90days=lowest,
        highest_90days=highest,
        average_90days=average,
        price_change_percent=change_percent,
        is_lowest=is_lowest,
        recommendation=recommendation,
        data_points=len(prices),
    )


@router.post("/{item_id}/check-price", response_model=PriceCheckResponse)
async def check_price_now(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    수동 가격 체크
    - 네이버 쇼핑 API로 현재 가격 즉시 조회
    - 가격 변동 시 DB 업데이트
    """
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

    previous_price = item.current_price

    # 네이버 쇼핑 API로 현재 가격 조회
    try:
        naver_client = get_naver_client()
        search_result = await naver_client.search(
            query=item.product_name,
            display=5,
        )

        if not search_result.items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="상품 검색 결과가 없습니다",
            )

        current_price = search_result.items[0].price

    except NaverShoppingError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"네이버 쇼핑 API 오류: {str(e)}",
        )

    # 가격 변동 계산
    price_changed = current_price != previous_price
    change_amount = current_price - previous_price
    if previous_price > 0:
        change_percent = round((change_amount / previous_price) * 100, 1)
    else:
        change_percent = 0.0

    # 가격이 변경된 경우 DB 업데이트
    if price_changed:
        # 가격 이력 추가
        price_history = PriceHistory(
            wishlist_item_id=item.id,
            price=current_price,
            recorded_at=datetime.utcnow(),
        )
        db.add(price_history)

        # 현재 가격 업데이트
        item.current_price = current_price

        # 90일 최저가 재계산
        since = datetime.utcnow() - timedelta(days=90)
        min_result = await db.execute(
            select(func.min(PriceHistory.price))
            .where(
                and_(
                    PriceHistory.wishlist_item_id == item_id,
                    PriceHistory.recorded_at >= since,
                )
            )
        )
        min_price = min_result.scalar()
        item.lowest_price_90days = min(min_price, current_price) if min_price else current_price

        await db.commit()

    # 최저가 여부 확인
    is_lowest = False
    if item.lowest_price_90days:
        is_lowest = current_price <= item.lowest_price_90days

    return PriceCheckResponse(
        previous_price=previous_price,
        current_price=current_price,
        price_changed=price_changed,
        change_amount=change_amount,
        change_percent=change_percent,
        is_lowest=is_lowest,
        lowest_90days=item.lowest_price_90days,
    )


@router.get("/{item_id}/prediction", response_model=PricePrediction)
async def get_price_prediction(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    가격 예측 조회
    - 추세 분석 (상승/하락/안정)
    - 다가오는 세일 정보
    - 구매 추천 (지금 구매 / 대기 / 중립)
    """
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

    # 90일 가격 이력 조회
    since = datetime.utcnow() - timedelta(days=90)
    history_result = await db.execute(
        select(PriceHistory)
        .where(
            and_(
                PriceHistory.wishlist_item_id == item_id,
                PriceHistory.recorded_at >= since,
            )
        )
        .order_by(PriceHistory.recorded_at.desc())
    )
    history = history_result.scalars().all()

    # 가격 이력을 (datetime, price) 튜플 리스트로 변환
    price_history = [(h.recorded_at, h.price) for h in history]

    # 예측 수행
    predictor = get_price_predictor()
    prediction = predictor.predict(
        product_id=item.product_id,
        current_price=item.current_price,
        price_history=price_history,
        category=item.category,
    )

    return prediction


@router.get("/predictions/summary", response_model=PredictionSummary)
async def get_predictions_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    모든 관심상품의 예측 요약
    - 지금 구매 추천 수
    - 대기 추천 수
    - 다가오는 세일 정보
    - 예상 절약 금액
    """
    # 사용자의 모든 관심상품 조회
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.user_id == current_user.id)
    )
    items = result.scalars().all()

    if not items:
        return PredictionSummary(
            total_products=0,
            buy_now_count=0,
            wait_count=0,
            neutral_count=0,
            next_sale=None,
            potential_savings=0,
        )

    predictor = get_price_predictor()
    predictions = []

    for item in items:
        # 각 상품의 가격 이력 조회
        since = datetime.utcnow() - timedelta(days=90)
        history_result = await db.execute(
            select(PriceHistory)
            .where(
                and_(
                    PriceHistory.wishlist_item_id == item.id,
                    PriceHistory.recorded_at >= since,
                )
            )
            .order_by(PriceHistory.recorded_at.desc())
        )
        history = history_result.scalars().all()
        price_history = [(h.recorded_at, h.price) for h in history]

        prediction = predictor.predict(
            product_id=item.product_id,
            current_price=item.current_price,
            price_history=price_history,
            category=item.category,
        )
        predictions.append(prediction)

    return predictor.get_summary(predictions)


class TestEmailRequest(BaseModel):
    """테스트 이메일 요청"""

    email: str


class TestEmailResponse(BaseModel):
    """테스트 이메일 응답"""

    success: bool
    message: str


@router.post("/notifications/test-email", response_model=TestEmailResponse)
async def send_test_email(
    request: TestEmailRequest,
    current_user: User = Depends(get_current_user),
):
    """
    테스트 이메일 발송
    - 이메일 설정 확인용
    """
    email_service = get_email_service()

    if not email_service.is_available():
        return TestEmailResponse(
            success=False,
            message="이메일 서비스가 설정되지 않았습니다. 관리자에게 문의하세요.",
        )

    try:
        success = await email_service.send_welcome_notification(request.email)

        if success:
            return TestEmailResponse(
                success=True,
                message=f"{request.email}로 테스트 이메일을 발송했습니다.",
            )
        else:
            return TestEmailResponse(
                success=False,
                message="이메일 발송에 실패했습니다. 이메일 주소를 확인해주세요.",
            )
    except Exception as e:
        return TestEmailResponse(
            success=False,
            message=f"이메일 발송 중 오류가 발생했습니다: {str(e)}",
        )


@router.get("/notifications/status")
async def get_notification_status(
    current_user: User = Depends(get_current_user),
):
    """
    알림 서비스 상태 확인
    """
    email_service = get_email_service()

    return {
        "email_available": email_service.is_available(),
        "user_email_enabled": current_user.email_notification_enabled,
        "user_notification_email": current_user.notification_email or current_user.email,
    }
