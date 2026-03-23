from datetime import datetime, timedelta
from typing import Literal

FreshnessStatus = Literal["싱싱", "임박"]

# 사용자가 선택한 신선도 상태 → 유효시간(시간 단위)
FRESHNESS_TTL: dict[str, int] = {
    "싱싱": 48,  # 싱싱 버튼 → +48시간
    "임박": 24,  # 임박 버튼 → +24시간
}


def calculate_expires_at(freshness_status: FreshnessStatus) -> datetime:
    """
    사용자가 선택한 신선도 상태에 따라 유효기간 만료 시각을 계산합니다.

    Args:
        freshness_status: '싱싱' 또는 '임박'

    Returns:
        현재 UTC 시각 + 유효시간(h)

    예시:
        calculate_expires_at("싱싱") → 지금으로부터 48시간 뒤
        calculate_expires_at("임박") → 지금으로부터 24시간 뒤
    """
    hours = FRESHNESS_TTL[freshness_status]
    return datetime.utcnow() + timedelta(hours=hours)


def is_expired(expires_at: datetime) -> bool:
    """식재료 유효기간이 지났는지 확인합니다."""
    return datetime.utcnow() > expires_at
