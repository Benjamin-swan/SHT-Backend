from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IngredientResponse(BaseModel):
    """
    GET /ingredients API의 응답 스키마.
    DB 모델(Ingredient)과 분리하여 API 응답 형태를 독립적으로 관리합니다.
    """

    id: UUID
    name: str
    category: str
    created_at: datetime

    model_config = {"from_attributes": True}
