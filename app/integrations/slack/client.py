from typing import Optional, Any
import httpx


class SlackClient:
    BASE_URL = "https://slack.com/api"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        url = f"{self.BASE_URL}/{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                json=json_data,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                raise ValueError(f"Slack API error: {data.get('error')}")

            return data

    async def list_channels(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
        types: str = "public_channel,private_channel",
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "types": types}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "conversations.list", params=params)

    async def list_users(
        self, limit: int = 100, cursor: Optional[str] = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "users.list", params=params)

    async def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
    ) -> dict:
        json_data: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            json_data["thread_ts"] = thread_ts
        return await self._request("POST", "chat.postMessage", json_data=json_data)

    async def search_messages(
        self,
        query: str,
        count: int = 20,
        page: int = 1,
    ) -> dict:
        return await self._request(
            "GET",
            "search.messages",
            params={"query": query, "count": count, "page": page},
        )

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {"channel": channel, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "conversations.history", params=params)
