# CartPilot Backend

LangGraph 기반 AI 쇼핑 어시스턴트 백엔드 서버

## 기술 스택

- **Framework**: FastAPI
- **AI/LLM**: LangGraph, LangChain, OpenAI/Gemini
- **Language**: Python 3.11+
- **Validation**: Pydantic v2

## 프로젝트 구조

```
Backend/
├── app/
│   ├── agents/           # LangGraph 에이전트
│   │   ├── analyzer.py       # 의도 분석 + 요구사항 추출
│   │   ├── gift_agent.py     # GIFT 모드 (선물 추천)
│   │   ├── value_agent.py    # VALUE 모드 (가성비 추천)
│   │   ├── bundle_agent.py   # BUNDLE 모드 (묶음 구매)
│   │   ├── review_agent.py   # REVIEW 모드 (리뷰 분석)
│   │   ├── trend_agent.py    # TREND 모드 (트렌드 추천)
│   │   ├── orchestrator.py   # 에이전트 오케스트레이션
│   │   └── state.py          # 에이전트 상태 정의
│   ├── api/              # API 엔드포인트
│   │   ├── chat.py           # /api/chat
│   │   ├── graph.py          # /api/graph (그래프 시각화)
│   │   └── health.py         # /health
│   ├── models/           # Pydantic 모델
│   │   ├── request.py        # 요청 모델
│   │   ├── response.py       # 응답 모델
│   │   ├── product.py        # 상품 모델
│   │   ├── recommendation.py # 추천 결과 모델
│   │   └── session.py        # 세션 모델
│   ├── services/         # 외부 서비스
│   │   ├── llm_provider.py   # LLM 제공자 (OpenAI/Gemini)
│   │   ├── naver_shopping.py # 네이버 쇼핑 API
│   │   ├── cache.py          # 캐시 서비스
│   │   └── session_store.py  # 세션 저장소
│   ├── utils/            # 유틸리티
│   │   ├── graph_visualizer.py # 그래프 시각화 유틸리티
│   │   └── text_parser.py      # 텍스트 파싱
│   ├── config.py         # 환경 설정
│   └── main.py           # FastAPI 앱 진입점
├── scripts/              # 스크립트
│   └── visualize_graph.py    # 그래프 시각화 CLI
├── docs/                 # 문서
│   ├── graph.md              # Mermaid 다이어그램
│   └── graph.png             # PNG 이미지
└── tests/                # 테스트
    ├── unit/
    └── integration/
```

## 5가지 추천 모드

| 모드 | 트리거 예시 | 설명 |
|------|-------------|------|
| **GIFT** | "30대 남자 동료 퇴사 선물 5만원" | 선물 추천 |
| **VALUE** | "가성비 무선 키보드 추천해줘" | 가격대별 가성비 추천 |
| **BUNDLE** | "노트북+마우스+키보드 100만원" | 묶음 구매 최적화 |
| **REVIEW** | "에어프라이어 사도 돼?" | 리뷰 기반 검증 |
| **TREND** | "요즘 뭐 사?" | 트렌드 상품 추천 |

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

# 서버 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker 실행

```bash
docker build -t cartpilot-backend .
docker run -p 8000:8000 --env-file .env cartpilot-backend
```

## API 엔드포인트

### POST /api/chat

채팅 메시지 처리 및 추천 생성

```json
{
  "message": "가성비 무선 키보드 추천해줘",
  "session_id": "optional-session-id"
}
```

### GET /health

서버 상태 확인

```json
{
  "status": "healthy",
  "llm_provider": "openai",
  "naver_api": "up",
  "active_sessions": 5
}
```

### GET /api/graph

LangGraph 시각화 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /api/graph` | 인터랙티브 HTML 뷰어 |
| `GET /api/graph/mermaid` | Mermaid 다이어그램 JSON |
| `GET /api/graph/ascii` | ASCII 다이어그램 |
| `GET /api/graph/png` | PNG 이미지 다운로드 |

## LangGraph 시각화

### 웹 브라우저에서 보기 (권장)

```bash
# 서버 실행 후
http://localhost:8000/api/graph
```

인터랙티브 Mermaid 다이어그램과 노드 설명을 볼 수 있습니다.

### CLI 스크립트

```bash
# 모든 형식으로 docs/에 저장
python scripts/visualize_graph.py

# ASCII만 콘솔에 출력
python scripts/visualize_graph.py -f ascii -p

# PNG만 저장
python scripts/visualize_graph.py -f png

# 특정 디렉토리에 저장
python scripts/visualize_graph.py -o ./output
```

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

## 아키텍처

```
사용자 요청
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
추천 결과 반환
```
