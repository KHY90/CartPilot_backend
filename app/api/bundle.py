"""
번들 동적 조합 API
품목 변경, 예산 조정, 호환성 검사 등
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.compatibility_checker import get_compatibility_checker, CompatibilityResult
from app.services.budget_optimizer import get_budget_optimizer, BudgetPlan
from app.services.naver_shopping import get_naver_client, NaverShoppingError
from app.models.product import ProductCandidate

router = APIRouter(prefix="/bundle", tags=["번들 조합"])


# ==================== Request/Response Models ====================
class CheckCompatibilityRequest(BaseModel):
    """호환성 검사 요청"""

    items: List[str] = Field(..., min_length=1, description="품목 리스트")


class BudgetPlanRequest(BaseModel):
    """예산 계획 요청"""

    items: List[str] = Field(..., min_length=1, description="품목 리스트")
    total_budget: int = Field(..., gt=0, description="총 예산")
    strategy: str = Field(default="balanced", description="전략 (budget/balanced/premium)")


class SuggestItemsRequest(BaseModel):
    """보완 품목 제안 요청"""

    current_items: List[str] = Field(..., min_length=1, description="현재 품목 리스트")
    max_suggestions: int = Field(default=3, ge=1, le=5, description="최대 제안 수")


class RecalculateRequest(BaseModel):
    """동적 재계산 요청"""

    items: List[str] = Field(..., min_length=1, description="품목 리스트")
    total_budget: int = Field(..., gt=0, description="총 예산")
    changed_item: str = Field(..., description="변경된 품목")
    new_product_id: str = Field(..., description="새로 선택된 상품 ID")
    strategy: str = Field(default="balanced", description="전략")


class ItemProductsRequest(BaseModel):
    """품목별 상품 검색 요청"""

    items: List[str] = Field(..., min_length=1, max_length=5, description="품목 리스트")
    products_per_item: int = Field(default=10, ge=1, le=20, description="품목당 상품 수")


class SuggestedItem(BaseModel):
    """제안 품목"""

    name: str
    reason: str
    priority: str


class ItemProducts(BaseModel):
    """품목별 상품 목록"""

    item_name: str
    products: List[dict]
    count: int


# ==================== API Endpoints ====================
@router.post("/check-compatibility", response_model=CompatibilityResult)
async def check_compatibility(request: CheckCompatibilityRequest):
    """
    품목 간 호환성 검사
    - 비호환 쌍 확인
    - 호환 그룹 감지
    - 추천 품목 제안
    """
    checker = get_compatibility_checker()
    result = checker.check_compatibility(request.items)
    return result


@router.post("/budget-plan", response_model=BudgetPlan)
async def create_budget_plan(request: BudgetPlanRequest):
    """
    예산 분배 계획 생성
    - 품목별 예산 범위 계산
    - 전략에 따른 조정
    """
    optimizer = get_budget_optimizer()
    plan = optimizer.create_budget_plan(
        items=request.items,
        total_budget=request.total_budget,
        strategy=request.strategy,
    )
    return plan


@router.post("/suggest-items", response_model=List[SuggestedItem])
async def suggest_complementary_items(request: SuggestItemsRequest):
    """
    보완 품목 제안
    - 호환 그룹 기반 추천
    - 우선순위 포함
    """
    checker = get_compatibility_checker()
    suggestions = checker.suggest_complementary_items(
        current_items=request.current_items,
        max_suggestions=request.max_suggestions,
    )
    return [SuggestedItem(**s) for s in suggestions]


@router.post("/search-items", response_model=List[ItemProducts])
async def search_items_products(request: ItemProductsRequest):
    """
    품목별 상품 검색
    - 각 품목에 대해 네이버 쇼핑 검색
    - 예산 최적화용 상품 목록 반환
    """
    naver_client = get_naver_client()
    results: List[ItemProducts] = []

    for item in request.items:
        try:
            search_result = await naver_client.search(
                query=item,
                display=request.products_per_item,
                sort="sim",
            )
            products = [
                {
                    "product_id": p.product_id,
                    "title": p.title,
                    "price": p.price,
                    "image": str(p.image) if p.image else None,
                    "mall_name": p.mall_name,
                    "link": str(p.link),
                }
                for p in search_result.items
            ]
            results.append(ItemProducts(
                item_name=item,
                products=products,
                count=len(products),
            ))
        except NaverShoppingError:
            results.append(ItemProducts(
                item_name=item,
                products=[],
                count=0,
            ))

    return results


@router.post("/recalculate")
async def recalculate_bundle(request: RecalculateRequest):
    """
    특정 품목 변경 시 번들 재계산
    - 변경된 품목 반영
    - 나머지 품목 예산 재조정
    - 최적화 결과 반환
    """
    optimizer = get_budget_optimizer()
    naver_client = get_naver_client()

    # 모든 품목 상품 검색
    products_by_item = {}
    for item in request.items:
        try:
            result = await naver_client.search(query=item, display=10, sort="sim")
            products_by_item[item] = result.items
        except NaverShoppingError:
            products_by_item[item] = []

    # 새 상품 찾기
    new_product = None
    for item, products in products_by_item.items():
        for p in products:
            if p.product_id == request.new_product_id:
                new_product = p
                break
        if new_product:
            break

    if not new_product:
        raise HTTPException(status_code=404, detail="선택한 상품을 찾을 수 없습니다")

    # 예산 계획 생성
    budget_plan = optimizer.create_budget_plan(
        items=request.items,
        total_budget=request.total_budget,
        strategy=request.strategy,
    )

    # 최적화 수행
    optimization_result = optimizer.optimize_selection(
        budget_plan=budget_plan,
        products_by_item=products_by_item,
    )

    # 조정 제안
    suggestions = optimizer.suggest_adjustments(
        optimization_result=optimization_result,
        total_budget=request.total_budget,
        products_by_item=products_by_item,
    )

    return {
        "optimization": {
            "total_spent": optimization_result.total_spent,
            "remaining_budget": optimization_result.remaining_budget,
            "savings": optimization_result.savings,
            "notes": optimization_result.optimization_notes,
            "selections": [
                {
                    "item_name": sel.item_name,
                    "product": sel.selected_product.model_dump() if sel.selected_product else None,
                    "actual_price": sel.actual_price,
                    "within_budget": sel.within_budget,
                    "alternatives": [
                        alt.model_dump() for alt in sel.alternatives
                    ],
                }
                for sel in optimization_result.selections
            ],
        },
        "suggestions": suggestions,
    }


@router.get("/price-tiers")
async def get_price_tiers():
    """
    가격 티어 정보 조회
    - budget/mid_range/premium 티어 정보
    """
    checker = get_compatibility_checker()
    return checker.rules.get("price_tiers", {})
