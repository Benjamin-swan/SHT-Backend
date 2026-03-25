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

# 호출 순서: Gemini 2.5 Flash → gemma-3-27b-it (429 폴백)
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
    """LLM에 전달할 레시피 생성 프롬프트를 작성합니다. (Groq / Gemini 공통 사용)"""
    ingredients_str = ", ".join(ingredient_names)
    return f"""당신은 한국 요리 전문가입니다.

[사전 검증 규칙 — 반드시 먼저 확인하세요]

1. [정규화] 입력값을 그대로 식재료로 취급하되, 아래 유형만 변환하세요:
   - 브랜드명 포함(가공식품): 동원참치캔→참치, 스팸→햄, 비비고김치→김치, 풀무원두부→두부, 오뚜기마요네즈→마요네즈, 햇반→밥, CJ햇반→밥
   - 한국 과자/스낵 브랜드: 칸쵸→초코과자, 새우깡→새우맛과자, 오레오→초코샌드위치쿠키, 포카칩→감자칩, 꼬깔콘→옥수수과자
   - 영문 표기: spam→햄, cheese→치즈, egg→계란
   - 용량/단위/조사 포함: 계란10개→계란, 돼지고기300g→돼지고기
   - 냉동 표기: 냉동만두→만두, 냉동새우→새우
   - 그 외 모든 입력(요리명, 떡류, 완성품, 가공식품 등)은 그대로 식재료로 사용하세요.
     예: 송편→송편, 치킨→치킨, 김치찌개→김치찌개, 라면→라면 (변환 없이 그대로 활용)

2. [차단] 아래 경우에만 {{"recipes": []}} 를 반환하세요 (판단이 애매하면 레시피를 만드세요):
   - 명백히 음식이 아닌 것: 나무, 돌, 플라스틱, 세제, 종이, 조리도구
   - 독성/유해 물질: 독극물, 화학물질, 농약, 의약품
   - 식재료를 전혀 특정할 수 없는 자연어: "아무거나", "냉장고에 있는 거 다"

3. [주의 레시피 생성] 레시피를 생성하되 instructions 마지막에 주의사항 1문장을 추가하세요:
   - 주요 알레르기 유발 식품 포함 시: "※ 해당 식품 알레르기가 있는 경우 주의하세요."
   - 날것으로 먹으면 위험한 식품 포함 시: "※ 반드시 충분히 가열 조리 후 섭취하세요."

4. [재료 수 제한] 입력 재료가 10개를 초과하면 앞에서부터 10개만 사용하세요.

5. [정상 진행] 위 1~4번에 해당하지 않으면 반드시 정확히 3개의 레시피를 만드세요.

[레시피 생성 규칙]
- 사용 가능한 재료는 오직 아래 두 가지입니다:
  A) 사용자가 제공한 식재료: {ingredients_str}
  B-1) 필수 기본 조미료(항상 보유 중이라 가정, is_optional: false): 물, 소금, 후추, 식용유, 설탕, 간장, 참기름, 다진마늘, 식초, 고춧가루, 된장, 고추장
  B-2) 선택 기본 조미료(없을 수도 있으므로 is_optional: true로 표시): 버터, 올리브오일, 깨
- 기본 조미료는 반드시 적극적으로 활용하여 맛있는 요리를 완성하세요. 조미료 없이 밋밋한 레시피를 만들지 마세요.
- 1인분 기준으로 레시피를 작성하세요. 사용자가 입력한 재료의 양이 소량(예: 밥 1컵, 오이 1개, 치즈 1장)이면 1인분으로 판단하세요.

- ★ 레시피의 ingredients 목록에 재료를 추가하기 전, 반드시 아래 질문을 스스로 확인하세요:
  "이 재료가 A 또는 B 목록에 있는가?"
  → YES: 포함 가능
  → NO: 절대 포함 불가. 해당 재료 없이 만들 수 있는 다른 요리로 대체하세요.

- 나쁜 예 (절대 금지): 입력이 [크림치즈, 밥]인데 ingredients에 "빵"을 추가하거나 title을 "크림치즈 샌드위치"로 짓는 것
- 좋은 예: 입력이 [크림치즈, 밥]이면 → "크림치즈 주먹밥", "크림치즈 볶음밥", "크림치즈 덮밥" 처럼 실제 보유 재료만으로 구성

- 재료가 적어 보여도 괜찮습니다. 있는 재료만으로 최대한 활용하는 것이 이 서비스의 핵심입니다.
- 레시피명(title)은 실제 한국 가정식·식당에서 쓰는 자연스러운 요리명을 사용하세요.
  - 올바른 예: "김치찌개", "계란말이", "두부조림", "콩나물무침", "제육볶음", "된장찌개", "소고기미역국"
  - 잘못된 예: "채소와 계란의 조화", "영양 가득 두부요리", "특제 볶음 요리" (설명형·창작형 금지)
  - 가능하면 [주재료 + 조리법] 형태로 작성하세요 (예: 볶음·조림·찌개·국·무침·전·구이·탕·밥)
  - 단, 과자·스낵류(예: 칸쵸, 새우깡, 오레오 등)는 조림·무침·찌개 같은 조리법을 붙이지 마세요. 대신 자연스러운 활용법(예: 칸쵸치킨, 칸쵸크러스트 등)으로 표현하세요.
  - "맛있는", "황금", "특제", "간단", "초간단", "영양" 같은 수식어는 절대 붙이지 마세요.
- 조리 순서(instructions)는 최소 3단계, 최대 5단계로만 작성하세요. 각 단계는 한 문장으로 간결하게 작성하세요.
- 각 레시피마다 실용적인 셰프의 팁(chef_tip)을 한 문장으로 제공하세요.
- 난이도(difficulty)는 EASY / NORMAL / HARD 중 하나로 판단하세요.
- 코드 블록(```)을 사용하지 말고, 순수 JSON만 반환하세요.

식재료: {ingredients_str}

반환 형식:
{{
  "recipes": [
    {{
      "title": "레시피명 (한글만, 형용사 없이)",
      "cooking_time_min": 30,
      "difficulty": "EASY",
      "instructions": "1. 단계별 조리 방법\\n2. 다음 단계",
      "ingredients": [
        {{"name": "재료명", "quantity": "수량", "is_optional": false}}
      ],
      "chef_tip": "셰프의 팁 한 문장"
    }}
  ]
}}"""


