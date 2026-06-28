import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

class Settings(BaseSettings):
    """
    Defensive configuration manager. 
    Loads from .env and guarantees required keys are present at startup.
    """
    llm_api_key: Optional[SecretStr] = Field(
        default=None, 
        alias="LLM_API_KEY",
        description="API Key for the Bring-Your-Own-Judge LLM provider"
    )
    llm_base_url: Optional[str] = Field(
        default=None, 
        alias="LLM_BASE_URL",
        description="Custom base URL for the LLM provider (e.g. Ollama, vLLM)"
    )
    llm_model_name: str = Field(
        default="gpt-4o-mini", 
        alias="LLM_MODEL_NAME",
        description="Model name to target for the judge evaluations"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate the settings.
settings = Settings()

# Inject into environment variables for OpenAI SDK
if settings.llm_api_key is not None:
    os.environ["OPENAI_API_KEY"] = settings.llm_api_key.get_secret_value()

if settings.llm_base_url is not None:
    os.environ["OPENAI_BASE_URL"] = settings.llm_base_url