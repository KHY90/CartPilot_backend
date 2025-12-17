"""
상품 모델 정의
네이버 쇼핑 API 응답 및 상품 후보 관련 모델
"""
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class ProductCandidate(BaseModel):
    """상품 후보 모델"""

    product_id: str = Field(..., description="상품 고유 ID")
    title: str = Field(..., description="상품명 (HTML 태그 제거됨)")
    link: HttpUrl = Field(..., description="상품 상세 URL")
    image: Optional[HttpUrl] = Field(None, description="썸네일 이미지 URL")
    price: int = Field(..., ge=0, description="최저가 (원)")
    high_price: Optional[int] = Field(None, ge=0, description="최고가 (원)")
    mall_name: str = Field(..., description="쇼핑몰 이름")
    brand: Optional[str] = Field(None, description="브랜드명")
    maker: Optional[str] = Field(None, description="제조사")
    category1: Optional[str] = Field(None, description="카테고리 1depth")
    category2: Optional[str] = Field(None, description="카테고리 2depth")
    category3: Optional[str] = Field(None, description="카테고리 3depth")
    category4: Optional[str] = Field(None, description="카테고리 4depth")

    # 메타 정보
    source: str = Field(default="naver", description="데이터 소스")
    fetched_at: str = Field(..., description="조회 시점 (ISO 8601)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_id": "12345678",
                "title": "로지텍 무선 키보드 K380",
                "link": "https://shopping.naver.com/...",
                "image": "https://shopping-phinf.pstatic.net/...",
                "price": 45000,
                "mall_name": "네이버",
                "brand": "로지텍",
                "category1": "디지털/가전",
                "category2": "PC주변기기",
                "category3": "키보드",
                "source": "naver",
                "fetched_at": "2025-12-17T10:00:00Z",
            }
        }
    }


class ProductSearchResult(BaseModel):
    """상품 검색 결과"""

    total: int = Field(..., description="총 검색 결과 수")
    items: List[ProductCandidate] = Field(default_factory=list)
    query: str = Field(..., description="검색어")
    sort: str = Field(default="sim", description="정렬 방식")
    cached: bool = Field(default=False, description="캐시 히트 여부")
