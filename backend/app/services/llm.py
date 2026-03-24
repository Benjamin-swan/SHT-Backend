import hashlib
import json
from typing import Any

import httpx
from sqlmodel import Session, select

from app.core.config import settings
from app.models.ingredient import Ingredient
from app.models.llm_cache import LLMCache
from app.models.recipe import Recipe, RecipeIngredient

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# 우선순위 순서로 시도할 모델 목록
# Rate Limit 또는 할당량 초과 시 다음 모델로 자동 폴백
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemma-3-27b-it",
]


# ── 해시 / 프롬프트 ────────────────────────────────────────────────────────────

def build_ingredients_hash(ingredient_names: list[str]) -> str:
    """
    재료명 목록을 정렬 후 합쳐서 SHA-256 해시를 생성합니다.
    순서가 달라도 동일한 재료 조합이면 같은 해시가 나옵니다.
    """
    key = ",".join(sorted(ingredient_names))
    return hashlib.sha256(key.encode()).hexdigest()


def build_prompt(ingredient_names: list[str]) -> str:
    """Gemini에 전달할 레시피 생성 프롬프트를 작성합니다."""
    ingredients_str = ", ".join(ingredient_names)
    return f"""당신은 한국 요리 전문가입니다.
다음 식재료들을 최대한 활용하여 만들 수 있는 한국 요리 레시피 3가지를 JSON 형식으로만 응답하세요.
코드 블록(```)을 사용하지 말고, 순수 JSON만 반환하세요.

식재료: {ingredients_str}

반환 형식:
{{
  "recipes": [
    {{
      "title": "레시피명",
      "cooking_time_min": 30,
      "instructions": "1. 단계별 조리 방법",
      "ingredients": [
        {{"name": "재료명", "quantity": "수량", "is_optional": false}}
      ]
    }}
  ]
}}"""


# ── Gemini API 호출 ────────────────────────────────────────────────────────────

async def call_gemini_api(prompt: str) -> str:
    """
    GEMINI_MODELS 우선순위에 따라 순차적으로 시도합니다.
    429 또는 할당량 초과 시 다음 모델로 자동 폴백합니다.
    모든 모델 실패 시 HTTPException 503 을 반환합니다.
    """
    from fastapi import HTTPException

    last_error: str = ""

    async with httpx.AsyncClient(timeout=30.0) as client:
        for model in GEMINI_MODELS:
            url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={settings.gemini_api_key}"
            response = await client.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )

            if response.status_code == 200:
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

            # 429 또는 할당량 초과 → 다음 모델로 폴백
            if response.status_code == 429:
                last_error = f"{model}: Rate Limit 초과"
                print(f"[llm] {last_error} → 다음 모델로 전환")
                continue

            # 그 외 에러는 즉시 중단
            last_error = f"{model}: {response.status_code}"
            break

    raise HTTPException(
        status_code=503,
        detail=f"모든 Gemini 모델 호출에 실패했습니다. ({last_error})",
    )


