from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    bungie_api_key: str = ""
    bungie_client_id: str = ""
    bungie_client_secret: str = ""
    redirect_uri: str = "https://localhost:8443/callback"
    # Where the OAuth callback sends the browser after login. Defaults to the
    # backend's own origin (single-server mode, which serves the built frontend).
    # For Vite dev, set FRONTEND_URL=http://localhost:5173 in .env.
    frontend_url: str = "https://localhost:8443"
    db_path: str = "weapon_advisor.sqlite"


@lru_cache
def get_settings() -> Settings:
    return Settings()
