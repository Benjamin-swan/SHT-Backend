from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api import ingredients, logs, recipes
from app.core.database import create_db_and_tables, engine
from app.models import llm_cache  # noqa: F401 — LLM_CACHE 테이블 생성 등록용


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 시작/종료 시 실행되는 lifespan 핸들러.
    - 시작: DB 테이블 생성 + 빈출 식재료 초기 데이터 시딩
    - 종료: (필요 시 정리 로직 추가)
    """
    # 앱 시작 시
    create_db_and_tables()
    _seed_on_startup()
    yield
    # 앱 종료 시 (현재는 별도 정리 없음)


def _seed_on_startup() -> None:
    """앱 최초 실행 시 빈출 식재료 데이터가 없으면 자동으로 시딩합니다."""
    from app.services.seed import seed_frequent_ingredients

    with Session(engine) as session:
        seed_frequent_ingredients(session)


app = FastAPI(
    title="요리조리 API",
    description="식재료 기반 레시피 추천 서비스 백엔드",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 설정 (프론트엔드 개발 서버 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(ingredients.router)
app.include_router(logs.router)
app.include_router(recipes.router)


@app.get("/health")
def health_check():
    """서버 상태 확인용 헬스체크 엔드포인트"""
    return {"status": "ok"}
