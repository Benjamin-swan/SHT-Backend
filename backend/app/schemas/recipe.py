from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── POST /recipes/recommend ───────────────────────────────────────────────────

class RecipeRecommendRequest(BaseModel):
    """
    레시피 추천 요청 스키마.

    세 가지 방식 중 하나를 사용합니다:
        - ingredient_names: 재료명 목록 직접 전달 (프론트엔드 기본 방식)
        - session_id:       세션 ID → 해당 세션의 입력 재료를 자동으로 조회
        - ingredient_ids:   재료 UUID 직접 전달 (내부 테스트용)

    limit: 반환할 최대 레시피 수 (기본 10, 최대 20)
    """

    ingredient_names: Optional[list[str]] = Field(
        default=None, description="재료명 목록 (예: ['계란', '김치'])"
    )
    session_id: Optional[UUID] = Field(default=None, description="사용자 세션 ID")
    ingredient_ids: Optional[list[UUID]] = Field(
        default=None, description="재료 UUID 목록 (session_id 없을 때 직접 전달)"
    )
    limit: int = Field(default=10, ge=1, le=20, description="반환할 최대 레시피 수")


class RecipeMatchItem(BaseModel):
    """추천 레시피 1건의 응답 스키마."""

    id: UUID
    title: str
    cooking_time_min: Optional[int]
    is_llm_generated: bool
    required_match_ratio: float = Field(description="필수 재료 매칭 비율 (0.0 ~ 1.0)")
    optional_match_ratio: float = Field(description="선택 재료 매칭 비율 (0.0 ~ 1.0)")
    matched_ingredients: list[str] = Field(description="보유한 재료명 목록")
    missing_ingredients: list[str] = Field(description="없는 필수 재료명 목록")

    model_config = {"from_attributes": True}


class RecipeRecommendResponse(BaseModel):
    """레시피 추천 응답 스키마."""

    total: int = Field(description="매칭된 레시피 총 수")
    recipes: list[RecipeMatchItem]


# ── GET /recipes/{recipe_id} ──────────────────────────────────────────────────

class RecipeIngredientItem(BaseModel):
    """레시피 상세의 재료 1건."""

    name: str
    quantity: Optional[str]
    is_optional: bool


class RecipeDetailResponse(BaseModel):
    """레시피 상세 조회 응답 스키마."""

    id: UUID
    title: str
    instructions: Optional[str]
    cooking_time_min: Optional[int]
    difficulty: Optional[str]
    is_llm_generated: bool
    source_url: Optional[str]
    ingredients: list[RecipeIngredientItem]

    model_config = {"from_attributes": True}
