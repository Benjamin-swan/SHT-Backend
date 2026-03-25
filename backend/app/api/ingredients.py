from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ingredient import Ingredient
from app.schemas.ingredient import (
    IngredientCreateRequest,
    IngredientCreateResponse,
    IngredientResponse,
)
from app.services.llm import classify_ingredient

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("/", response_model=list[IngredientResponse])
def get_ingredients(
    category: str | None = Query(default=None, description="카테고리 필터 (예: frequent)"),
    session: Session = Depends(get_session),
) -> list[Ingredient]:
    """
    식재료 목록 조회 API.

    - category 파라미터 없음 → 전체 식재료 반환
    - category=frequent → 한국인 빈출 식재료 10개만 반환

    사용 예시:
        GET /ingredients              # 전체 목록
        GET /ingredients?category=frequent  # 빈출 식재료만
    """
    query = select(Ingredient)

    if category:
        query = query.where(Ingredient.category == category)

    ingredients = list(session.exec(query).all())
    return ingredients


@router.post(
    "/",
    response_model=IngredientCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="신규 식재료 LLM 자동 분류 등록 (SHT-BE-1)",
)
async def create_ingredient(
    body: IngredientCreateRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> IngredientCreateResponse:
    """
    사용자가 입력한 식재료명을 DB에 등록합니다.

    처리 흐름:
        1. DB에 이미 존재하면 LLM 호출 없이 기존 데이터 반환 (200, is_new=False)
        2. DB에 없으면 LLM으로 식용 가능 여부 + 카테고리 판단
        3. 식용 불가 → 422 에러
        4. 식용 가능 → DB INSERT 후 반환 (201, is_new=True)
    """
    name = body.name.strip()
    category_from_user = body.category

    # 1. 중복 확인 — LLM 호출 없이 즉시 반환 (200)
    existing = session.exec(
        select(Ingredient).where(Ingredient.name == name)
    ).first()
    if existing:
        # 라우터 기본값(201)을 200으로 덮어씁니다.
        response.status_code = status.HTTP_200_OK
        return IngredientCreateResponse(
            id=existing.id,
            name=existing.name,
            category=existing.category,
            created_at=existing.created_at,
            is_new=False,
        )

    # 2. LLM으로 식용 여부 + 카테고리 분류
    result = await classify_ingredient(name)

    # 3. 식용 불가 → 422
    if not result.get("is_food"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{name}'은(는) 식재료로 인식되지 않습니다.",
        )

    # 4. DB에 저장 (201)
    final_category: str = category_from_user or result.get("category") or "기타"
    ingredient = Ingredient(name=name, category=final_category)
    session.add(ingredient)
    session.commit()
    session.refresh(ingredient)

    return IngredientCreateResponse(
        id=ingredient.id,
        name=ingredient.name,
        category=ingredient.category,
        created_at=ingredient.created_at,
        is_new=True,
    )
