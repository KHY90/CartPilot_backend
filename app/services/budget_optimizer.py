"""
예산 분배 최적화 서비스
번들 품목별 예산 최적화 및 동적 재계산
"""
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.models.product import ProductCandidate
from app.services.compatibility_checker import get_compatibility_checker


class ItemBudget(BaseModel):
    """품목별 예산"""

    item_name: str = Field(..., description="품목명")
    min_budget: int = Field(..., description="최소 예산")
    max_budget: int = Field(..., description="최대 예산")
    suggested_budget: int = Field(..., description="권장 예산")
    priority: str = Field(default="normal", description="우선순위 (high/normal/low)")


class BudgetPlan(BaseModel):
    """예산 계획"""

    total_budget: int = Field(..., description="총 예산")
    items: List[ItemBudget] = Field(default_factory=list, description="품목별 예산")
    remaining_budget: int = Field(default=0, description="여유 예산")
    allocation_strategy: str = Field(default="balanced", description="분배 전략")


class SelectionResult(BaseModel):
    """상품 선택 결과"""

    item_name: str = Field(..., description="품목명")
    selected_product: Optional[ProductCandidate] = Field(None, description="선택된 상품")
    alternatives: List[ProductCandidate] = Field(default_factory=list, description="대안 상품")
    actual_price: int = Field(default=0, description="실제 가격")
    within_budget: bool = Field(default=True, description="예산 내 여부")


class OptimizationResult(BaseModel):
    """최적화 결과"""

    selections: List[SelectionResult] = Field(default_factory=list, description="선택 결과")
    total_spent: int = Field(default=0, description="총 사용 금액")
    remaining_budget: int = Field(default=0, description="남은 예산")
    savings: int = Field(default=0, description="절약 금액")
    optimization_notes: List[str] = Field(default_factory=list, description="최적화 노트")


