import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

class Settings(BaseSettings):
    """
    Defensive configuration manager. 
    Loads from .env and guarantees required keys are present at startup.
    """
    gemini_api_key: SecretStr = Field(
        ..., 
        alias="GEMINI_API_KEY", 
        description="Google Gemini API Key for the LLM judge"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate the settings. 
# If GEMINI_API_KEY is missing from the .env, this will raise a ValidationError.
settings = Settings()

# Inject it back into os.environ so the google-genai SDK picks it up automatically
os.environ["GEMINI_API_KEY"] = settings.gemini_api_key.get_secret_value()