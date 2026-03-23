from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ingredient import Ingredient
from app.schemas.ingredient import IngredientResponse

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("/", response_model=list[IngredientResponse])
def get_ingredients(
    category: Optional[str] = Query(default=None, description="카테고리 필터 (예: frequent)"),
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

    ingredients = session.exec(query).all()
    return ingredients
