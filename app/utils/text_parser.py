"""
텍스트 파싱 유틸리티
한국어 입력에서 예산, 품목 등을 추출
"""
import re
from typing import List, Optional, Tuple

from app.models.request import BudgetRange, RecipientInfo


def extract_budget(text: str) -> Optional[BudgetRange]:
    """
    텍스트에서 예산 정보 추출

    지원 패턴:
    - "5만원", "50000원", "5만"
    - "3~5만원", "30000~50000원"
    - "100만원", "1000000원"
    - "약 5만원", "대략 5만원"

    Args:
        text: 원문 텍스트

    Returns:
        BudgetRange 또는 None
    """
    # 숫자 + 만/천 + 원 패턴
    korean_number_pattern = r"(\d+(?:\.\d+)?)\s*(천|만|백만|억)?\s*원?"

    # 범위 패턴 (예: 3~5만원, 30000~50000원)
    range_pattern = r"(\d+(?:\.\d+)?)\s*(천|만|백만)?\s*[~\-에서부터]\s*(\d+(?:\.\d+)?)\s*(천|만|백만)?\s*원?"

    # "약", "대략" 등 유연성 표시
    is_flexible = bool(re.search(r"(약|대략|정도|쯤|내외|전후)", text))

    # 범위 패턴 먼저 체크
    range_match = re.search(range_pattern, text)
    if range_match:
        min_val = _parse_korean_number(range_match.group(1), range_match.group(2))
        max_val = _parse_korean_number(range_match.group(3), range_match.group(4))

        if min_val and max_val:
            return BudgetRange(
                min_price=int(min_val),
                max_price=int(max_val),
                is_flexible=is_flexible,
            )

    # 단일 금액 패턴
    single_matches = re.findall(korean_number_pattern, text)
    if single_matches:
        # 가장 큰 금액을 기준으로 범위 설정
        amounts = []
        for num_str, unit in single_matches:
            amount = _parse_korean_number(num_str, unit)
            if amount:
                amounts.append(amount)

        if amounts:
            base_amount = max(amounts)
            # 기본적으로 ±20% 범위 설정
            return BudgetRange(
                min_price=int(base_amount * 0.8),
                max_price=int(base_amount * 1.2),
                total_budget=int(base_amount),
                is_flexible=is_flexible,
            )

    return None


def _parse_korean_number(num_str: str, unit: Optional[str]) -> Optional[float]:
    """한국어 숫자 단위를 실제 숫자로 변환"""
    try:
        base = float(num_str)
    except ValueError:
        return None

    multipliers = {
        "천": 1000,
        "만": 10000,
        "백만": 1000000,
        "억": 100000000,
    }

    if unit and unit in multipliers:
        return base * multipliers[unit]
    elif base > 10000:
        # 이미 원 단위로 보이면 그대로 반환
        return base
    elif base > 0 and base <= 1000:
        # 만원 단위로 추정
        return base * 10000

    return base


def extract_items(text: str) -> List[str]:
    """
    텍스트에서 품목/카테고리 추출

    Args:
        text: 원문 텍스트

    Returns:
        품목 리스트
    """
    # 일반적인 품목 키워드
    common_items = [
        "노트북",
        "키보드",
        "마우스",
        "모니터",
        "이어폰",
        "헤드폰",
        "스피커",
        "카메라",
        "시계",
        "가방",
        "지갑",
        "신발",
        "옷",
        "화장품",
        "향수",
        "액세서리",
        "에어프라이어",
        "청소기",
        "가습기",
        "공기청정기",
        "전자레인지",
        "커피머신",
        "믹서기",
        "선풍기",
        "히터",
    ]

    found_items = []

    # 알려진 품목 찾기
    for item in common_items:
        if item in text:
            found_items.append(item)

    # + 또는 , 로 구분된 품목 파싱
    if "+" in text or "," in text:
        parts = re.split(r"[+,]", text)
        for part in parts:
            part = part.strip()
            # 숫자나 금액이 아닌 경우만 추가
            if part and not re.match(r"^\d+", part) and part not in found_items:
                # 금액 관련 단어 제외
                if not any(kw in part for kw in ["원", "만원", "천원", "예산"]):
                    found_items.append(part)

    return found_items


def extract_recipient_info(text: str) -> Optional[RecipientInfo]:
    """
    텍스트에서 선물 대상 정보 추출

    Args:
        text: 원문 텍스트

    Returns:
        RecipientInfo 또는 None
    """
    relation = None
    gender = None
    age_group = None
    occasion = None

    # 관계 추출
    relation_patterns = {
        "친구": "friend",
        "동료": "colleague",
        "상사": "boss",
        "부모님": "parent",
        "엄마": "mother",
        "아빠": "father",
        "여자친구": "girlfriend",
        "남자친구": "boyfriend",
        "아내": "wife",
        "남편": "husband",
        "자녀": "child",
        "아들": "son",
        "딸": "daughter",
        "선생님": "teacher",
        "교수님": "professor",
    }

    for korean, english in relation_patterns.items():
        if korean in text:
            relation = english
            break

    # 성별 추출
    if any(kw in text for kw in ["남자", "남성", "아빠", "아들", "남편", "남자친구"]):
        gender = "male"
    elif any(kw in text for kw in ["여자", "여성", "엄마", "딸", "아내", "여자친구"]):
        gender = "female"

    # 연령대 추출
    age_match = re.search(r"(\d{1,2})\s*대", text)
    if age_match:
        age_group = f"{age_match.group(1)}대"

    # 상황/이벤트 추출
    occasion_patterns = {
        "생일": "birthday",
        "퇴사": "farewell",
        "입사": "welcome",
        "승진": "promotion",
        "결혼": "wedding",
        "기념일": "anniversary",
        "크리스마스": "christmas",
        "발렌타인": "valentine",
        "화이트데이": "whiteday",
        "어버이날": "parents_day",
        "스승의날": "teachers_day",
        "졸업": "graduation",
        "입학": "enrollment",
    }

    for korean, english in occasion_patterns.items():
        if korean in text:
            occasion = english
            break

    # 하나라도 추출되면 RecipientInfo 반환
    if any([relation, gender, age_group, occasion]):
        return RecipientInfo(
            relation=relation,
            gender=gender,
            age_group=age_group,
            occasion=occasion,
        )

    return None


def parse_user_input(text: str) -> Tuple[Optional[BudgetRange], List[str], Optional[RecipientInfo]]:
    """
    사용자 입력 통합 파싱

    Args:
        text: 원문 텍스트

    Returns:
        (BudgetRange, 품목 리스트, RecipientInfo) 튜플
    """
    budget = extract_budget(text)
    items = extract_items(text)
    recipient = extract_recipient_info(text)

    return budget, items, recipient
