"""Application settings loaded from environment variables."""
from functools import lru_cache
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Multi-Agent Email Assistant")
    database_url: str = Field(default="sqlite:///email_agents.db")

    azure_ai_project_endpoint: str | None = Field(default=None, alias="AZURE_AI_PROJECT_ENDPOINT")
    azure_ai_api_key: str | None = Field(default=None, alias="AZURE_AI_API_KEY")
    azure_ai_model_deployment_name: str | None = Field(default=None, alias="AZURE_AI_MODEL_DEPLOYMENT_NAME")

    use_fake_model: bool = Field(default=False, alias="USE_FAKE_MODEL")

    knowledge_base_path: str = Field(default="data/knowledge")


class UIStatus(BaseModel):
    """Simple descriptor exposed to the frontend."""

    provider_label: str
    is_demo_mode: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
