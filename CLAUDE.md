# CLAUDE.md — 요리조리 Backend

## 프로젝트 개요

**서비스명**: 요리조리
**한 줄 설명**: 사용자가 보유한 식재료를 입력하면, DB 매칭 + Gemini AI를 통해 맞춤 레시피를 추천해주는 MVP 웹앱 서비스
**레포 경로**: `SHT-Backend/`

---

## AI 페르소나 및 응답 원칙

당신은 시니어 풀스택 개발자입니다. 신중하고 자세한 답변을 제공하며 뛰어난 사고력을 가지고 있습니다.

- 사용자가 질문하면 먼저 **단계별로 생각하며 계획을 세우고** 답변하세요.
- 항상 **올바르고, 모범적인, DRY 원칙**(중복을 피하는 코드), 버그 없는 코드를 작성하세요.
- **가독성을 우선**하되, 성능도 고려한 코드를 작성하세요.
- 요청된 모든 기능을 **완전히 구현**하세요. 중간에 생략하지 마세요.
- 코드는 간결하고 불필요한 설명은 최소화하세요.
- 모르는 경우는 모른다고 답하고, 추가 조사가 필요하면 이를 언급하세요.
- 별도의 요청이 없으면 **모든 응답은 한국어**로 답하세요.
- 사용자가 **주니어 개발자**라고 가정하고, 코드에 대한 자세한 설명을 모든 답변에 포함하세요.

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| 웹 프레임워크 | FastAPI |
| ASGI 서버 | Uvicorn |
| DB | PostgreSQL |
| ORM | SQLModel (SQLAlchemy + Pydantic 통합) |
| 데이터 수집 | pandas, openpyxl (엑셀 → DB 임포트) |
| AI 추천 | httpx + Gemini Flash API (비동기 호출) |
| 환경 관리 | python-dotenv |

---

## 프로젝트 폴더 구조

```
backend/
├── app/
│   ├── main.py              # FastAPI 앱 진입점, CORS 설정
│   ├── core/
│   │   ├── config.py        # 환경변수 (DB URL, API 키)
│   │   └── database.py      # SQLModel 세션 관리
│   ├── models/
│   │   ├── ingredient.py    # 식재료 테이블 (SQLModel)
│   │   ├── recipe.py        # 레시피 테이블 (SQLModel)
│   │   └── user.py          # 익명 유저, 세션 테이블 (SQLModel)
│   ├── api/
│   │   ├── ingredients.py   # GET /ingredients
│   │   ├── recipes.py       # POST /recipes/recommend
│   │   └── logs.py          # POST /logs/event
│   ├── services/
│   │   ├── matcher.py       # DB 기반 재료 매칭 로직
│   │   ├── llm.py           # Gemini API 비동기 호출
│   │   └── freshness.py     # +48h / +24h 유효시간 계산
│   └── schemas/
│       └── recipe.py        # Request / Response Pydantic 모델
├── scripts/
│   └── import_recipes.py    # 엑셀 → PostgreSQL (최초 1회)
├── .env                     # 환경변수 (git 제외)
└── requirements.txt         # 패키지 목록
```

### 레이어 역할 요약

