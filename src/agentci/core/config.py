import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

class Settings(BaseSettings):
    """
    Defensive configuration manager. 
    Loads from .env and guarantees required keys are present at startup.
    """
    # Removed the alias and explicitly defined default=None to satisfy Pylance
    gemini_api_key: Optional[SecretStr] = Field(
        default=None, 
        description="Google Gemini API Key for the LLM judge"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate the settings. Pylance is now happy because the field has a default.
settings = Settings()

# But we still enforce our defensive validation manually!
if settings.gemini_api_key is None:
    raise ValueError("GEMINI_API_KEY environment variable is missing. Please check your .env file.")

# Inject it back into os.environ so the google-genai SDK picks it up automatically
os.environ["GEMINI_API_KEY"] = settings.gemini_api_key.get_secret_value()