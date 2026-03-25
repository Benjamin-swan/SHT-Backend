from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class LLMCache(SQLModel, table=True):
    """
    LLM API 응답 캐시 테이블.
    동일한 재료 조합 재요청 시 API 재호출 없이 캐시에서 반환합니다.

    ingredients_hash: sorted(재료명 목록) → SHA-256 → 캐시 키
    parsed_recipes:   파싱된 레시피 목록 (JSON)
    hit_count:        캐시 히트 횟수 (분석용)
    """

    __tablename__ = "llm_cache"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    ingredients_hash: str = Field(index=True, description="재료 조합 SHA-256 해시")
    response_text: str = Field(description="LLM API 원본 응답 텍스트")
    parsed_recipes: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column("parsed_recipes", JSON),
        description="파싱된 레시피 목록 (JSON)",
    )
    hit_count: int = Field(default=0, description="캐시 히트 횟수")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
