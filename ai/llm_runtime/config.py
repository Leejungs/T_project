# ================================================================
# config.py
# ------------------------------------------------
# ⚙️ 역할:
# - .env 파일에서 환경 변수를 로드하고,
# - 프로젝트 전체에서 재사용할 수 있도록 Settings 객체를 제공
# ================================================================

from pydantic import BaseModel
from dotenv import load_dotenv
import os

# .env 파일 로드
THIS_DIR = os.path.dirname(__file__)
ENV_PATH = os.path.join(THIS_DIR, ".env")
load_dotenv(ENV_PATH)

class Settings(BaseModel):
    """
    OpenAI API 관련 설정을 담는 데이터 클래스
    """
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# 전역 설정 객체 (다른 모듈에서 import 해서 사용)
settings = Settings()
