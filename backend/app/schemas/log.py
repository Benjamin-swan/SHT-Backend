from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# 사용자가 선택 가능한 신선도 상태값 타입 (코드 전역에서 재사용)
FreshnessStatus = Literal["싱싱", "임박"]


# ── POST /logs/event ──────────────────────────────────────────────────────────

class IngredientEventRequest(BaseModel):
    """
    식재료 입력 이벤트 요청 스키마.

    프론트엔드 흐름:
        1. 사용자가 식재료를 선택 (button: 빈출 목록 클릭 / direct: 직접 입력)
        2. 싱싱 또는 임박 버튼을 눌러 신선도를 지정
        3. 이 두 정보를 묶어 POST /logs/event 로 전송
    """

    browser_uuid: str = Field(description="브라우저 고유 UUID (프론트 localStorage 보관)")
    ingredient_id: UUID = Field(description="선택된 식재료 ID (INGREDIENTS 테이블 기준)")
    input_method: Literal["button", "direct"] = Field(
        description="입력 방식: 'button'=빈출 목록 클릭, 'direct'=직접 텍스트 입력"
    )
    freshness_status: FreshnessStatus = Field(
        default="싱싱",
        description="신선도 상태: '싱싱'=+48h, '임박'=+24h",
    )
    session_id: UUID | None = Field(default=None, description="기존 세션 ID (없으면 신규 생성)")
    ip_address: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)


class IngredientEventResponse(BaseModel):
    """식재료 입력 이벤트 저장 응답 스키마."""

    event_id: UUID
    session_id: UUID
    ingredient_id: UUID
    ingredient_name: str
    input_method: str
    freshness_status: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── PATCH /logs/event/{event_id}/freshness ────────────────────────────────────

class FreshnessUpdateRequest(BaseModel):
    """
    신선도 상태 변경 요청 스키마.
    싱싱 → 임박 방향 변경만 허용합니다.
    """

    freshness_status: Literal["임박"] = Field(description="변경할 신선도 상태 (현재는 '임박'만 허용)")


class FreshnessUpdateResponse(BaseModel):
    """신선도 상태 변경 응답 스키마."""

    event_id: UUID
    ingredient_name: str
    previous_status: str
    current_status: str
    expires_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── GET /sessions/{session_id}/ingredients ────────────────────────────────────

class SessionIngredientItem(BaseModel):
    """세션 내 식재료 1건의 응답 스키마."""

    event_id: UUID
    ingredient_id: UUID
    ingredient_name: str
    input_method: str
    freshness_status: str
    expires_at: datetime
    is_expired: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── POST /logs/recipe-click ───────────────────────────────────────────────────

class RecipeClickRequest(BaseModel):
    """
    추천 레시피 클릭 이벤트 요청 스키마.

    extra_data 예시:
        {
            "rank": 1,              # 추천 목록에서 몇 번째 항목이었는지
            "required_match_ratio": 0.85  # 클릭 시점의 매칭 비율
        }
    """

    session_id: UUID = Field(description="현재 사용자 세션 ID")
    recipe_id: UUID = Field(description="클릭된 레시피 ID")
    extra_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="부가 정보 (클릭 순위, 매칭 비율 등)",
    )


class RecipeClickResponse(BaseModel):
    """추천 레시피 클릭 이벤트 저장 응답 스키마."""

    log_id: UUID
    session_id: UUID
    recipe_id: UUID
    recipe_title: str
    event_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── GET /logs/interactions/{session_id} ───────────────────────────────────────

class InteractionLogItem(BaseModel):
    """클릭 이벤트 조회 1건의 응답 스키마."""

    log_id: UUID
    recipe_id: UUID
    recipe_title: str
    event_type: str
    extra_data: Optional[dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}
