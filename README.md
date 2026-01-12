# CartPilot Backend

LangGraph 기반 AI 쇼핑 어시스턴트 백엔드 서버

## 서비스 소개

CartPilot은 AI 기반 스마트 쇼핑 어시스턴트입니다. 사용자의 자연어 요청을 분석하여 맞춤형 상품을 추천하고, 관심 상품의 가격을 모니터링하여 최적의 구매 시점을 알려드립니다.

### 주요 서비스 기능

- **AI 쇼핑 추천**: 5가지 모드(선물/가성비/묶음/리뷰/트렌드)로 맞춤형 상품 추천
- **상품 비교**: 2~4개 상품을 나란히 비교 (가격/평점/리뷰 수 테이블)
- **소셜 로그인**: 카카오, 네이버 OAuth 2.0 기반 간편 로그인
- **관심상품 관리**: 상품 저장, 목표가 설정, 메모 기능
- **가격 모니터링**: 자동 가격 추적 및 90일 최저가 분석
- **가격 예측**: Prophet 기반 시계열 분석으로 7일/30일 후 가격 예측
- **스마트 알림**: 목표가 도달, 최저가 갱신 시 이메일 알림
- **구매 기록**: 구매 이력 관리 및 분석
- **상품 평점**: 구매 상품 평가 및 리뷰 기능

## 기술 스택

| 분류 | 기술 |
|------|------|
| **Framework** | FastAPI 0.109+ |
| **AI/LLM** | LangGraph 1.0+, LangChain 1.2+, OpenAI (gpt-4o-mini) / Gemini |
| **Language** | Python 3.11+ |
| **Database** | PostgreSQL 16 + SQLAlchemy 2.0 (Async) |
| **Caching** | 인메모리 캐싱 (asyncio.Lock 기반) |
| **Session** | 인메모리 세션 스토어 |
| **Migration** | Alembic |
| **Auth** | JWT (Access/Refresh Token), OAuth 2.0 (카카오, 네이버) |
| **Scheduling** | APScheduler (가격 모니터링) |
| **Price Prediction** | Prophet (시계열 예측) |
| **Validation** | Pydantic v2 |

## 프로젝트 구조

