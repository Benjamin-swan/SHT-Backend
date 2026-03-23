"""
한국인 빈출 식재료 초기 데이터 시딩 스크립트.

실행 방법 (SHT-Backend/ 루트에서):
    PYTHONPATH=backend python -m scripts.seed_ingredients
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlmodel import Session

from app.core.database import create_db_and_tables, engine
from app.services.seed import seed_frequent_ingredients

if __name__ == "__main__":
    print("=== 한국인 빈출 식재료 시딩 시작 ===")
    create_db_and_tables()
    with Session(engine) as session:
        seed_frequent_ingredients(session)
    print("=== 시딩 종료 ===")
