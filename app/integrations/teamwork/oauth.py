from urllib.parse import urlencode
import httpx

from app.config.store import get_integration_credentials


TEAMWORK_AUTH_URL = "https://www.teamwork.com/launchpad/login"
TEAMWORK_TOKEN_URL = "https://www.teamwork.com/launchpad/v1/token.json"


def get_oauth_start_url(state: str, redirect_uri: str) -> str:
    client_id, _ = get_integration_credentials("teamwork")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{TEAMWORK_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = get_integration_credentials("teamwork")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TEAMWORK_TOKEN_URL,
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

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
            "installation": data.get("installation", {}),
        }


async def refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret = get_integration_credentials("teamwork")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TEAMWORK_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        data = response.json()

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in"),
        }
