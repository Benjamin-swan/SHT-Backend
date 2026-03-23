from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class InteractionLog(SQLModel, table=True):
    """
    사용자 행동 이벤트 로그 테이블.

    현재 사용 중인 event_type:
        - "recipe_click": 추천 레시피 클릭

    extra_data (DB 컬럼명: metadata):
        - SQLAlchemy에서 'metadata'는 예약어이므로 Python 속성명은 extra_data 로 사용
        - 클릭 위치(rank), 입력 재료 수 등 부가 정보를 자유롭게 저장
    """

    __tablename__ = "interaction_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(foreign_key="user_sessions.id", index=True)
    recipe_id: UUID = Field(foreign_key="recipes.id", index=True)
    event_type: str = Field(index=True, description="이벤트 종류 (예: recipe_click)")
    extra_data: Optional[dict] = Field(
        default=None,
        sa_column=Column("metadata", JSON),
        description="부가 정보 (JSON). DB 컬럼명: metadata",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