```
Backend/
├── app/
│   ├── agents/              # LangGraph AI 에이전트
│   │   ├── analyzer.py          # 의도 분석 + 요구사항 추출 (단일 LLM 호출)
│   │   ├── gift_agent.py        # GIFT 모드 (선물 추천)
│   │   ├── value_agent.py       # VALUE 모드 (가성비 추천, 3티어)
│   │   ├── bundle_agent.py      # BUNDLE 모드 (묶음 구매 최적화)
│   │   ├── review_agent.py      # REVIEW 모드 (리뷰 분석 검증)
│   │   ├── trend_agent.py       # TREND 모드 (트렌드 추천)
│   │   ├── validation_agent.py  # 상품 적합성 검증
│   │   ├── orchestrator.py      # LangGraph 오케스트레이션
│   │   ├── state.py             # 에이전트 상태 정의
│   │   ├── intent_classifier.py # 의도 분류기
│   │   └── requirement_extractor.py # 요구사항 추출기
│   ├── api/                 # API 엔드포인트
│   │   ├── auth.py              # 인증 (소셜 로그인, JWT)
│   │   ├── chat.py              # AI 채팅 (메인 API)
│   │   ├── wishlist.py          # 관심상품 관리
│   │   ├── ratings.py           # 상품 평점
│   │   ├── combination_ratings.py # 묶음 상품 평점
│   │   ├── purchases.py         # 구매 기록
│   │   ├── preferences.py       # 사용자 선호도
│   │   ├── bundle.py            # 묶음 상품 관리
│   │   ├── admin.py             # 관리자 기능
│   │   ├── graph.py             # LangGraph 시각화 (Mermaid/ASCII)
│   │   └── health.py            # 헬스체크
│   ├── models/              # SQLAlchemy & Pydantic 모델
│   │   ├── user.py              # 사용자 모델
│   │   ├── wishlist.py          # 관심상품/가격이력 모델
│   │   ├── rating.py            # 평점 모델
│   │   ├── combination_rating.py # 묶음 평점 모델
│   │   ├── purchase.py          # 구매 기록 모델
│   │   ├── product.py           # 상품 모델
│   │   ├── review.py            # 리뷰 인사이트 모델
│   │   ├── session.py           # 세션 상태 모델
│   │   ├── request.py           # 요청 모델 (IntentType, Requirements)
│   │   ├── response.py          # 응답 모델 (ChatResponse)
│   │   ├── recommendation.py    # 추천 결과 모델
│   │   └── price_prediction.py  # 가격 예측 모델
│   ├── services/            # 비즈니스 로직 서비스
│   │   ├── oauth/               # OAuth 서비스
│   │   │   ├── base.py              # OAuth 기본 클래스
│   │   │   ├── kakao.py             # 카카오 OAuth
│   │   │   └── naver.py             # 네이버 OAuth
│   │   ├── notifications/       # 알림 서비스
│   │   │   ├── notification_manager.py  # 알림 관리자 (카카오톡 우선)
│   │   │   ├── kakao_message.py     # 카카오톡 "나에게 보내기"
│   │   │   └── email_service.py     # 이메일 발송
│   │   ├── llm_provider.py      # LLM 제공자 (OpenAI/Gemini)
│   │   ├── naver_shopping.py    # 네이버 쇼핑 API
│   │   ├── price_monitor.py     # 가격 모니터링
│   │   ├── price_predictor.py   # Prophet 기반 가격 예측
│   │   ├── preference_analyzer.py # 사용자 성향 분석
│   │   ├── sentiment_analyzer.py  # 리뷰 감정 분석
│   │   ├── review_crawler.py    # 리뷰 크롤링
│   │   ├── keyword_expander.py  # 검색 키워드 확장
│   │   ├── budget_optimizer.py  # 예산 최적화
│   │   ├── compatibility_checker.py # 제품 호환성 검사
│   │   ├── recommendation_reranker.py # 추천 재정렬
│   │   ├── jwt_service.py       # JWT 토큰 관리
│   │   ├── scheduler.py         # APScheduler (가격 모니터링)
│   │   ├── cache.py             # 인메모리 캐시 (Redis 비활성화)
│   │   └── session_store.py     # 인메모리 세션 저장소
│   ├── dependencies/        # FastAPI 의존성
│   │   └── auth.py              # 인증 의존성
│   ├── utils/               # 유틸리티
│   │   ├── graph_visualizer.py  # LangGraph 시각화
│   │   └── text_parser.py       # 텍스트 파싱
│   ├── config.py            # 환경 설정 (Pydantic Settings)
│   ├── database.py          # DB 연결 설정 (비동기)
│   └── main.py              # FastAPI 앱 진입점
├── alembic/                 # DB 마이그레이션
│   ├── versions/                # 마이그레이션 스크립트
│   └── env.py                   # Alembic 환경 설정
├── scripts/                 # 유틸리티 스크립트
├── tests/                   # 테스트
└── docker-compose.yml       # Docker 구성
```

## 5가지 AI 추천 모드

| 모드 | 트리거 예시 | 설명 |
|------|-------------|------|
| **GIFT** | "30대 남자 동료 퇴사 선물 5만원" | 수신자 분석 기반 선물 추천 |
| **VALUE** | "가성비 무선 키보드 추천해줘" | 저가/표준/프리미엄 3티어 추천 |
| **BUNDLE** | "노트북+마우스+키보드 100만원" | 예산 내 최적 조합 추천 |
| **REVIEW** | "에어프라이어 사도 돼?" | 리뷰 분석 기반 장단점 제공 |
| **TREND** | "요즘 뭐 사?" | 인기 트렌드 상품 추천 |

## 가격 모니터링 시스템

### 자동 가격 추적
- 스케줄러가 주기적으로 관심상품 가격 확인
- 가격 변동 시 자동으로 이력 기록
- 90일 최저가/최고가/평균가 자동 계산

### 알림 조건 (개별 설정 가능)
| 조건 | 설명 |
|------|------|
| **목표가 도달** | 설정한 목표 가격 이하로 하락 시 |
| **90일 최저가** | 90일 내 최저 가격 도달 시 |
| **N% 하락** | 이전 가격 대비 N% 이상 하락 시 |

### 알림 채널
1. **이메일** 

## 가격 예측 시스템 (Prophet 기반)

> 2025-01-06 추가

### 개요
Meta의 Prophet 시계열 예측 라이브러리를 활용하여 상품 가격을 예측합니다.

