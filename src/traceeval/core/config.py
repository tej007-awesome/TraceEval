import os
from typing import Optional

from openai import AsyncOpenAI
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Defensive configuration manager.

    Loads from .env and guarantees required keys are present at startup.
    """

    llm_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="LLM_API_KEY",
        description="API Key for the Bring-Your-Own-Judge LLM provider",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        alias="LLM_BASE_URL",
        description="Custom base URL for the LLM provider (e.g. Ollama, vLLM)",
    )
    llm_model_name: str = Field(
        default="gpt-4o-mini",
        alias="LLM_MODEL_NAME",
        description="Model name to target for the judge evaluations",
    )
    judge_temperature: Optional[float] = Field(
        default=0.0,
        alias="LLM_JUDGE_TEMPERATURE",
        description="Temperature sent on judge calls. Set to null (e.g. programmatically, "
        "not via .env) to omit the parameter entirely - some models (e.g. reasoning-effort-"
        "tuned models) reject or ignore it. Defaults to 0.0, preserving prior behavior.",
    )
    judge_reasoning_effort: Optional[str] = Field(
        default=None,
        alias="LLM_JUDGE_REASONING_EFFORT",
        description="Reasoning effort sent on judge calls via extra_body, for models that "
        "support it (e.g. 'low'/'minimal'/'none' on reasoning-effort-tuned models). None "
        "omits the parameter entirely - the default, since most judge models don't use it.",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Instantiate the settings.
settings = Settings()


def get_judge_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client configured explicitly from settings or environment."""
    api_key = (
        settings.llm_api_key.get_secret_value()
        if settings.llm_api_key
        else os.environ.get("OPENAI_API_KEY")
    )
    base_url = settings.llm_base_url

    if not api_key and base_url:
        api_key = "not-needed"

    return AsyncOpenAI(api_key=api_key, base_url=base_url)