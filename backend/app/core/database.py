from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

# SQLAlchemy 엔진 생성. echo=True 는 실행되는 SQL을 콘솔에 출력 (개발 시 디버깅용)
engine = create_engine(settings.database_url, echo=True)


def create_db_and_tables() -> None:
    """
    앱 시작 시 호출되어 모든 SQLModel 테이블을 DB에 생성합니다.
    이미 존재하는 테이블은 건드리지 않습니다 (idempotent).
    """
    SQLModel.metadata.create_all(engine)


def get_session():
    """
    FastAPI 의존성 주입(Depends)에 사용되는 DB 세션 제공자.
    요청마다 새 세션을 열고, 요청이 끝나면 자동으로 닫습니다.
    """
    with Session(engine) as session:
        yield session