### 예측 방식
| 데이터 양 | 예측 방법 | 설명 |
|----------|----------|------|
| **14일 이상** | Prophet | 시계열 분석 기반 예측, 주간 패턴 감지 |
| **7~13일** | 단순 추세 외삽 | 선형 추세 기반 fallback |
| **7일 미만** | 예측 불가 | "데이터 수집 중" 안내 |

### Prophet 설정
```python
Prophet(
    yearly_seasonality=False,  # 90일 데이터로는 연간 패턴 불가
    weekly_seasonality=True,   # 주간 패턴 감지 (주말 가격 변동 등)
    daily_seasonality=False,   # 일간 패턴 불필요
    changepoint_prior_scale=0.05,  # 부드러운 추세 예측
)
```

### 신뢰도 계산
- 데이터 포인트 수 (14/30/60일) 기반
- Prophet 예측 불확실성 (yhat_upper - yhat_lower) 반영
- 0.2 ~ 0.9 범위로 제한

### 예상 세일 캘린더
- **음력 명절**: 설날/추석 정확한 양력 날짜 반영 (2024-2030)
- **고정 명절**: 블랙프라이데이, 크리스마스 등
- **주의**: 과거 패턴 기반 "예상" 일정이며, 실제 할인은 쇼핑몰에서 직접 확인 필요

### API 엔드포인트
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/wishlist/{id}/prediction` | 단일 상품 가격 예측 |
| GET | `/api/wishlist/predictions/summary` | 전체 상품 예측 요약 |

## 설치 및 실행

### 환경 변수 설정

`.env` 파일 생성:

```env
# LLM 설정
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
# GOOGLE_API_KEY=your_google_api_key  # Gemini 사용 시

# 네이버 쇼핑 API
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

# 카카오 OAuth
KAKAO_CLIENT_ID=your_kakao_client_id
KAKAO_CLIENT_SECRET=your_kakao_client_secret
KAKAO_REDIRECT_URI=http://localhost:8000/api/auth/kakao/callback

# 네이버 OAuth
NAVER_OAUTH_CLIENT_ID=your_naver_oauth_client_id
NAVER_OAUTH_CLIENT_SECRET=your_naver_oauth_client_secret
NAVER_REDIRECT_URI=http://localhost:8000/api/auth/naver/callback

# JWT 설정
JWT_SECRET_KEY=your_super_secret_jwt_key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30

# 데이터베이스
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=cartpilot
POSTGRES_PASSWORD=cartpilot123
POSTGRES_DB=cartpilot

# Redis (현재 비활성화 - 인메모리 캐시 사용 중)
# REDIS_HOST=localhost
# REDIS_PORT=6379

# 이메일 (선택)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# 서버 설정
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false

# CORS
CORS_ORIGINS=http://localhost:3000
```

### 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 데이터베이스 마이그레이션
alembic upgrade head

# 서버 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker 실행

```bash
# 전체 스택 실행 (Backend + PostgreSQL)
docker-compose up -d

# 백엔드만 빌드 및 실행
docker build -t cartpilot-backend .
docker run -p 8000:8000 --env-file .env cartpilot-backend
```

> **참고**: 현재 Redis는 비활성화되어 있으며 인메모리 캐싱을 사용합니다. 서버 재시작 시 캐시가 초기화됩니다.

## API 엔드포인트

### 인증 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/auth/kakao` | 카카오 로그인 시작 |
| GET | `/api/auth/kakao/callback` | 카카오 콜백 처리 |
| GET | `/api/auth/naver` | 네이버 로그인 시작 |
| GET | `/api/auth/naver/callback` | 네이버 콜백 처리 |
| POST | `/api/auth/refresh` | 토큰 갱신 |
| POST | `/api/auth/logout` | 로그아웃 |
| GET | `/api/auth/me` | 내 정보 조회 |

### 채팅 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/chat` | AI 채팅 (상품 추천) |

```json
{
  "message": "가성비 무선 키보드 추천해줘",
  "session_id": "optional-session-id"
}
```

### 관심상품 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/wishlist` | 내 관심상품 목록 |
| POST | `/api/wishlist` | 관심상품 등록 |
| PUT | `/api/wishlist/{id}` | 관심상품 수정 (목표가, 알림 설정) |
| DELETE | `/api/wishlist/{id}` | 관심상품 삭제 |
| GET | `/api/wishlist/{id}/price-history` | 가격 이력 조회 |
| GET | `/api/wishlist/{id}/price-analysis` | 가격 분석 (최저/최고/평균) |
| POST | `/api/wishlist/{id}/check-price` | 수동 가격 체크 |