- **api/** — HTTP 요청/응답 처리, 라우터 등록. 비즈니스 로직 포함 금지.
- **services/** — 핵심 비즈니스 로직. DB 쿼리 + AI 호출 + 계산 담당.
- **models/** — DB 테이블 정의 (SQLModel). 마이그레이션 기준.
- **schemas/** — API 입출력 전용 Pydantic 모델. DB 모델과 분리.
- **core/** — 설정, DB 연결 등 인프라 레벨 코드.

---

## ERD (데이터베이스 구조)

### 테이블 목록

#### `ANONYMOUS_USERS` — 익명 사용자
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| browser_uuid | string | 브라우저 고유 식별자 |
| ip_address | string | 접속 IP |
| user_agent | string | 브라우저 정보 |
| created_at | timestamp | 생성일시 |
| last_seen_at | timestamp | 마지막 접속일시 |

#### `USER_SESSIONS` — 세션
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| anonymous_user_id | uuid | FK → ANONYMOUS_USERS |
| created_at | timestamp | 세션 생성일시 |
| expires_at | timestamp | 세션 만료일시 |

#### `USER_INGREDIENT_INPUTS` — 사용자가 입력한 식재료
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| session_id | uuid | FK → USER_SESSIONS |
| ingredient_id | uuid | FK → INGREDIENTS |
| input_method | string | 입력 방식 (직접입력 / 냉장고) |
| freshness_status | string | 신선도 상태 |
| expires_at | timestamp | 유효기간 만료일시 |
| created_at | timestamp | 생성일시 |

#### `INGREDIENTS` — 식재료 마스터
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| name | string | 식재료명 |
| category | string | 카테고리 (채소, 단백질, frequent 등) |
| created_at | timestamp | 생성일시 |

> **변경사항**: MVP UX 개선을 위해 `unit` 컬럼 제외. 빈출 식재료 구분은 `category = "frequent"` 로 필터링.

#### `RECIPES` — 레시피 마스터
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| title | string | 레시피명 |
| source | string | 출처 |
| source_url | string | 원문 URL |
| instructions | text | 조리 방법 |
| cooking_time_min | int | 조리 시간 (분) |
| is_llm_generated | bool | LLM 생성 여부 |
| created_at | timestamp | 생성일시 |

#### `RECIPE_INGREDIENTS` — 레시피-식재료 관계 (N:M)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| recipe_id | uuid | FK → RECIPES |
| ingredient_id | uuid | FK → INGREDIENTS |
| quantity | string | 필요 수량 |
| is_optional | bool | 선택 재료 여부 |

#### `INTERACTION_LOGS` — 사용자 행동 로그
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| session_id | uuid | FK → USER_SESSIONS |
| recipe_id | uuid | FK → RECIPES |
| event_type | string | 이벤트 유형 (click, view 등) |
| metadata | jsonb | 추가 메타데이터 |
| created_at | timestamp | 발생일시 |

#### `LLM_CACHE` — LLM 응답 캐시
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| ingredients_hash | string | 입력 재료 해시값 (캐시 키) |
| response_text | text | LLM 원본 응답 |
| parsed_recipes | jsonb | 파싱된 레시피 목록 |
| hit_count | int | 캐시 히트 횟수 |
| created_at | timestamp | 생성일시 |

### 테이블 관계 요약

```
ANONYMOUS_USERS (1) ──── (N) USER_SESSIONS
USER_SESSIONS (1) ──── (N) USER_INGREDIENT_INPUTS
USER_SESSIONS (1) ──── (N) INTERACTION_LOGS
RECIPES (1) ──── (N) RECIPE_INGREDIENTS
INGREDIENTS (1) ──── (N) RECIPE_INGREDIENTS
RECIPES (1) ──── (N) INTERACTION_LOGS
```

---

## 핵심 API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/ingredients` | 식재료 전체 목록 조회 |
| POST | `/recipes/recommend` | 보유 식재료 기반 레시피 추천 |
| POST | `/logs/event` | 사용자 행동 이벤트 로그 저장 |

---

## 코딩 컨벤션

- **Python 스타일**: PEP 8 준수, 타입 힌트 필수
- **비동기**: I/O 작업(DB, HTTP)은 `async/await` 사용
- **모델 분리**: SQLModel DB 모델과 Pydantic 스키마를 명확히 분리
- **환경변수**: 하드코딩 금지, 반드시 `.env` + `config.py` 통해 주입
- **에러 처리**: FastAPI `HTTPException` 사용, 적절한 HTTP 상태코드 반환
- **DRY**: 반복 로직은 `services/`로 추출

---

## 개발 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에서 DB URL, Gemini API Key 설정

# 서버 실행
uvicorn app.main:app --reload
```

---

## 주요 참고사항

- MVP 단계이므로 **회원가입/로그인 없이 익명 사용자** 기반으로 동작
- LLM 비용 절감을 위해 **LLM_CACHE** 테이블로 동일 재료 조합 캐싱
- 식재료 데이터는 **엑셀 → `scripts/import_recipes.py`** 로 최초 1회 임포트
- 신선도 유효기간: 냉장고 등록 재료 기준 **+48h**, 직접 입력 기준 **+24h**

---

## 백엔드 백로그

### SHT-BE-7 — LLM 기반 신규 식재료 자동 등록 (POST /ingredients)
- 사용자가 DB에 없는 식재료명을 입력하면 LLM이 식용 가능 여부와 카테고리를 판단하여 자동으로 DB에 등록합니다.
- 이미 존재하는 식재료는 LLM 호출 없이 기존 데이터를 반환합니다 (중복 방지).
- 식용 불가 입력(예: "나무", "돌") 시 422 에러를 반환합니다.

**Success Criteria**
- [ ] `POST /ingredients` 요청 시 DB에 이미 있으면 LLM 호출 없이 기존 데이터 반환 (200)
- [ ] DB에 없는 식재료명 입력 시 LLM이 식용 여부 + 카테고리를 JSON으로 응답
- [ ] LLM이 식용 가능으로 판단하면 `ingredients` 테이블에 자동 INSERT 후 201 반환
- [ ] LLM이 식용 불가로 판단하면 422 Unprocessable Entity 반환
- [ ] 응답에 `is_new` 필드로 신규 등록 여부를 표시
- [ ] LLM 호출은 레시피 추천(`POST /recipes/recommend`)과 독립적으로 동작 (추가 호출 없음)

**TODO**
- [ ] `app/schemas/ingredient.py`에 `IngredientCreateRequest`, `IngredientCreateResponse` 추가
- [ ] `app/services/llm.py`에 `classify_ingredient(name)` 함수 추가 (식용 여부 + 카테고리 반환)
- [ ] `app/api/ingredients.py`에 `POST /ingredients` 엔드포인트 추가
- [ ] 프론트엔드 `client.js`에 `createIngredient(name)` 함수 추가
- [ ] `IngredientSearchInput.jsx`에 검색 결과 없을 때 "추가하기" 버튼 표시
