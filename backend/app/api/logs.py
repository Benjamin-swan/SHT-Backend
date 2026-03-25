from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.ingredient import Ingredient
from app.models.interaction import InteractionLog
from app.models.recipe import Recipe
from app.models.user import AnonymousUser, UserIngredientInput, UserSession
from app.schemas.log import (
    FreshnessUpdateRequest,
    FreshnessUpdateResponse,
    IngredientEventRequest,
    IngredientEventResponse,
    IngredientEventResponse,
    InteractionLogItem,
    RecipeInteractionRequest,
    RecipeInteractionResponse,
    SessionIngredientItem,
)
from app.services.freshness import calculate_expires_at, is_expired

router = APIRouter(tags=["logs"])

SESSION_TTL_HOURS = 24


# ── POST /logs/event ──────────────────────────────────────────────────────────

@router.post(
    "/logs/event",
    response_model=IngredientEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="식재료 입력 이벤트 저장",
)
def log_ingredient_event(
    body: IngredientEventRequest,
    session: Session = Depends(get_session),
) -> IngredientEventResponse:
    """
    사용자의 식재료 입력 이벤트를 저장합니다.

    처리 흐름:
        1. browser_uuid 로 익명 사용자 조회 또는 신규 생성
        2. 유효한 세션이 있으면 재사용, 없으면 신규 세션 생성
        3. ingredient_id 유효성 검증
        4. freshness_status('싱싱'/'임박')로 expires_at 계산
        5. UserIngredientInput 저장
    """
    # 1. 익명 사용자 조회 또는 생성
    anon_user = session.exec(
        select(AnonymousUser).where(AnonymousUser.browser_uuid == body.browser_uuid)
    ).first()

    if not anon_user:
        anon_user = AnonymousUser(
            browser_uuid=body.browser_uuid,
            ip_address=body.ip_address,
            user_agent=body.user_agent,
        )
        session.add(anon_user)
        session.flush()
    else:
        anon_user.last_seen_at = datetime.utcnow()
        session.add(anon_user)

    # 2. 유효한 세션 조회 또는 신규 생성
    user_session = None
    if body.session_id:
        user_session = session.exec(
            select(UserSession).where(
                UserSession.id == body.session_id,
                UserSession.anonymous_user_id == anon_user.id,
                UserSession.expires_at > datetime.utcnow(),
            )
        ).first()

    if not user_session:
        user_session = UserSession(
            anonymous_user_id=anon_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
        )
        session.add(user_session)
        session.flush()

    # 3. ingredient_id 유효성 검증
    ingredient = session.get(Ingredient, body.ingredient_id)
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ingredient_id '{body.ingredient_id}' 를 찾을 수 없습니다.",
        )

    # 4. 신선도 기반 유효기간 계산 (싱싱=+48h, 임박=+24h)
    expires_at = calculate_expires_at(body.freshness_status)

    # 5. 이벤트 저장
    event = UserIngredientInput(
        session_id=user_session.id,
        ingredient_id=body.ingredient_id,
        input_method=body.input_method,
        freshness_status=body.freshness_status,
        expires_at=expires_at,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    return IngredientEventResponse(
        event_id=event.id,
        session_id=user_session.id,
        ingredient_id=event.ingredient_id,
        ingredient_name=ingredient.name,
        input_method=event.input_method,
        freshness_status=event.freshness_status,
        expires_at=event.expires_at,
        created_at=event.created_at,
    )


# ── PATCH /logs/event/{event_id}/freshness ────────────────────────────────────

@router.patch(
    "/logs/event/{event_id}/freshness",
    response_model=FreshnessUpdateResponse,
    summary="식재료 신선도 상태 변경 (싱싱 → 임박)",
)
def update_freshness(
    event_id: str,
    body: FreshnessUpdateRequest,
    session: Session = Depends(get_session),
) -> FreshnessUpdateResponse:
    """
    식재료 신선도 상태를 싱싱 → 임박으로 변경합니다.

    규칙:
        - 싱싱 → 임박 변경만 허용 (임박 → 싱싱 복구 불가)
        - 이미 임박 상태인 경우 400 에러 반환
        - 존재하지 않는 event_id 는 404 반환
    """
    event = session.get(UserIngredientInput, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"event_id '{event_id}' 를 찾을 수 없습니다.",
        )

    if event.freshness_status == "임박":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 '임박' 상태입니다. 싱싱 → 임박 방향 변경만 허용됩니다.",
        )

    ingredient = session.get(Ingredient, event.ingredient_id)
    previous_status = event.freshness_status

    # 임박으로 변경: expires_at 재계산
    event.freshness_status = "임박"
    event.expires_at = calculate_expires_at("임박")
    session.add(event)
    session.commit()
    session.refresh(event)

    return FreshnessUpdateResponse(
        event_id=event.id,
        ingredient_name=ingredient.name if ingredient else "알 수 없음",
        previous_status=previous_status,
        current_status=event.freshness_status,
        expires_at=event.expires_at,
        updated_at=datetime.utcnow(),
    )


