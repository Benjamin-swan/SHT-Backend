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


class IngredientCreateRequest(BaseModel):
    """POST /ingredients 요청 스키마."""

    name: str


class IngredientCreateResponse(BaseModel):
    """
    POST /ingredients 응답 스키마.
    is_new: 이번 요청으로 새로 등록된 경우 True, 기존에 존재하던 경우 False.
    """

    id: UUID
    name: str
    category: str
    created_at: datetime
    is_new: bool

    model_config = {"from_attributes": True}
