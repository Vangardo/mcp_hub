from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Application
    app_name: str = "MCP Hub"
    debug: bool = False
    base_url: str = "http://localhost:8000"

    # Database
    database_path: str = "data/app.db"

    # Admin credentials (created on first start)
    admin_email: str = "admin@example.com"
    admin_password: str = "changeme"

    # JWT
    jwt_secret: str = Field(default="change-this-secret-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 20 * 24 * 60  # 20 days
    refresh_token_expire_days: int = 30

    # Token encryption
    tokens_encryption_key: str = Field(default="change-this-key-in-production")

    # Teamwork OAuth
    teamwork_client_id: Optional[str] = None
    teamwork_client_secret: Optional[str] = None

    # Slack OAuth
    slack_client_id: Optional[str] = None
    slack_client_secret: Optional[str] = None

    # Telegram (MTProto)
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    @property
    def oauth_redirect_base(self) -> str:
        return self.base_url.rstrip("/")


settings = Settings()