class BudgetOptimizer:
    """예산 분배 최적화 서비스"""

    def __init__(self):
        self._checker = get_compatibility_checker()

    def create_budget_plan(
        self,
        items: List[str],
        total_budget: int,
        strategy: str = "balanced",
    ) -> BudgetPlan:
        """
        예산 계획 생성

        Args:
            items: 품목 리스트
            total_budget: 총 예산
            strategy: 분배 전략 (balanced/budget/premium)

        Returns:
            BudgetPlan: 예산 계획
        """
        # 호환성 검사로 그룹 감지
        compatibility = self._checker.check_compatibility(items)

        # 예산 분배 규칙 적용
        allocations = self._checker.get_budget_allocation(
            items, total_budget, compatibility.detected_group
        )

        # 전략에 따른 조정
        strategy_multipliers = {
            "budget": 0.75,
            "balanced": 1.0,
            "premium": 1.25,
        }
        multiplier = strategy_multipliers.get(strategy, 1.0)

        item_budgets: List[ItemBudget] = []
        total_suggested = 0

        for i, item in enumerate(items):
            min_budget, max_budget = allocations.get(item, (0, total_budget // len(items)))

            # 전략에 따라 권장 예산 조정
            if strategy == "budget":
                suggested = int(min_budget * 1.1)
            elif strategy == "premium":
                suggested = int(max_budget * 0.9)
            else:
                suggested = (min_budget + max_budget) // 2

            # 우선순위 결정 (첫 번째 품목이 주요 품목)
            priority = "high" if i == 0 else ("normal" if i < 3 else "low")

            item_budgets.append(ItemBudget(
                item_name=item,
                min_budget=int(min_budget * multiplier),
                max_budget=int(max_budget * multiplier),
                suggested_budget=suggested,
                priority=priority,
            ))
            total_suggested += suggested

        # 남은 예산 계산
        remaining = max(0, total_budget - total_suggested)

        return BudgetPlan(
            total_budget=total_budget,
            items=item_budgets,
            remaining_budget=remaining,
            allocation_strategy=strategy,
        )

    def optimize_selection(
        self,
        budget_plan: BudgetPlan,
        products_by_item: Dict[str, List[ProductCandidate]],
    ) -> OptimizationResult:
        """
        예산 계획에 따른 상품 선택 최적화

        Args:
            budget_plan: 예산 계획
            products_by_item: 품목별 상품 리스트

        Returns:
            OptimizationResult: 최적화 결과
        """
        selections: List[SelectionResult] = []
        total_spent = 0
        notes: List[str] = []

        # 우선순위대로 정렬
        priority_order = {"high": 0, "normal": 1, "low": 2}
        sorted_items = sorted(
            budget_plan.items,
            key=lambda x: priority_order.get(x.priority, 1)
        )

        remaining_total = budget_plan.total_budget

        for item_budget in sorted_items:
            item_name = item_budget.item_name
            products = products_by_item.get(item_name, [])

            if not products:
                selections.append(SelectionResult(
                    item_name=item_name,
                    selected_product=None,
                    alternatives=[],
                    actual_price=0,
                    within_budget=True,
                ))
                notes.append(f"'{item_name}'에 대한 검색 결과가 없습니다.")
                continue

            # 예산 범위 내 상품 필터링
            within_budget_products = [
                p for p in products
                if p.price <= item_budget.max_budget
            ]

            # 권장 예산에 가장 가까운 상품 선택
            selected = None
            if within_budget_products:
                # 권장 예산에 가장 가까운 상품
                within_budget_products.sort(
                    key=lambda p: abs(p.price - item_budget.suggested_budget)
                )
                selected = within_budget_products[0]
            else:
                # 예산 초과해도 가장 저렴한 상품
                products.sort(key=lambda p: p.price)
                selected = products[0]
                notes.append(f"'{item_name}' 예산 초과 - 가장 저렴한 상품 선택")

            # 대안 상품 (선택된 상품 제외)
            alternatives = [
                p for p in products[:5]
                if p.product_id != selected.product_id
            ][:3]

            actual_price = selected.price
            within_budget = actual_price <= item_budget.max_budget

            selections.append(SelectionResult(
                item_name=item_name,
                selected_product=selected,
                alternatives=alternatives,
                actual_price=actual_price,
                within_budget=within_budget,
            ))

            total_spent += actual_price
            remaining_total -= actual_price

        # 절약 금액 계산
        expected_spending = sum(ib.suggested_budget for ib in budget_plan.items)
        savings = max(0, expected_spending - total_spent)

        if savings > 0:
            notes.append(f"권장 예산 대비 {savings:,}원 절약!")

        return OptimizationResult(
            selections=selections,
            total_spent=total_spent,
            remaining_budget=max(0, budget_plan.total_budget - total_spent),
            savings=savings,
            optimization_notes=notes,
        )

    def recalculate_with_change(
        self,
        current_selections: List[SelectionResult],
        changed_item: str,
        new_product: ProductCandidate,
        total_budget: int,
        products_by_item: Dict[str, List[ProductCandidate]],
    ) -> OptimizationResult:
        """
        특정 품목 변경 시 나머지 품목 재계산

        Args:
            current_selections: 현재 선택 결과
            changed_item: 변경된 품목
            new_product: 새로 선택된 상품
            total_budget: 총 예산
            products_by_item: 품목별 상품 리스트

        Returns:
            OptimizationResult: 재계산된 결과
        """
        # 변경된 품목의 가격 차이 계산
        price_diff = 0
        for sel in current_selections:
            if sel.item_name == changed_item and sel.selected_product:
                price_diff = new_product.price - sel.selected_product.price
                break

        # 남은 예산 계산
        current_total = sum(
            s.actual_price for s in current_selections if s.item_name != changed_item
        )
        new_remaining = total_budget - current_total - new_product.price

        notes = []
        new_selections: List[SelectionResult] = []

        # 변경된 품목 업데이트
        for sel in current_selections:
            if sel.item_name == changed_item:
                alternatives = [
                    p for p in products_by_item.get(changed_item, [])[:5]
                    if p.product_id != new_product.product_id
                ][:3]

                new_selections.append(SelectionResult(
                    item_name=changed_item,
                    selected_product=new_product,
                    alternatives=alternatives,
                    actual_price=new_product.price,
                    within_budget=True,
                ))
            else:
                new_selections.append(sel)

        if price_diff > 0:
            notes.append(f"'{changed_item}' 가격 증가로 {price_diff:,}원 추가 지출")
        elif price_diff < 0:
            notes.append(f"'{changed_item}' 가격 감소로 {abs(price_diff):,}원 절약")

        total_spent = sum(s.actual_price for s in new_selections)

        return OptimizationResult(
            selections=new_selections,
            total_spent=total_spent,
            remaining_budget=max(0, total_budget - total_spent),
            savings=max(0, -price_diff) if price_diff < 0 else 0,
            optimization_notes=notes,
        )

    def suggest_adjustments(
        self,
        optimization_result: OptimizationResult,
        total_budget: int,
        products_by_item: Dict[str, List[ProductCandidate]],
    ) -> List[dict]:
        """
        예산 조정 제안

        Args:
            optimization_result: 현재 최적화 결과
            total_budget: 총 예산
            products_by_item: 품목별 상품 리스트

        Returns:
            List[dict]: 조정 제안 리스트
        """
        suggestions = []
        total_spent = optimization_result.total_spent

        # 예산 초과 시 절감 방안 제안
        if total_spent > total_budget:
            over_amount = total_spent - total_budget
            suggestions.append({
                "type": "over_budget",
                "message": f"총 예산을 {over_amount:,}원 초과했습니다.",
                "actions": [],
            })

            # 각 품목에서 더 저렴한 대안 찾기
            for sel in optimization_result.selections:
                for alt in sel.alternatives:
                    if alt.price < sel.actual_price:
                        savings = sel.actual_price - alt.price
                        suggestions[-1]["actions"].append({
                            "item": sel.item_name,
                            "current_price": sel.actual_price,
                            "alternative_price": alt.price,
                            "savings": savings,
                            "product": alt.model_dump() if hasattr(alt, 'model_dump') else alt,
                        })
                        break

        # 여유 예산 시 업그레이드 제안
        elif optimization_result.remaining_budget > total_budget * 0.1:
            extra = optimization_result.remaining_budget
            suggestions.append({
                "type": "extra_budget",
                "message": f"{extra:,}원의 여유 예산이 있습니다.",
                "actions": [],
            })

            # 각 품목에서 업그레이드 옵션 찾기
            for sel in optimization_result.selections:
                products = products_by_item.get(sel.item_name, [])
                for p in products:
                    if p.price > sel.actual_price and (p.price - sel.actual_price) <= extra:
                        upgrade_cost = p.price - sel.actual_price
                        suggestions[-1]["actions"].append({
                            "item": sel.item_name,
                            "current_price": sel.actual_price,
                            "upgrade_price": p.price,
                            "additional_cost": upgrade_cost,
                            "product": p.model_dump() if hasattr(p, 'model_dump') else p,
                        })
                        break

        return suggestions


# 싱글톤 인스턴스
_budget_optimizer: BudgetOptimizer | None = None


def get_budget_optimizer() -> BudgetOptimizer:
    """BudgetOptimizer 싱글톤 인스턴스 반환"""
    global _budget_optimizer
    if _budget_optimizer is None:
        _budget_optimizer = BudgetOptimizer()
    return _budget_optimizer
