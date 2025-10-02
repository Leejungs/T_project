from pydantic import BaseModel, Field, validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Union, Annotated, Optional

# --- Provider-specific settings ---

class OpenAISettings(BaseModel):
    provider: Literal["openai"] = "openai"
    api_key: str
    model_name: str

class GoogleSettings(BaseModel):
    provider: Literal["google"] = "google"
    api_key: str
    model_name: str

# --- Discriminated Union for LLM settings ---

LLMSettings = Annotated[Union[OpenAISettings, GoogleSettings], Field(discriminator="provider")]

# --- Main Settings class ---

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Settings (loaded directly from env vars)
    LLM_PROVIDER: Literal["openai", "google"] = "openai"
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    LLM_MODEL_NAME: str = "gpt-4o-mini"

    # Internal LLM object (constructed after validation)
    llm: Optional[LLMSettings] = None # Will be set by model_validator

    # Embedding Model
    EMBEDDING_MODEL_NAME: str = "jhgan/ko-sroberta-multitask"

    # Vector DB Path
    VECTOR_DB_PATH: str = "./data/chroma_db"


    # Evaluation Settings
    EVAL_LLM_MODEL_NAME: str = "gpt-4-turbo"
    EVAL_DATASET_PATH: str = "./data/evaluation/dataset.json"

    @model_validator(mode='after')
    def create_llm_settings(self):
        if self.LLM_PROVIDER == "openai":
            if not self.OPENAI_API_KEY:
                raise ValueError("LLM_PROVIDER is 'openai', but OPENAI_API_KEY is not set.")
            self.llm = OpenAISettings(api_key=self.OPENAI_API_KEY, model_name=self.LLM_MODEL_NAME)
        elif self.LLM_PROVIDER == "google":
            if not self.GOOGLE_API_KEY:
                raise ValueError("LLM_PROVIDER is 'google', but GOOGLE_API_KEY is not set.")
            self.llm = GoogleSettings(api_key=self.GOOGLE_API_KEY, model_name=self.LLM_MODEL_NAME)
        return self

# 설정 객체 생성
settings = Settings()