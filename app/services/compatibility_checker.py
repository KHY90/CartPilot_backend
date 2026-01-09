"""
호환성 검증 서비스
번들 품목 간 호환성 검사 및 추천
"""
import json
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class CompatibilityResult(BaseModel):
    """호환성 검사 결과"""

    is_compatible: bool = Field(..., description="호환 여부")
    warnings: List[str] = Field(default_factory=list, description="경고 메시지")
    suggestions: List[str] = Field(default_factory=list, description="추천 품목")
    detected_group: Optional[str] = Field(None, description="감지된 호환 그룹")


class CompatibilityChecker:
    """호환성 검증 서비스"""

    def __init__(self):
        self._rules: dict | None = None
        self._rules_path = Path(__file__).parent.parent / "data" / "compatibility_rules.json"

    @property
    def rules(self) -> dict:
        """호환성 규칙 데이터 (lazy loading)"""
        if self._rules is None:
            try:
                with open(self._rules_path, "r", encoding="utf-8") as f:
                    self._rules = json.load(f)
            except FileNotFoundError:
                self._rules = {
                    "compatibility_groups": {},
                    "incompatible_pairs": [],
                    "budget_allocation_rules": {},
                    "category_keywords": {},
                }
        return self._rules

    def _normalize_item(self, item: str) -> str:
        """품목명 정규화"""
        # 불필요한 접미사 제거
        item = item.lower().strip()
        for suffix in ["추천", "가성비", "좋은", "인기", "최고"]:
            item = item.replace(suffix, "")
        return item.strip()

    def _match_category(self, item: str) -> Optional[str]:
        """품목을 카테고리에 매칭"""
        normalized = self._normalize_item(item)

        for category, keywords in self.rules.get("category_keywords", {}).items():
            for kw in keywords:
                if kw.lower() in normalized or normalized in kw.lower():
                    return category

        return None

    def _detect_group(self, items: List[str]) -> Optional[str]:
        """품목 리스트에서 호환 그룹 감지"""
        item_categories = [self._match_category(item) for item in items]

        for group_name, group_data in self.rules.get("compatibility_groups", {}).items():
            required = group_data.get("required", [])
            recommended = group_data.get("recommended", [])

            # 필수 품목 중 하나라도 포함되어 있는지 확인
            has_required = any(
                cat in required or any(cat and req.lower() in cat.lower() for req in required)
                for cat in item_categories
                if cat
            )

            # 추천 품목 중 일부라도 포함되어 있는지 확인
            has_recommended = any(
                cat in recommended or any(cat and rec.lower() in cat.lower() for rec in recommended)
                for cat in item_categories
                if cat
            )

            if has_required or (has_recommended and len([c for c in item_categories if c]) >= 2):
                return group_name

        return None

    def check_compatibility(self, items: List[str]) -> CompatibilityResult:
        """
        품목 리스트의 호환성 검사

        Args:
            items: 품목명 리스트

        Returns:
            CompatibilityResult: 호환성 검사 결과
        """
        warnings = []
        suggestions = []
        is_compatible = True

        # 비호환 쌍 검사
        normalized_items = [self._normalize_item(item) for item in items]

        for pair in self.rules.get("incompatible_pairs", []):
            pair_lower = [p.lower() for p in pair]
            matches = [
                item for item in normalized_items
                if any(p in item or item in p for p in pair_lower)
            ]
            if len(matches) >= 2:
                is_compatible = False
                warnings.append(f"'{pair[0]}'와 '{pair[1]}'은 함께 구매하기 적합하지 않습니다.")

        # 호환 그룹 감지
        detected_group = self._detect_group(items)

        # 그룹에 맞는 추천 품목 제안
        if detected_group:
            group_data = self.rules.get("compatibility_groups", {}).get(detected_group, {})
            recommended = group_data.get("recommended", [])
            optional = group_data.get("optional", [])

            # 현재 품목에 없는 추천/선택 품목 제안
            for rec in recommended + optional[:3]:
                rec_lower = rec.lower()
                if not any(rec_lower in item or item in rec_lower for item in normalized_items):
                    suggestions.append(rec)
                    if len(suggestions) >= 3:
                        break

        return CompatibilityResult(
            is_compatible=is_compatible,
            warnings=warnings,
            suggestions=suggestions[:3],
            detected_group=detected_group,
        )

    def get_budget_allocation(
        self,
        items: List[str],
        total_budget: int,
        detected_group: Optional[str] = None,
    ) -> dict[str, Tuple[int, int]]:
        """
        예산 배분 계산

        Args:
            items: 품목 리스트
            total_budget: 총 예산
            detected_group: 감지된 호환 그룹

        Returns:
            dict: 품목별 (최소 예산, 최대 예산) 튜플
        """
        allocation = {}
        allocation_rules = self.rules.get("budget_allocation_rules", {})

        # 그룹별 규칙 사용
        group_rules = allocation_rules.get(detected_group, allocation_rules.get("default", {}))

        # 품목별 예산 계산
        remaining_budget = total_budget
        allocated_count = 0

        for item in items:
            normalized = self._normalize_item(item)
            matched_category = self._match_category(item)

            # 카테고리별 비율 찾기
            ratio = None
            if matched_category:
                ratio = group_rules.get(matched_category)

            if ratio is None:
                # 기본 비율 적용
                if allocated_count == 0:
                    ratio = group_rules.get("primary", 0.5)
                elif allocated_count == 1:
                    ratio = group_rules.get("secondary", 0.3)
                elif allocated_count == 2:
                    ratio = group_rules.get("tertiary", 0.15)
                else:
                    ratio = group_rules.get("other", 0.05)

            # 최소/최대 예산 계산 (±30% 범위)
            base_budget = int(total_budget * ratio)
            min_budget = int(base_budget * 0.7)
            max_budget = int(base_budget * 1.3)

            allocation[item] = (min_budget, max_budget)
            allocated_count += 1

        return allocation

    def suggest_complementary_items(
        self,
        current_items: List[str],
        max_suggestions: int = 3,
    ) -> List[dict]:
        """
        보완 품목 제안

        Args:
            current_items: 현재 품목 리스트
            max_suggestions: 최대 제안 수

        Returns:
            List[dict]: 제안 품목 리스트 [{name, reason}]
        """
        compatibility = self.check_compatibility(current_items)
        suggestions = []

        if compatibility.detected_group:
            group_data = self.rules.get("compatibility_groups", {}).get(
                compatibility.detected_group, {}
            )

            normalized_items = [self._normalize_item(item) for item in current_items]

            # 추천 품목 먼저
            for rec in group_data.get("recommended", []):
                rec_lower = rec.lower()
                if not any(rec_lower in item or item in rec_lower for item in normalized_items):
                    suggestions.append({
                        "name": rec,
                        "reason": f"{compatibility.detected_group} 구성에 추천되는 품목",
                        "priority": "recommended",
                    })

            # 선택 품목
            for opt in group_data.get("optional", []):
                opt_lower = opt.lower()
                if not any(opt_lower in item or item in opt_lower for item in normalized_items):
                    suggestions.append({
                        "name": opt,
                        "reason": "선택적으로 추가하면 좋은 품목",
                        "priority": "optional",
                    })

        return suggestions[:max_suggestions]

    def get_upgrade_suggestions(
        self,
        item: str,
        level: str = "다음단계",
    ) -> List[dict]:
        """
        업그레이드 제안

        Args:
            item: 현재 품목
            level: "다음단계" 또는 "고급업그레이드"

        Returns:
            List[dict]: 업그레이드 제안 [{name, reason}]
        """
        upgrade_suggestions = self.rules.get("upgrade_suggestions", {})
        normalized = self._normalize_item(item)
        suggestions = []

        # 품목에 해당하는 업그레이드 찾기
        for category, upgrades in upgrade_suggestions.items():
            category_lower = category.lower()
            if category_lower in normalized or normalized in category_lower:
                items = upgrades.get(level, [])
                for upgrade_item in items:
                    suggestions.append({
                        "name": upgrade_item,
                        "reason": f"{category} 업그레이드 추천",
                        "level": level,
                    })
                break

        return suggestions

    def get_gift_recommendations(
        self,
        occasion: Optional[str] = None,
        recipient: Optional[str] = None,
        age_group: Optional[str] = None,
    ) -> List[str]:
        """
        선물 추천

        Args:
            occasion: 행사 (생일, 결혼, 집들이 등)
            recipient: 대상 (남성, 여성)
            age_group: 연령대 (20대, 30대)

        Returns:
            List[str]: 추천 선물 카테고리 리스트
        """
        gift_recommendations = self.rules.get("gift_recommendations", {})

        # 키 조합 생성 (예: "생일_남성_20대", "결혼선물", "집들이")
        possible_keys = []

        if occasion and recipient and age_group:
            possible_keys.append(f"{occasion}_{recipient}_{age_group}")
        if occasion and recipient:
            possible_keys.append(f"{occasion}_{recipient}")
        if occasion:
            possible_keys.append(f"{occasion}선물")
            possible_keys.append(occasion)
        if recipient and age_group:
            possible_keys.append(f"{recipient}_{age_group}")

        # 매칭되는 추천 찾기
        for key in possible_keys:
            if key in gift_recommendations:
                return gift_recommendations[key]

        # 부분 매칭 시도
        for gift_key, items in gift_recommendations.items():
            if occasion and occasion in gift_key:
                return items
            if recipient and recipient in gift_key:
                return items

        return []

    def get_brand_accessories(self, brand: str) -> dict:
        """
        브랜드별 호환 액세서리 조회

        Args:
            brand: 브랜드명

        Returns:
            dict: {compatible_accessories, note}
        """
        brand_compatibility = self.rules.get("brand_compatibility", {})

        # 정확한 매칭
        if brand in brand_compatibility:
            return brand_compatibility[brand]

        # 부분 매칭
        brand_lower = brand.lower()
        for b, data in brand_compatibility.items():
            if b.lower() in brand_lower or brand_lower in b.lower():
                return data

        return {"compatible_accessories": [], "note": ""}

    def get_price_tier_info(self, tier: str = "mid_range") -> dict:
        """
        가격 티어 정보 조회

        Args:
            tier: budget, mid_range, premium, luxury

        Returns:
            dict: {label, multiplier, quality_note}
        """
        price_tiers = self.rules.get("price_tiers", {})
        return price_tiers.get(tier, {
            "label": "균형",
            "multiplier": 1.0,
            "quality_note": "성능과 가격의 균형"
        })

    def analyze_bundle_for_gift(
        self,
        items: List[str],
        occasion: Optional[str] = None,
        recipient: Optional[str] = None,
    ) -> dict:
        """
        선물용 번들 분석

        Args:
            items: 품목 리스트
            occasion: 행사
            recipient: 대상

        Returns:
            dict: {is_suitable, score, suggestions, missing_items}
        """
        # 기본 호환성 검사
        compatibility = self.check_compatibility(items)

        # 선물 추천 품목 가져오기
        recommended_gifts = self.get_gift_recommendations(
            occasion=occasion,
            recipient=recipient,
        )

        normalized_items = [self._normalize_item(item) for item in items]

        # 추천 품목 중 포함된 것 확인
        included = []
        missing = []
        for gift in recommended_gifts:
            gift_lower = gift.lower()
            if any(gift_lower in item or item in gift_lower for item in normalized_items):
                included.append(gift)
            else:
                missing.append(gift)

        # 점수 계산 (포함된 추천 품목 비율)
        score = len(included) / len(recommended_gifts) * 100 if recommended_gifts else 50

        # 적합성 판단
        is_suitable = score >= 30 or len(included) >= 1

        return {
            "is_suitable": is_suitable,
            "score": round(score, 1),
            "included_recommendations": included,
            "missing_recommendations": missing[:3],
            "compatibility": compatibility,
            "occasion": occasion,
            "recipient": recipient,
        }


# 싱글톤 인스턴스
_compatibility_checker: CompatibilityChecker | None = None


def get_compatibility_checker() -> CompatibilityChecker:
    """CompatibilityChecker 싱글톤 인스턴스 반환"""
    global _compatibility_checker
    if _compatibility_checker is None:
        _compatibility_checker = CompatibilityChecker()
    return _compatibility_checker
