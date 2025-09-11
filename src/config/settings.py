from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """Loads and validates all application settings from a .env file."""
    model_config = SettingsConfigDict(
        env_file='.env', 
        env_file_encoding='utf-8', 
        extra='ignore'
    )

    mongo_uri: str = Field(..., alias='MONGO_URI')

settings = Settings()