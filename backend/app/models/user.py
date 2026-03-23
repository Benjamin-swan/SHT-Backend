from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class AnonymousUser(SQLModel, table=True):
    """
    익명 사용자 테이블.
    로그인 없이 browser_uuid(브라우저 고유 ID)로 사용자를 식별합니다.
    """

    __tablename__ = "anonymous_users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    browser_uuid: str = Field(index=True, description="프론트에서 생성한 브라우저 고유 UUID")
    ip_address: Optional[str] = Field(default=None, description="접속 IP")
    user_agent: Optional[str] = Field(default=None, description="브라우저 User-Agent")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)


class UserSession(SQLModel, table=True):
    """
    사용자 세션 테이블.
    한 명의 익명 사용자가 여러 세션을 가질 수 있습니다 (1:N).
    """

    __tablename__ = "user_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    anonymous_user_id: UUID = Field(foreign_key="anonymous_users.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(description="세션 만료 시각")


class UserIngredientInput(SQLModel, table=True):
    """
    사용자가 입력한 식재료 이벤트 테이블.
    - input_method: 'button' (빈출 식재료 버튼 클릭) 또는 'direct' (직접 텍스트 입력)
    - freshness_status / expires_at: freshness.py 서비스가 계산하여 저장
    """

    __tablename__ = "user_ingredient_inputs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(foreign_key="user_sessions.id", index=True)
    ingredient_id: UUID = Field(foreign_key="ingredients.id", index=True)
    input_method: str = Field(description="입력 방식: 'button' 또는 'direct'")
    freshness_status: str = Field(default="fresh", description="신선도 상태")
    expires_at: datetime = Field(description="식재료 유효기간 만료 시각")
    created_at: datetime = Field(default_factory=datetime.utcnow)
