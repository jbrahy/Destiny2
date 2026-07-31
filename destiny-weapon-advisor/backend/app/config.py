from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    # Bungie (single shared app)
    bungie_api_key: str = ""
    bungie_client_id: str = ""
    bungie_client_secret: str = ""
    redirect_uri: str = "https://localhost:8443/callback"
    # Where the OAuth callback sends the browser after login. Defaults to the
    # backend's own origin (single-server mode, which serves the built frontend).
    # For Vite dev, set FRONTEND_URL=http://localhost:5173 in .env.
    frontend_url: str = "https://localhost:8443"

    # MySQL
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "advisor"
    db_password: str = ""
    db_name: str = "advisor"

    # Security
    token_enc_key: str = ""        # Fernet key (urlsafe base64, 32 bytes)
    session_secret: str = ""       # HMAC secret for cookie signing
    session_ttl_days: int = 30
    cookie_secure: bool = True

    # Behavior
    user_cache_ttl_seconds: int = 1800
    bungie_throttle_concurrency: int = 20
    # Score crafted weapons on the best roll they could be SHAPED into rather
    # than what is currently socketed. Off by default: turning it on changes
    # verdicts for every crafted weapon.
    score_crafted_potential: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
