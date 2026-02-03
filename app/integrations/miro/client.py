from typing import Optional, Any

import httpx


class MiroClient:
    BASE_URL = "https://api.miro.com/v2"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        url = f"{self.BASE_URL}{endpoint}"
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

            if response.status_code == 204 or not response.content:
                return {"success": True, "status_code": response.status_code}

            return response.json()

    # === USER ===

    async def get_current_user(self) -> dict:
        """Get current authenticated user info"""
        url = "https://api.miro.com/v1/oauth-token"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._headers(), timeout=30.0)
            response.raise_for_status()
            return response.json()

    # === BOARDS ===

    async def list_boards(
        self,
        query: Optional[str] = None,
        team_id: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if team_id:
            params["team_id"] = team_id
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/boards", params=params)

    async def get_board(self, board_id: str) -> dict:
        return await self._request("GET", f"/boards/{board_id}")

    async def create_board(
        self,
        name: str,
        description: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> dict:
        json_data: dict[str, Any] = {"name": name}
        if description:
            json_data["description"] = description
        if team_id:
            json_data["teamId"] = team_id
        return await self._request("POST", "/boards", json_data=json_data)

    async def update_board(
        self,
        board_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        json_data: dict[str, Any] = {}
        if name:
            json_data["name"] = name
        if description is not None:
            json_data["description"] = description
        return await self._request("PATCH", f"/boards/{board_id}", json_data=json_data)

    async def delete_board(self, board_id: str) -> dict:
        return await self._request("DELETE", f"/boards/{board_id}")

    async def copy_board(self, board_id: str, title: Optional[str] = None) -> dict:
        json_data: dict[str, Any] = {}
        if title:
            json_data["title"] = title
        return await self._request("POST", f"/boards/{board_id}/copy", json_data=json_data)

    # === BOARD MEMBERS ===

    async def list_board_members(self, board_id: str) -> dict:
        return await self._request("GET", f"/boards/{board_id}/members")

    async def share_board(
        self,
        board_id: str,
        emails: list[str],
        role: str = "commenter",
    ) -> dict:
        json_data = {"emails": emails, "role": role}
        return await self._request("POST", f"/boards/{board_id}/members", json_data=json_data)

    # === ITEMS (generic) ===

    async def list_items(
        self,
        board_id: str,
        item_type: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if item_type:
            params["type"] = item_type
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/boards/{board_id}/items", params=params)

    async def get_item(self, board_id: str, item_id: str) -> dict:
        return await self._request("GET", f"/boards/{board_id}/items/{item_id}")

    async def delete_item(self, board_id: str, item_id: str) -> dict:
        return await self._request("DELETE", f"/boards/{board_id}/items/{item_id}")

    # === STICKY NOTES ===

    async def create_sticky_note(
        self,
        board_id: str,
        content: str,
        color: Optional[str] = None,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
    ) -> dict:
        data: dict[str, Any] = {"content": content}
        if color:
            data["shape"] = "square"
            data["style"] = {"fillColor": color}
        json_data: dict[str, Any] = {"data": data}
        if position_x is not None and position_y is not None:
            json_data["position"] = {"x": position_x, "y": position_y}
        return await self._request("POST", f"/boards/{board_id}/sticky_notes", json_data=json_data)

    async def update_sticky_note(
        self,
        board_id: str,
        item_id: str,
        content: Optional[str] = None,
        color: Optional[str] = None,
    ) -> dict:
        data: dict[str, Any] = {}
        if content is not None:
            data["content"] = content
        style = {}
        if color:
            style["fillColor"] = color
        json_data: dict[str, Any] = {}
        if data:
            json_data["data"] = data
        if style:
            json_data["style"] = style
        return await self._request("PATCH", f"/boards/{board_id}/sticky_notes/{item_id}", json_data=json_data)

    # === TEXT ===

    async def create_text(
        self,
        board_id: str,
        content: str,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
        font_size: Optional[int] = None,
    ) -> dict:
        data: dict[str, Any] = {"content": content}
        if font_size:
            data["style"] = {"fontSize": str(font_size)}
        json_data: dict[str, Any] = {"data": data}
        if position_x is not None and position_y is not None:
            json_data["position"] = {"x": position_x, "y": position_y}
        return await self._request("POST", f"/boards/{board_id}/texts", json_data=json_data)

    # === SHAPES ===

    async def create_shape(
        self,
        board_id: str,
        content: Optional[str] = None,
        shape: str = "rectangle",
        color: Optional[str] = None,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> dict:
        data: dict[str, Any] = {"shape": shape}
        if content:
            data["content"] = content
        style: dict[str, Any] = {}
        if color:
            style["fillColor"] = color
        json_data: dict[str, Any] = {"data": data}
        if style:
            json_data["style"] = style
        if position_x is not None and position_y is not None:
            json_data["position"] = {"x": position_x, "y": position_y}
        geometry: dict[str, Any] = {}
        if width:
            geometry["width"] = width
        if height:
            geometry["height"] = height
        if geometry:
            json_data["geometry"] = geometry
        return await self._request("POST", f"/boards/{board_id}/shapes", json_data=json_data)

    # === CARDS ===

    async def create_card(
        self,
        board_id: str,
        title: str,
        description: Optional[str] = None,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
    ) -> dict:
        data: dict[str, Any] = {"title": title}
        if description:
            data["description"] = description
        json_data: dict[str, Any] = {"data": data}
        if position_x is not None and position_y is not None:
            json_data["position"] = {"x": position_x, "y": position_y}
        return await self._request("POST", f"/boards/{board_id}/cards", json_data=json_data)

    # === CONNECTORS ===

    async def create_connector(
        self,
        board_id: str,
        start_item_id: str,
        end_item_id: str,
        style: Optional[str] = None,
    ) -> dict:
        json_data: dict[str, Any] = {
            "startItem": {"id": start_item_id},
            "endItem": {"id": end_item_id},
        }
        if style:
            json_data["style"] = {"strokeStyle": style}
        return await self._request("POST", f"/boards/{board_id}/connectors", json_data=json_data)