# ── GET /sessions/{session_id}/ingredients ────────────────────────────────────

@router.get(
    "/sessions/{session_id}/ingredients",
    response_model=list[SessionIngredientItem],
    summary="세션 내 식재료 목록 조회 (신선도 포함)",
)
def get_session_ingredients(
    session_id: str,
    session: Session = Depends(get_session),
) -> list[SessionIngredientItem]:
    """
    특정 세션에서 입력된 식재료 목록을 신선도 상태와 함께 반환합니다.

    반환 데이터:
        - 식재료명, 입력방식, 신선도 상태(싱싱/임박), 만료 시각
        - is_expired: 현재 시각 기준으로 유효기간 초과 여부
    """
    user_session = session.get(UserSession, session_id)
    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session_id '{session_id}' 를 찾을 수 없습니다.",
        )

    events = session.exec(
        select(UserIngredientInput).where(UserIngredientInput.session_id == session_id)
    ).all()

    result = []
    for event in events:
        ingredient = session.get(Ingredient, event.ingredient_id)
        result.append(
            SessionIngredientItem(
                event_id=event.id,
                ingredient_id=event.ingredient_id,
                ingredient_name=ingredient.name if ingredient else "알 수 없음",
                input_method=event.input_method,
                freshness_status=event.freshness_status,
                expires_at=event.expires_at,
                is_expired=is_expired(event.expires_at),
                created_at=event.created_at,
            )
        )

    return result


# ── POST /logs/interaction ───────────────────────────────────────────────────

@router.post(
    "/logs/interaction",
    response_model=RecipeInteractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="추천 레시피 상호작용 이벤트 저장",
)
def log_recipe_interaction(
    body: RecipeInteractionRequest,
    session: Session = Depends(get_session),
) -> RecipeInteractionResponse:
    """
    사용자가 추천 레시피를 클릭하거나 저장(하트)했을 때 이벤트를 저장합니다.

    처리 흐름:
        1. session_id 유효성 검증
        2. recipe_id 유효성 검증
        3. InteractionLog 레코드 저장 (event_type 동적 적용)
    """
    # 1. session_id가 user_sessions에 없으면 자동 생성 (MVP 허용 흐름)
    user_session = session.get(UserSession, body.session_id)
    if not user_session:
        anon_user = AnonymousUser(browser_uuid=str(body.session_id))
        session.add(anon_user)
        session.flush()
        user_session = UserSession(
            id=body.session_id,
            anonymous_user_id=anon_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
        )
        session.add(user_session)
        session.flush()

    # 2. 레시피 유효성 검증
    recipe = session.get(Recipe, body.recipe_id)
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recipe_id '{body.recipe_id}' 를 찾을 수 없습니다.",
        )

    # 3. 이벤트 저장
    log = InteractionLog(
        session_id=body.session_id,
        recipe_id=body.recipe_id,
        event_type=body.event_type,
        extra_data=body.extra_data,
    )
    session.add(log)
    session.commit()
    session.refresh(log)

    return RecipeInteractionResponse(
        log_id=log.id,
        session_id=log.session_id,
        recipe_id=log.recipe_id,
        recipe_title=recipe.title,
        event_type=log.event_type,
        created_at=log.created_at,
    )


# ── GET /logs/interactions/{session_id} ───────────────────────────────────────

@router.get(
    "/logs/interactions/{session_id}",
    response_model=list[InteractionLogItem],
    summary="세션 내 클릭 이벤트 이력 조회",
)
def get_interaction_logs(
    session_id: str,
    session: Session = Depends(get_session),
) -> list[InteractionLogItem]:
    """
    특정 세션의 추천 레시피 클릭 이력을 반환합니다.

    반환 데이터:
        - 클릭된 레시피명, 이벤트 타입, 부가 정보(rank 등), 클릭 시각
    """
    user_session = session.get(UserSession, session_id)
    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session_id '{session_id}' 를 찾을 수 없습니다.",
        )

    logs = session.exec(
        select(InteractionLog)
        .where(InteractionLog.session_id == session_id)
        .order_by(InteractionLog.created_at.desc())
    ).all()

    result = []
    for log in logs:
        recipe = session.get(Recipe, log.recipe_id)
        result.append(
            InteractionLogItem(
                log_id=log.id,
                recipe_id=log.recipe_id,
                recipe_title=recipe.title if recipe else "알 수 없음",
                event_type=log.event_type,
                extra_data=log.extra_data,
                created_at=log.created_at,
            )
        )

    return result
