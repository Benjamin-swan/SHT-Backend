from sqlmodel import Session, select

from app.models.ingredient import Ingredient

FREQUENT_INGREDIENTS = [
    {"name": "마늘", "category": "frequent"},
    {"name": "대파", "category": "frequent"},
    {"name": "양파", "category": "frequent"},
    {"name": "달걀", "category": "frequent"},
    {"name": "김치", "category": "frequent"},
    {"name": "두부", "category": "frequent"},
    {"name": "청양고추", "category": "frequent"},
    {"name": "감자", "category": "frequent"},
    {"name": "참치캔", "category": "frequent"},
    {"name": "스팸", "category": "frequent"},
]


def seed_frequent_ingredients(session: Session) -> None:
    """
    빈출 식재료 10개를 DB에 삽입합니다.
    이미 같은 이름의 식재료가 존재하면 건너뜁니다 (idempotent).
    """
    inserted_count = 0

    for data in FREQUENT_INGREDIENTS:
        existing = session.exec(
            select(Ingredient).where(Ingredient.name == data["name"])
        ).first()

        if existing:
            continue

        session.add(Ingredient(**data))
        inserted_count += 1

    session.commit()

    if inserted_count:
        print(f"[seed] 빈출 식재료 {inserted_count}개 삽입 완료")
