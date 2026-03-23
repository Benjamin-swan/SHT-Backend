from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ingredient import Ingredient
from app.models.user import UserIngredientInput, UserSession
from app.schemas.recipe import RecipeMatchItem, RecipeRecommendRequest, RecipeRecommendResponse
from app.services.llm import get_or_generate_recipes
from app.services.matcher import find_matching_recipes

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.post(
    "/recommend",
    response_model=RecipeRecommendResponse,
    summary="입력 재료 기반 추천 레시피 목록 조회",
)
async def recommend_recipes(
    body: RecipeRecommendRequest,
    session: Session = Depends(get_session),
) -> RecipeRecommendResponse:
    """
    사용자가 보유한 식재료를 기준으로 레시피를 추천합니다.

    처리 흐름:
        1. session_id 또는 ingredient_ids 로 보유 재료 확정
        2. DB 매칭 시도 (RECIPES 테이블 기준)
        3. DB 결과 있음 → 매칭 결과 반환
        4. DB 결과 없음 → Gemini API 호출 (캐시 우선) → 생성된 레시피 반환
    """
    # ── 재료 ID 목록 확정 ──────────────────────────────────────────────────────
    if body.session_id:
        user_session = session.get(UserSession, body.session_id)
        if not user_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session_id '{body.session_id}' 를 찾을 수 없습니다.",
            )
        inputs = session.exec(
            select(UserIngredientInput).where(
                UserIngredientInput.session_id == body.session_id
            )
        ).all()
        ingredient_ids = [inp.ingredient_id for inp in inputs]

    elif body.ingredient_ids:
        ingredient_ids = body.ingredient_ids

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id 또는 ingredient_ids 중 하나는 반드시 전달해야 합니다.",
        )

    if not ingredient_ids:
        return RecipeRecommendResponse(total=0, recipes=[])

    # ── DB 매칭 시도 ──────────────────────────────────────────────────────────
    match_results = find_matching_recipes(
        ingredient_ids=ingredient_ids,
        session=session,
        limit=body.limit,
    )

    if match_results:
        recipes = [
            RecipeMatchItem(
                id=r.recipe.id,
                title=r.recipe.title,
                cooking_time_min=r.recipe.cooking_time_min,
                is_llm_generated=r.recipe.is_llm_generated,
                required_match_ratio=r.required_match_ratio,
                optional_match_ratio=r.optional_match_ratio,
                matched_ingredients=r.matched_ingredients,
                missing_ingredients=r.missing_ingredients,
            )
            for r in match_results
        ]
        return RecipeRecommendResponse(total=len(recipes), recipes=recipes)

    # ── DB 결과 없음 → Gemini API 호출 ───────────────────────────────────────
    # 재료 ID → 재료명 변환 (LLM 프롬프트용)
    ingredients = [session.get(Ingredient, iid) for iid in ingredient_ids]
    ingredient_names = [ing.name for ing in ingredients if ing]

    if not ingredient_names:
        return RecipeRecommendResponse(total=0, recipes=[])

    llm_recipes, is_cached = await get_or_generate_recipes(
        ingredient_names=ingredient_names,
        db=session,
    )

    recipes = [
        RecipeMatchItem(
            id=recipe.id,
            title=recipe.title,
            cooking_time_min=recipe.cooking_time_min,
            is_llm_generated=True,
            # LLM이 입력 재료 기반으로 생성했으므로 매칭 비율 1.0
            required_match_ratio=1.0,
            optional_match_ratio=0.0,
            matched_ingredients=ingredient_names,
            missing_ingredients=[],
        )
        for recipe in llm_recipes
    ]

    return RecipeRecommendResponse(total=len(recipes), recipes=recipes)
