import base64
from urllib.parse import urlencode

import httpx

from app.config.store import get_integration_credentials


FIGMA_AUTH_URL = "https://www.figma.com/oauth"
FIGMA_TOKEN_URL = "https://api.figma.com/v1/oauth/token"
FIGMA_REFRESH_URL = "https://api.figma.com/v1/oauth/refresh"

FIGMA_SCOPES = [
    "file_content:read",
    "file_metadata:read",
    "file_comments:write",
    "file_dev_resources:read",
    "current_user:read",
]


def get_oauth_start_url(state: str, redirect_uri: str) -> str:
    client_id, _ = get_integration_credentials("figma")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(FIGMA_SCOPES),
        "state": state,
    }
    return f"{FIGMA_AUTH_URL}?{urlencode(params)}"


def _basic_auth_header() -> str:
    client_id, client_secret = get_integration_credentials("figma")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {credentials}"


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = get_integration_credentials("figma")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            FIGMA_TOKEN_URL,
            headers={"Authorization": _basic_auth_header()},
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "access_token" not in data:
            raise ValueError(f"Figma OAuth error: {data.get('error', 'no access_token')}")

        return data


async def refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret = get_integration_credentials("figma")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            FIGMA_REFRESH_URL,
            headers={"Authorization": _basic_auth_header()},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "access_token" not in data:
            raise ValueError(f"Figma token refresh error: {data.get('error', 'no access_token')}")

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in"),
        }
