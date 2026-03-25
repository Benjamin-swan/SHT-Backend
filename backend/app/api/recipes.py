from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import UserIngredientInput, UserSession
from app.schemas.recipe import (
    RecipeDetailResponse,
    RecipeIngredientItem,
    RecipeMatchItem,
    RecipeRecommendRequest,
    RecipeRecommendResponse,
)
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
    # 우선순위: ingredient_names > session_id > ingredient_ids
    skip_db_match = False  # DB 매칭을 건너뛰고 LLM으로 직행할지 여부
    if body.ingredient_names:
        # 재료명으로 DB에서 UUID를 조회합니다.
        matched = session.exec(
            select(Ingredient).where(Ingredient.name.in_(body.ingredient_names))
        ).all()
        ingredient_ids = [ing.id for ing in matched]

        # 입력 재료 중 DB에 없는 것이 하나라도 있으면 DB 매칭을 건너뜁니다.
        # 예: "스팸, 라면" 입력 시 라면이 DB에 없으면 스팸 단독 레시피가 반환되는 문제 방지.
        # LLM은 원본 ingredient_names 전체를 받아 올바른 조합으로 레시피를 생성합니다.
        if len(ingredient_ids) < len(body.ingredient_names):
            skip_db_match = True

    elif body.session_id:
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
            detail="ingredient_names, session_id, ingredient_ids 중 하나는 반드시 전달해야 합니다.",
        )

    if not ingredient_ids:
        return RecipeRecommendResponse(total=0, recipes=[])

    # ── DB 매칭 시도 ──────────────────────────────────────────────────────────
    match_results = [] if skip_db_match else find_matching_recipes(
        ingredient_ids=ingredient_ids,
        session=session,
        limit=3,
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

    # ── DB 결과 없음 → LLM API 호출 ──────────────────────────────────────────
    # LLM에 전달할 재료명 확정:
    # ingredient_names로 요청이 들어온 경우 원본을 그대로 사용합니다.
    # ID→이름 변환 시 DB에 없는 재료(예: 치킨, 칸쵸)가 누락되는 버그 방지.
    if body.ingredient_names:
        ingredient_names = body.ingredient_names
    else:
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


@router.get(
    "/{recipe_id}",
    response_model=RecipeDetailResponse,
    summary="레시피 상세 조회",
)
def get_recipe_detail(
    recipe_id: UUID,
    session: Session = Depends(get_session),
) -> RecipeDetailResponse:
    """
    레시피 ID로 상세 정보를 반환합니다.
    재료 목록(이름, 수량, 선택여부)이 함께 포함됩니다.
    """
    recipe = session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recipe_id '{recipe_id}' 를 찾을 수 없습니다.",
        )

    # 레시피에 연결된 재료 목록 조회
    recipe_ingredients = session.exec(
        select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)
    ).all()

    ingredients_list = []
    for ri in recipe_ingredients:
        ingredient = session.get(Ingredient, ri.ingredient_id)
        if ingredient:
            ingredients_list.append(
                RecipeIngredientItem(
                    name=ingredient.name,
                    quantity=ri.quantity,
                    is_optional=ri.is_optional,
                )
            )

    # instructions에서 [DIFFICULTY] 태그를 파싱합니다.
    # 저장 형식: "...조리내용...\n\n[CHEF_TIP]\n팁\n\n[DIFFICULTY]\nEASY"
    difficulty = None
    instructions_clean = recipe.instructions
    if recipe.instructions and "[DIFFICULTY]" in recipe.instructions:
        parts = recipe.instructions.split("[DIFFICULTY]")
        instructions_clean = parts[0].strip()
        difficulty = parts[1].strip().splitlines()[0].strip()

    return RecipeDetailResponse(
        id=recipe.id,
        title=recipe.title,
        instructions=instructions_clean,
        cooking_time_min=recipe.cooking_time_min,
        difficulty=difficulty,
        is_llm_generated=recipe.is_llm_generated,
        source_url=recipe.source_url,
        ingredients=ingredients_list,
    )
