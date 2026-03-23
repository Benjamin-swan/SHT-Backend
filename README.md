# 요리조리 — 식재료 기반 레시피 추천 서비스 (Backend)

사용자가 보유한 식재료를 입력하면, DB 매칭과 Gemini AI를 통해 맞춤 레시피를 추천해주는 MVP 웹앱 서비스의 백엔드 레포지토리입니다.

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| 웹 프레임워크 | FastAPI |
| ASGI 서버 | Uvicorn |
| 데이터베이스 | PostgreSQL |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| AI 추천 | Gemini Flash API (httpx 비동기 호출) |
| 환경 관리 | pydantic-settings + python-dotenv |

---

## 프로젝트 구조

```
SHT-Backend/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI 앱 진입점, CORS 설정
│       ├── core/
│       │   ├── config.py        # 환경변수 (DB URL, API 키)
│       │   └── database.py      # SQLModel 세션 관리
│       ├── models/              # SQLModel DB 모델
│       │   ├── ingredient.py
│       │   ├── recipe.py
│       │   ├── user.py
│       │   ├── interaction.py
│       │   └── llm_cache.py
│       ├── api/                 # FastAPI 라우터
│       │   ├── ingredients.py   # GET /ingredients
│       │   ├── recipes.py       # POST /recipes/recommend
│       │   └── logs.py          # POST /logs/event
│       ├── services/            # 비즈니스 로직
│       │   ├── matcher.py       # DB 기반 재료 매칭
│       │   ├── llm.py           # Gemini API 비동기 호출 + 캐싱
│       │   ├── freshness.py     # 신선도 유효시간 계산
│       │   └── seed.py          # 빈출 식재료 초기 데이터
│       └── schemas/
│           ├── recipe.py        # 레시피 Request/Response 스키마
│           └── log.py           # 로그 Request/Response 스키마
├── scripts/
│   └── seed_ingredients.py      # 독립 실행용 시딩 스크립트
├── .env.example                 # 환경변수 템플릿 (실제 값 제외)
├── requirements.txt
└── README.md
```

---

## 시작하기

### 1. 사전 요구사항

- Python 3.11+
- PostgreSQL 실행 중

### 2. 설치

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
# .env.example을 복사해서 .env 파일 생성
cp .env.example .env
```

`.env` 파일을 열어 실제 값으로 수정합니다:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/yorijori
GEMINI_API_KEY=your_gemini_api_key_here
```

> Gemini API 키는 [Google AI Studio](https://aistudio.google.com/)에서 발급받을 수 있습니다.

### 4. 서버 실행

```bash
cd backend
uvicorn app.main:app --reload
```

서버가 시작되면 자동으로:
- DB 테이블이 생성됩니다
- 빈출 식재료 10종 (마늘, 대파, 양파 등)이 시딩됩니다

---

## API 문서

서버 실행 후 아래 주소에서 Swagger UI를 통해 API를 테스트할 수 있습니다:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 주요 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/ingredients` | 식재료 전체 목록 조회 |
| GET | `/ingredients?category=frequent` | 빈출 식재료만 조회 |
| POST | `/recipes/recommend` | 보유 식재료 기반 레시피 추천 |
| POST | `/logs/event` | 재료 입력 이벤트 로그 저장 |
| GET | `/health` | 서버 상태 확인 |

### 레시피 추천 흐름

```
사용자 재료 입력
    ↓
DB 매칭 (RECIPES 테이블, 필수 재료 50% 이상 보유 시)
    ↓ (DB 결과 없을 때)
LLM 캐시 조회 (동일 재료 조합 이전 요청 여부)
    ↓ (캐시 미스 시)
Gemini API 호출 (gemini-2.5-flash → gemma-3-27b-it 폴백)
    ↓
레시피 파싱 → DB 저장 → 캐시 저장 → 응답
```

---

## 주요 설계 결정

- **익명 사용자**: 회원가입 없이 `browser_uuid` 기반 세션으로 동작
- **LLM 캐싱**: 동일한 재료 조합은 SHA-256 해시로 캐싱하여 Gemini API 비용 절감
- **모델 폴백**: `gemini-2.5-flash` 할당량 초과(429) 시 `gemma-3-27b-it`으로 자동 전환
- **신선도 TTL**: 싱싱 +48시간, 임박 +24시간 유효기간 자동 계산
