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

    # === DIRECT MESSAGES (DM) ===
    async def list_dm_conversations(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> dict:
        """List all direct message conversations (1:1 DMs)"""
        params: dict[str, Any] = {"limit": limit, "types": "im"}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "conversations.list", params=params)

    async def list_group_dms(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> dict:
        """List all group direct messages (multi-person DMs)"""
        params: dict[str, Any] = {"limit": limit, "types": "mpim"}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "conversations.list", params=params)

    async def open_dm(self, user_id: str) -> dict:
        """Open/get a DM conversation with a user"""
        return await self._request(
            "POST",
            "conversations.open",
            json_data={"users": user_id},
        )

    async def open_group_dm(self, user_ids: list[str]) -> dict:
        """Open/get a group DM with multiple users"""
        return await self._request(
            "POST",
            "conversations.open",
            json_data={"users": ",".join(user_ids)},
        )

    async def get_dm_history(
        self,
        user_id: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> dict:
        """Get DM history with a specific user"""
        # First open/get the DM channel
        dm = await self.open_dm(user_id)
        channel_id = dm.get("channel", {}).get("id")
        if not channel_id:
            raise ValueError(f"Could not open DM with user {user_id}")
        return await self.get_channel_history(channel_id, limit, cursor)

    async def send_dm(
        self,
        user_id: str,
        text: str,
        thread_ts: Optional[str] = None,
    ) -> dict:
        """Send a direct message to a user"""
        dm = await self.open_dm(user_id)
        channel_id = dm.get("channel", {}).get("id")
        if not channel_id:
            raise ValueError(f"Could not open DM with user {user_id}")
        return await self.post_message(channel_id, text, thread_ts)

    async def get_user_by_email(self, email: str) -> dict:
        """Find a user by their email address"""
        return await self._request(
            "GET",
            "users.lookupByEmail",
            params={"email": email},
        )

    async def get_user_info(self, user_id: str) -> dict:
        """Get detailed info about a user"""
        return await self._request(
            "GET",
            "users.info",
            params={"user": user_id},
        )

    # === CANVAS ===
    async def create_canvas(
        self,
        title: str,
        document_content: Optional[dict] = None,
    ) -> dict:
        """Create a new canvas"""
        json_data: dict[str, Any] = {"title": title}
        if document_content:
            json_data["document_content"] = document_content
        return await self._request("POST", "canvases.create", json_data=json_data)

    async def edit_canvas(
        self,
        canvas_id: str,
        changes: list[dict],
    ) -> dict:
        """Edit canvas content.

        changes format:
        [{"operation": "insert_at_end", "document_content": {"type": "markdown", "markdown": "text"}}]
        """
        return await self._request(
            "POST",
            "canvases.edit",
            json_data={"canvas_id": canvas_id, "changes": changes},
        )

    async def delete_canvas(self, canvas_id: str) -> dict:
        """Delete a canvas"""
        return await self._request(
            "POST",
            "canvases.delete",
            json_data={"canvas_id": canvas_id},
        )

    async def list_canvas_access(self, canvas_id: str) -> dict:
        """List who has access to a canvas"""
        return await self._request(
            "POST",
            "canvases.access.list",
            json_data={"canvas_id": canvas_id},
        )

    async def lookup_canvas_sections(
        self,
        canvas_id: str,
        section_types: Optional[list[str]] = None,
        contains_text: Optional[str] = None,
    ) -> dict:
        """Find sections in a canvas by heading type or text content.

        section_types: e.g. ["h1", "h2", "any_header"]
        contains_text: text to search for within sections
        """
        criteria: dict[str, Any] = {}
        if section_types:
            criteria["section_types"] = section_types
        if contains_text:
            criteria["contains_text"] = contains_text
        return await self._request(
            "POST",
            "canvases.sections.lookup",
            json_data={"canvas_id": canvas_id, "criteria": criteria},
        )

    async def set_canvas_access(
        self,
        canvas_id: str,
        access_level: str = "read",
        channel_ids: Optional[list[str]] = None,
        user_ids: Optional[list[str]] = None,
    ) -> dict:
        """Set canvas access for users or channels.

        access_level: 'read' or 'write'
        """
        json_data: dict[str, Any] = {
            "canvas_id": canvas_id,
            "access_level": access_level,
        }
        if channel_ids:
            json_data["channel_ids"] = channel_ids
        if user_ids:
            json_data["user_ids"] = user_ids
        return await self._request("POST", "canvases.access.set", json_data=json_data)

    async def get_conversation_info(self, channel: str) -> dict:
        """Get info about a conversation (channel, DM, group)"""
        return await self._request(
            "GET",
            "conversations.info",
            params={"channel": channel},
        )

    async def search_all(
        self,
        query: str,
        count: int = 20,
        page: int = 1,
    ) -> dict:
        """Search messages across all conversations including DMs"""
        # Add modifiers for broader search
        return await self._request(
            "GET",
            "search.messages",
            params={"query": query, "count": count, "page": page},
        )