### 평점/구매 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/ratings` | 내 평점 목록 |
| POST | `/api/ratings` | 평점 등록 |
| GET | `/api/purchases` | 구매 기록 목록 |
| POST | `/api/purchases` | 구매 기록 등록 |

### 묶음 상품 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/bundles` | 저장된 묶음 상품 목록 |
| POST | `/api/bundles` | 묶음 상품 저장 |
| GET | `/api/combination-ratings` | 묶음 평점 목록 |
| POST | `/api/combination-ratings` | 묶음 평점 등록 |

### 헬스체크

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/health` | 서버 상태 |
| GET | `/api/health` | 상세 헬스체크 |

## 데이터베이스 마이그레이션

```bash
# 최신 마이그레이션 적용
alembic upgrade head

# 마이그레이션 롤백
alembic downgrade -1

# 새 마이그레이션 생성 (모델 변경 자동 감지)
alembic revision --autogenerate -m "Add new table"

# 마이그레이션 히스토리 확인
alembic history
```

### 마이그레이션 히스토리
1. `001` - users 테이블 생성
2. `002` - wishlist, price_history 테이블 생성
3. `003` - purchase_records 테이블 생성
4. `004` - 카카오 토큰 필드 추가
5. `005` - 알림 조건 필드 추가

## 아키텍처

```
사용자 요청
    ↓
[FastAPI] 인증 미들웨어 (JWT)
    ↓
[Analyzer] 의도 분류 + 요구사항 추출
    ↓
[Orchestrator] 의도별 에이전트 라우팅
    ↓
┌─────────┬─────────┬─────────┬─────────┬─────────┐
│  GIFT   │  VALUE  │ BUNDLE  │ REVIEW  │  TREND  │
└─────────┴─────────┴─────────┴─────────┴─────────┘
    ↓
[네이버 쇼핑 API] 상품 검색
    ↓
[LLM] 추천 생성
    ↓
[Validation Agent] 상품 적합성 검증  ← NEW
    │
    ├─ 적합 상품 3개+ → 결과 반환
    └─ 적합 상품 0개 → 재검색 (1회)
    ↓
추천 결과 반환

[백그라운드]
Scheduler → Price Monitor → 가격 변동 감지 → Notification Manager → 카카오톡/이메일

[캐싱/세션]
인메모리 캐시 (asyncio.Lock) - 검색 결과, LLM 응답 캐싱
인메모리 세션 (asyncio.Lock) - 대화 세션 관리
```

> **참고**: 현재 Redis 없이 인메모리 캐싱을 사용합니다. 서버 재시작 시 캐시와 세션이 초기화됩니다.

## 검증 에이전트 (Validation Agent)

추천된 상품이 사용자 요청에 실제로 부합하는지 검증하는 에이전트입니다.

### 문제 해결
- "가벼운 식사 대용품" 요청 시 물리적으로 가벼운 "보관 케이스", "컵" 등이 추천되는 문제 해결
- 의미적 불일치 (예: "가벼운" = 칼로리/소화 vs 물리적 무게) 감지 및 필터링

### 검증 로직
1. **규칙 기반 필터 (1차)**: 카테고리/키워드로 명백한 부적합 상품 제거
   - 식품 요청 → 식품 카테고리만 허용
   - "케이스", "보관함", "용기" 등 부적합 키워드 필터링
2. **LLM 검증 (2차)**: 의미적 적합성 판단
   - 카테고리 적합성, 용도 적합성, 의미적 일치 여부 확인

### 처리 조건
| 조건 | 처리 |
|------|------|
| 적합 상품 3개+ 또는 50%+ | 검증 통과, 필터링된 결과 반환 |
| 적합 상품 1~2개 | 부분 통과, 피드백 메시지 포함 |
| 적합 상품 0개 | 재검색 (LLM 제안 키워드, 최대 1회) |

## 테스트

```bash
# 전체 테스트
pytest

# 커버리지 포함
pytest --cov=app

# 특정 테스트
pytest tests/unit/test_intent_classifier.py -v
```

## 코드 품질

```bash
# 린팅
ruff check .

# 포맷팅
black .

# 타입 체크
mypy app/
```
