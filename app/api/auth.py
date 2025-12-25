"""
인증 API 엔드포인트
소셜 로그인 (카카오, 네이버) 및 JWT 토큰 관리
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.services.oauth.kakao import kakao_oauth_service
from app.services.oauth.naver import naver_oauth_service
from app.services.jwt_service import jwt_service
from app.dependencies.auth import get_current_user
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["인증"])

# 임시 state 저장소 (프로덕션에서는 Redis 사용)
oauth_states: dict[str, str] = {}


# ==================== Response Models ====================
class TokenResponse(BaseModel):
    """토큰 응답"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """사용자 정보 응답"""

    id: str
    email: Optional[str]
    name: Optional[str]
    profile_image: Optional[str]
    provider: str
    kakao_notification_enabled: bool
    email_notification_enabled: bool
    created_at: Optional[str]


class RefreshTokenRequest(BaseModel):
    """토큰 갱신 요청"""

    refresh_token: str


# ==================== 카카오 로그인 ====================
@router.get("/kakao")
async def kakao_login():
    """카카오 로그인 시작 - 카카오 인증 페이지로 리다이렉트"""
    state = secrets.token_urlsafe(32)
    oauth_states[state] = "kakao"
    auth_url = kakao_oauth_service.get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/kakao/callback")
async def kakao_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """카카오 로그인 콜백 처리"""
    # state 검증
    if state not in oauth_states or oauth_states[state] != "kakao":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 state입니다",
        )
    del oauth_states[state]

    try:
        # 액세스 토큰 교환 (토큰 정보 전체 반환)
        token_data = await kakao_oauth_service.get_access_token(code)

        # 사용자 정보 조회
        user_info = await kakao_oauth_service.get_user_info(token_data["access_token"])

        # 사용자 조회 또는 생성
        user = await get_or_create_user(db, user_info)

        # 카카오 토큰 저장 (나에게 보내기 기능용)
        user.kakao_access_token = token_data["access_token"]
        user.kakao_refresh_token = token_data.get("refresh_token")
        user.kakao_token_expires_at = datetime.utcnow() + timedelta(
            seconds=token_data.get("expires_in", 21599)
        )
        await db.commit()

        # JWT 토큰 발급
        tokens = create_tokens(str(user.id), user.provider)

        # 프론트엔드로 리다이렉트 (토큰을 URL 파라미터로 전달)
        frontend_url = settings.cors_origins_list[0]
        redirect_url = (
            f"{frontend_url}/auth/callback"
            f"?access_token={tokens['access_token']}"
            f"&refresh_token={tokens['refresh_token']}"
        )
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"카카오 로그인 실패: {str(e)}",
        )


# ==================== 네이버 로그인 ====================
@router.get("/naver")
async def naver_login():
    """네이버 로그인 시작 - 네이버 인증 페이지로 리다이렉트"""
    state = secrets.token_urlsafe(32)
    oauth_states[state] = "naver"
    auth_url = naver_oauth_service.get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/naver/callback")
async def naver_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """네이버 로그인 콜백 처리"""
    # state 검증
    if state not in oauth_states or oauth_states[state] != "naver":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 state입니다",
        )
    del oauth_states[state]

    try:
        # 액세스 토큰 교환
        access_token = await naver_oauth_service.get_access_token(code)

        # 사용자 정보 조회
        user_info = await naver_oauth_service.get_user_info(access_token)

        # 사용자 조회 또는 생성
        user = await get_or_create_user(db, user_info)

        # JWT 토큰 발급
        tokens = create_tokens(str(user.id), user.provider)

        # 프론트엔드로 리다이렉트
        frontend_url = settings.cors_origins_list[0]
        redirect_url = (
            f"{frontend_url}/auth/callback"
            f"?access_token={tokens['access_token']}"
            f"&refresh_token={tokens['refresh_token']}"
        )
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"네이버 로그인 실패: {str(e)}",
        )


# ==================== 토큰 관리 ====================
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """토큰 갱신"""
    token_data = jwt_service.verify_token(request.refresh_token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 리프레시 토큰입니다",
        )

    # 사용자 존재 확인
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다",
        )

    # 새 토큰 발급
    tokens = create_tokens(str(user.id), user.provider)
    return TokenResponse(**tokens)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """로그아웃 (클라이언트에서 토큰 삭제)"""
    # JWT는 stateless이므로 서버에서 무효화할 수 없음
    # 클라이언트에서 토큰을 삭제해야 함
    # 추후 Redis에 블랙리스트 구현 가능
    return {"message": "로그아웃 되었습니다"}


# ==================== 사용자 정보 ====================
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """현재 로그인된 사용자 정보 조회"""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        profile_image=current_user.profile_image,
        provider=current_user.provider,
        kakao_notification_enabled=current_user.kakao_notification_enabled,
        email_notification_enabled=current_user.email_notification_enabled,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


# ==================== Helper Functions ====================
async def get_or_create_user(db: AsyncSession, user_info) -> User:
    """사용자 조회 또는 생성"""
    # 기존 사용자 조회
    result = await db.execute(
        select(User).where(
            User.provider == user_info.provider,
            User.provider_id == user_info.provider_id,
        )
    )
    user = result.scalar_one_or_none()

    if user:
        # 마지막 로그인 시간 업데이트
        user.last_login_at = datetime.utcnow()
        # 프로필 정보 업데이트
        if user_info.name:
            user.name = user_info.name
        if user_info.profile_image:
            user.profile_image = user_info.profile_image
        if user_info.email:
            user.email = user_info.email
        await db.commit()
        return user

    # 신규 사용자 생성
    new_user = User(
        email=user_info.email,
        name=user_info.name,
        profile_image=user_info.profile_image,
        provider=user_info.provider,
        provider_id=user_info.provider_id,
        kakao_id=user_info.kakao_id,
        notification_email=user_info.email,
        last_login_at=datetime.utcnow(),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


def create_tokens(user_id: str, provider: str) -> dict:
    """JWT 토큰 쌍 생성"""
    access_token = jwt_service.create_access_token(user_id, provider)
    refresh_token = jwt_service.create_refresh_token(user_id, provider)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_minutes * 60,
    }