def parse_gemini_response(text: str) -> dict[str, Any]:
    """
    Gemini 응답 텍스트에서 JSON을 파싱합니다.
    마크다운 코드 블록(```json ... ```)이 포함된 경우도 처리합니다.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return json.loads(text)


# ── DB 저장 ────────────────────────────────────────────────────────────────────

def _find_or_create_ingredient(name: str, db: Session) -> Ingredient:
    """
    이름으로 식재료를 조회합니다.
    없으면 category='llm_generated' 로 새로 생성합니다.
    """
    ingredient = db.exec(
        select(Ingredient).where(Ingredient.name == name)
    ).first()

    if not ingredient:
        ingredient = Ingredient(name=name, category="llm_generated")
        db.add(ingredient)
        db.flush()  # id 즉시 확보

    return ingredient


def save_parsed_recipes(parsed: dict[str, Any], db: Session) -> list[Recipe]:
    """
    파싱된 레시피 딕셔너리를 RECIPES + RECIPE_INGREDIENTS 테이블에 저장합니다.
    동일한 제목의 레시피가 이미 존재하면 저장 없이 기존 레코드를 반환합니다.
    """
    saved: list[Recipe] = []

    for r in parsed.get("recipes", []):
        # 중복 레시피 방지
        existing = db.exec(
            select(Recipe).where(Recipe.title == r["title"])
        ).first()
        if existing:
            saved.append(existing)
            continue

        recipe = Recipe(
            title=r["title"],
            instructions=r.get("instructions"),
            cooking_time_min=r.get("cooking_time_min"),
            is_llm_generated=True,
        )
        db.add(recipe)
        db.flush()

        for ing_data in r.get("ingredients", []):
            ingredient = _find_or_create_ingredient(ing_data["name"], db)
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=ing_data.get("quantity"),
                is_optional=ing_data.get("is_optional", False),
            ))

        saved.append(recipe)

    db.commit()
    return saved


# ── 식재료 분류 ────────────────────────────────────────────────────────────────

async def classify_ingredient(name: str) -> dict[str, Any]:
    """
    LLM을 호출하여 입력된 이름이 식용 가능한 식재료인지 판단하고 카테고리를 반환합니다.

    Returns:
        {"is_food": True, "category": "과일"}   — 식용 가능
        {"is_food": False, "category": None}    — 식용 불가

    카테고리 예시: 채소, 과일, 육류, 해산물, 유제품, 곡물, 양념, 버섯, 두류, 견과류, 가공식품
    """
    prompt = f"""다음 입력이 요리에 사용할 수 있는 식재료인지 판단하세요.
식용 가능하면 카테고리도 함께 반환하세요.
코드 블록 없이 순수 JSON만 반환하세요.

입력: "{name}"

반환 형식:
{{"is_food": true, "category": "채소"}}
또는
{{"is_food": false, "category": null}}

카테고리는 다음 중 하나만 사용하세요: 채소, 과일, 육류, 해산물, 유제품, 곡물, 양념, 버섯, 두류, 견과류, 가공식품"""

    response_text = await call_gemini_api(prompt)
    return parse_gemini_response(response_text)


# ── 캐시 + 생성 통합 ────────────────────────────────────────────────────────────

async def get_or_generate_recipes(
    ingredient_names: list[str],
    db: Session,
) -> tuple[list[Recipe], bool]:
    """
    재료명 목록으로 레시피를 조회하거나 생성합니다.

    처리 흐름:
        1. 재료명 해시로 LLM_CACHE 조회
        2. 캐시 히트 → hit_count 증가 후 기존 Recipe 반환
        3. 캐시 미스 → Gemini API 호출 → 파싱 → DB 저장 → 캐시 저장

    Returns:
        (recipes, is_cached):
            recipes:   Recipe 객체 목록
            is_cached: 캐시에서 반환됐으면 True
    """
    ingredients_hash = build_ingredients_hash(ingredient_names)

    # 1. 캐시 조회
    cache = db.exec(
        select(LLMCache).where(LLMCache.ingredients_hash == ingredients_hash)
    ).first()

    if cache:
        cache.hit_count += 1
        db.add(cache)
        db.commit()

        titles = [r["title"] for r in (cache.parsed_recipes or {}).get("recipes", [])]
        recipes = [
            db.exec(select(Recipe).where(Recipe.title == t)).first()
            for t in titles
        ]
        return [r for r in recipes if r], True

    # 2. Gemini API 호출
    prompt = build_prompt(ingredient_names)
    response_text = await call_gemini_api(prompt)
    parsed = parse_gemini_response(response_text)

    # 3. 레시피 DB 저장
    recipes = save_parsed_recipes(parsed, db)

    # 4. 캐시 저장
    db.add(LLMCache(
        ingredients_hash=ingredients_hash,
        response_text=response_text,
        parsed_recipes=parsed,
        hit_count=0,
    ))
    db.commit()

    return recipes, False
