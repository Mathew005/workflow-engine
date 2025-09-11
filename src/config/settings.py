from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """Loads and validates all application settings from a .env file."""
    model_config = SettingsConfigDict(
        env_file='.env', 
        env_file_encoding='utf-8', 
        extra='ignore'
    )

    # The API key is now managed by the ApiKeyManager, so we only need the MONGO_URI here.
    mongo_uri: str = Field(..., alias='MONGO_URI')

# Create a single, importable instance of the settings
settings = Settings()