from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Recipe(SQLModel, table=True):
    """
    레시피 마스터 테이블.
    - is_llm_generated: DB 레시피(False) vs Gemini가 생성한 레시피(True) 구분
    """

    __tablename__ = "recipes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(index=True, description="레시피명")
    source: Optional[str] = Field(default=None, description="출처 (예: 만개의레시피)")
    source_url: Optional[str] = Field(default=None, description="원문 URL")
    instructions: Optional[str] = Field(default=None, description="조리 방법")
    cooking_time_min: Optional[int] = Field(default=None, description="조리 시간 (분)")
    is_llm_generated: bool = Field(default=False, description="LLM 생성 레시피 여부")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RecipeIngredient(SQLModel, table=True):
    """
    레시피-식재료 연결 테이블 (N:M 관계 해소).
    - is_optional=False: 필수 재료 → 매칭 점수 계산에 사용
    - is_optional=True : 선택 재료 → 보너스 점수
    """

    __tablename__ = "recipe_ingredients"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    recipe_id: UUID = Field(foreign_key="recipes.id", index=True)
    ingredient_id: UUID = Field(foreign_key="ingredients.id", index=True)
    quantity: Optional[str] = Field(default=None, description="필요 수량 (예: 2쪽, 100g)")
    is_optional: bool = Field(default=False, description="선택 재료 여부")
