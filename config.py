from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_core import ValidationError
import pydantic_core
from functools import lru_cache

class Settings(BaseSettings):
    # If .env is missing (Production), it silently ignores this and looks at System Env Vars
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 1. Define the Keys you need
    DATABASE_URL: str
    SUPABASE_DB_URL: str
    SUPABASE_DB_PASSWORD: str

    # Authentication
    SUPABASE_JWT_SECRET: str

    # 3. The Admin Tool (Optional - for Storage/Auth management)
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_PUBLISHABLE_API_KEY: str
    
    # 2. Set Defaults (Optional)
    DEBUG: bool = False
    ENVIRONMENT: str = "production"


# Use lru_cache so we only read the file once per startup
@lru_cache
def get_settings():
    try:
        return Settings()
    except pydantic_core._pydantic_core.ValidationError:
        raise NotImplementedError("Could not get configuration settings, check .env file.")

# Usage:
# from config import get_settings
# settings = get_settings()
# print(settings.DATABASE_URL)