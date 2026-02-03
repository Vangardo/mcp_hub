from typing import Optional, Tuple
from urllib.parse import urlparse

from app.db import get_db
from app.settings import settings


PUBLIC_BASE_URL_KEY = "public_base_url"
PUBLIC_HOST_KEY = "public_host"
TEAMWORK_CLIENT_ID_KEY = "teamwork_client_id"
TEAMWORK_CLIENT_SECRET_KEY = "teamwork_client_secret"
SLACK_CLIENT_ID_KEY = "slack_client_id"
SLACK_CLIENT_SECRET_KEY = "slack_client_secret"
MIRO_CLIENT_ID_KEY = "miro_client_id"
MIRO_CLIENT_SECRET_KEY = "miro_client_secret"
TELEGRAM_API_ID_KEY = "telegram_api_id"
TELEGRAM_API_HASH_KEY = "telegram_api_hash"


def get_setting(conn, key: str) -> Optional[str]:
    cursor = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (key,),
    )
    row = cursor.fetchone()
    return row["value"] if row else None


def set_setting(conn, key: str, value: Optional[str]) -> None:
    value = value.strip() if isinstance(value, str) else value
    if not value:
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        conn.commit()
        return

    conn.execute(
        """INSERT INTO app_settings (key, value)
           VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET
             value = excluded.value,
             updated_at = datetime('now')""",
        (key, value),
    )
    conn.commit()


def get_setting_value(key: str) -> Optional[str]:
    with get_db() as conn:
        return get_setting(conn, key)


def get_public_base_url() -> str:
    public_base_url = get_setting_value(PUBLIC_BASE_URL_KEY)
    if public_base_url:
        return public_base_url.rstrip("/")

    public_host = get_setting_value(PUBLIC_HOST_KEY)
    if public_host:
        if public_host.startswith("http://") or public_host.startswith("https://"):
            return public_host.rstrip("/")
        parsed = urlparse(settings.base_url)
        scheme = parsed.scheme or "http"
        return f"{scheme}://{public_host}".rstrip("/")

    return settings.base_url.rstrip("/")


def get_integration_credentials(provider: str) -> Tuple[Optional[str], Optional[str]]:
    provider = provider.lower()
    if provider == "teamwork":
        return (
            get_setting_value(TEAMWORK_CLIENT_ID_KEY) or settings.teamwork_client_id,
            get_setting_value(TEAMWORK_CLIENT_SECRET_KEY) or settings.teamwork_client_secret,
        )
    if provider == "slack":
        return (
            get_setting_value(SLACK_CLIENT_ID_KEY) or settings.slack_client_id,
            get_setting_value(SLACK_CLIENT_SECRET_KEY) or settings.slack_client_secret,
        )
    if provider == "miro":
        return (
            get_setting_value(MIRO_CLIENT_ID_KEY) or settings.miro_client_id,
            get_setting_value(MIRO_CLIENT_SECRET_KEY) or settings.miro_client_secret,
        )
    return (None, None)


def get_telegram_api_credentials() -> Tuple[Optional[int], Optional[str]]:
    api_id_raw = get_setting_value(TELEGRAM_API_ID_KEY) or settings.telegram_api_id
    api_hash = get_setting_value(TELEGRAM_API_HASH_KEY) or settings.telegram_api_hash
    api_id = None
    if api_id_raw:
        try:
            api_id = int(api_id_raw)
        except ValueError:
            api_id = None
    return api_id, api_hash
