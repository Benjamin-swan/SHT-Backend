from pathlib import Path

from pydantic_settings import BaseSettings

# config.py 위치: backend/app/core/config.py
# .env 위치:      SHT-Backend/.env  (4단계 위)
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """
    환경변수를 .env 파일에서 읽어오는 설정 클래스.
    pydantic-settings가 자동으로 .env 파일을 파싱해줍니다.
    """
    database_url: str
    gemini_api_key: str

    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8"}


# 앱 전역에서 import해서 사용하는 싱글턴 설정 객체
settings = Settings()
