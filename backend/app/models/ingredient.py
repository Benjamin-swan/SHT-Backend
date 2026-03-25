from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Ingredient(SQLModel, table=True):
    """
    식재료 마스터 테이블.
    - category = "frequent" 인 항목이 '한국인 빈출 식재료' 목록입니다.
    - unit 컬럼은 MVP 단계에서 UX 혼란 방지를 위해 제외되었습니다.
    """

    __tablename__: ClassVar[str] = "ingredients"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, description="식재료명")
    category: str = Field(index=True, description="카테고리 (예: 채소, 단백질, frequent 등)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