# ── LLM API 호출 ────────────────────────────────────────────────────────────────
# 호출 순서: [1] Gemini 2.5 Flash → [2] gemma-3-27b-it (429 폴백)
# 앞 모델이 성공하면 뒤 모델은 호출하지 않습니다.

async def call_llm_api(prompt: str) -> str:
    """
    LLM 호출 통합 함수.
    - 1순위: Gemini 2.5 Flash
    - 2순위: gemma-3-27b-it (429 Rate Limit 폴백)
    모든 모델 실패 시 HTTPException 503 을 반환합니다.
    """
    from fastapi import HTTPException

    last_error: str = ""

    async with httpx.AsyncClient(timeout=60.0) as client:
        for model in GEMINI_MODELS:
            url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={settings.gemini_api_key}"
            # thinkingBudget=0: Gemini 2.5 Flash의 thinking 모드 비활성화 → 응답 속도 개선
            response = await client.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

            # 429 → 다음 모델로 폴백
            if response.status_code == 429:
                last_error = f"{model}: Rate Limit 초과"
                print(f"[llm] {last_error} → 다음 모델로 전환")
                continue

            # 그 외 에러는 즉시 중단
            last_error = f"{model}: {response.status_code}"
            break

    raise HTTPException(
        status_code=503,
        detail=f"모든 LLM 모델 호출에 실패했습니다. ({last_error})",
    )


def parse_llm_response(text: str) -> dict[str, Any]:
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

        # 셰프의 팁과 난이도를 DB 스키마 변경 없이 instructions 끝에 태그로 저장합니다.
        # LLM이 instructions를 배열로 반환하는 경우 줄바꿈 문자열로 변환합니다.
        instructions_raw = r.get("instructions", "")
        if isinstance(instructions_raw, list):
            instructions_text = "\n".join(
                f"{i + 1}. {step}" for i, step in enumerate(instructions_raw)
            )
        else:
            instructions_text = instructions_raw
        chef_tip_text = r.get("chef_tip")
        if chef_tip_text:
            instructions_text += f"\n\n[CHEF_TIP]\n{chef_tip_text}"
        difficulty_text = r.get("difficulty", "EASY").upper()
        if difficulty_text not in ("EASY", "NORMAL", "HARD"):
            difficulty_text = "EASY"
        instructions_text += f"\n\n[DIFFICULTY]\n{difficulty_text}"

        recipe = Recipe(
            title=r["title"],
            instructions=instructions_text,
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

    카테고리 예시: grain, 단백질, 채소, 달걀, 양념, 발효
    """
    prompt = f"""다음 입력이 요리에 사용할 수 있는 식재료인지 판단하세요.
식용 가능하면 카테고리도 함께 반환하세요.
코드 블록 없이 순수 JSON만 반환하세요.

입력: "{name}"

반환 형식:
{{"is_food": true, "category": "채소"}}
또는
{{"is_food": false, "category": null}}

카테고리는 다음 중 하나만 사용하세요: grain, 단백질, 채소, 달걀, 양념, 발효"""

    response_text = await call_llm_api(prompt)
    return parse_llm_response(response_text)


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
        4. LLM이 비식품/독성 물질로 판단하면 빈 목록 반환 (캐시 미저장)

    Returns:
        (recipes, is_cached):
            recipes:   Recipe 객체 목록 (비식품 포함 시 빈 리스트)
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
    response_text = await call_llm_api(prompt)
    print(f"[llm] raw response: {response_text[:500]}")  # 디버그: 실제 LLM 응답 확인용
    parsed = parse_llm_response(response_text)
    print(f"[llm] parsed recipes count: {len(parsed.get('recipes', []))}")

    # 3. 비식품/독성 재료 포함 시 — 빈 목록 반환 (캐시 저장 안 함)
    # LLM이 검증 규칙에 따라 {"recipes": []} 를 반환한 경우입니다.
    if not parsed.get("recipes"):
        return [], False

    # 4. 레시피 DB 저장
    recipes = save_parsed_recipes(parsed, db)

    # 5. 캐시 저장
    db.add(LLMCache(
        ingredients_hash=ingredients_hash,
        response_text=response_text,
        parsed_recipes=parsed,
        hit_count=0,
    ))
    db.commit()

    return recipes, False
