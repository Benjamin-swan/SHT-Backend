from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── POST /recipes/recommend ───────────────────────────────────────────────────

class RecipeRecommendRequest(BaseModel):
    """
    레시피 추천 요청 스키마.

    두 가지 방식을 지원합니다 (둘 중 하나 필수):
        - session_id:      세션 ID → 해당 세션의 입력 재료를 자동으로 조회
        - ingredient_ids:  재료 UUID 직접 전달 (세션 없이 테스트할 때 유용)

    limit: 반환할 최대 레시피 수 (기본 10, 최대 20)
    """

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
