from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session, select

from app.models.ingredient import Ingredient
from app.models.recipe import Recipe, RecipeIngredient


@dataclass
class RecipeMatchResult:
    """
    레시피 매칭 결과를 담는 데이터 클래스.

    Attributes:
        recipe:                레시피 객체
        required_match_ratio:  필수 재료 매칭 비율 (0.0 ~ 1.0)
        optional_match_ratio:  선택 재료 매칭 비율 (0.0 ~ 1.0)
        matched_ingredients:   사용자가 보유한 재료명 목록
        missing_ingredients:   사용자에게 없는 필수 재료명 목록
    """

    recipe: Recipe
    required_match_ratio: float
    optional_match_ratio: float
    matched_ingredients: list[str]
    missing_ingredients: list[str]


def find_matching_recipes(
    ingredient_ids: list[UUID],
    session: Session,
    limit: int = 10,
    min_match_ratio: float = 0.5,
) -> list[RecipeMatchResult]:
    """
    사용자의 보유 식재료를 기반으로 만들 수 있는 레시피를 매칭하여 반환합니다.

    매칭 알고리즘:
        1. 전체 레시피를 순회하며 각 레시피의 필수/선택 재료를 조회
        2. 사용자 보유 재료와 교집합으로 매칭 점수 계산
        3. 필수 재료 매칭 비율 ≥ min_match_ratio 인 레시피만 포함
        4. 필수 매칭 비율 내림차순 → 선택 매칭 비율 내림차순으로 정렬

    Args:
        ingredient_ids:   사용자가 보유한 식재료 UUID 리스트
        session:          DB 세션
        limit:            반환할 최대 레시피 수 (기본: 10)
        min_match_ratio:  최소 필수 재료 매칭 비율 (기본: 0.5 = 50%)

    Returns:
        RecipeMatchResult 리스트 (매칭 점수 내림차순)
    """
    if not ingredient_ids:
        return []

    user_ingredient_ids: set[UUID] = set(ingredient_ids)

    # 전체 재료명을 한 번에 조회 (N+1 쿼리 방지)
    all_ingredients = session.exec(select(Ingredient)).all()
    ingredient_name_map: dict[UUID, str] = {ing.id: ing.name for ing in all_ingredients}

    # 전체 레시피 조회
    recipes = session.exec(select(Recipe)).all()

    results: list[RecipeMatchResult] = []

    for recipe in recipes:
        # 해당 레시피의 재료 목록 조회
        recipe_ingredients = session.exec(
            select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
        ).all()

        required = [ri for ri in recipe_ingredients if not ri.is_optional]
        optional = [ri for ri in recipe_ingredients if ri.is_optional]

        # 필수 재료가 없는 레시피는 매칭 불가 → 스킵
        if not required:
            continue

        required_ids = {ri.ingredient_id for ri in required}
        optional_ids = {ri.ingredient_id for ri in optional}

        matched_required = required_ids & user_ingredient_ids
        matched_optional = optional_ids & user_ingredient_ids
        missing_required = required_ids - user_ingredient_ids

        required_match_ratio = len(matched_required) / len(required_ids)
        optional_match_ratio = (
            len(matched_optional) / len(optional_ids) if optional_ids else 0.0
        )

        # 최소 매칭 비율 미달 레시피 제외
        if required_match_ratio < min_match_ratio:
            continue

        results.append(
            RecipeMatchResult(
                recipe=recipe,
                required_match_ratio=round(required_match_ratio, 2),
                optional_match_ratio=round(optional_match_ratio, 2),
                matched_ingredients=[
                    ingredient_name_map[uid]
                    for uid in matched_required | matched_optional
                    if uid in ingredient_name_map
                ],
                missing_ingredients=[
                    ingredient_name_map[uid]
                    for uid in missing_required
                    if uid in ingredient_name_map
                ],
            )
        )

    # 필수 매칭 비율 → 선택 매칭 비율 순으로 내림차순 정렬
    results.sort(
        key=lambda r: (r.required_match_ratio, r.optional_match_ratio),
        reverse=True,
    )

    return results[:limit]
