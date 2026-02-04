from typing import Optional, Any

import httpx


class FigmaClient:
    BASE_URL = "https://api.figma.com/v1"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.is_pat = access_token.startswith("figd_")

    def _headers(self) -> dict:
        if self.is_pat:
            return {
                "X-Figma-Token": self.access_token,
                "Content-Type": "application/json",
            }
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

    async def get_me(self) -> dict:
        return await self._request("GET", "/me")

    # === FILES ===

    async def get_file(
        self,
        file_key: str,
        depth: Optional[int] = None,
        node_id: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if depth is not None:
            params["depth"] = depth
        if node_id:
            params["node-id"] = node_id
        return await self._request("GET", f"/files/{file_key}", params=params or None)

    async def get_file_nodes(
        self,
        file_key: str,
        ids: list[str],
        depth: Optional[int] = None,
    ) -> dict:
        params: dict[str, Any] = {"ids": ",".join(ids)}
        if depth is not None:
            params["depth"] = depth
        return await self._request("GET", f"/files/{file_key}/nodes", params=params)

    async def get_file_meta(self, file_key: str) -> dict:
        return await self._request("GET", f"/files/{file_key}/meta")

    # === IMAGES ===

    async def get_images(
        self,
        file_key: str,
        ids: list[str],
        format: str = "png",
        scale: Optional[float] = None,
    ) -> dict:
        params: dict[str, Any] = {
            "ids": ",".join(ids),
            "format": format,
        }
        if scale is not None:
            params["scale"] = scale
        return await self._request("GET", f"/images/{file_key}", params=params)

    async def get_image_fills(self, file_key: str) -> dict:
        return await self._request("GET", f"/files/{file_key}/images")

    # === VERSIONS ===

    async def get_file_versions(self, file_key: str) -> dict:
        return await self._request("GET", f"/files/{file_key}/versions")

    # === COMMENTS ===

    async def get_comments(self, file_key: str) -> dict:
        return await self._request("GET", f"/files/{file_key}/comments")

    async def post_comment(
        self,
        file_key: str,
        message: str,
        node_id: Optional[str] = None,
    ) -> dict:
        json_data: dict[str, Any] = {"message": message}
        if node_id:
            json_data["client_meta"] = {"node_id": node_id}
        return await self._request("POST", f"/files/{file_key}/comments", json_data=json_data)

    async def delete_comment(self, file_key: str, comment_id: str) -> dict:
        return await self._request("DELETE", f"/files/{file_key}/comments/{comment_id}")

    # === PROJECTS ===

    async def get_team_projects(self, team_id: str) -> dict:
        return await self._request("GET", f"/teams/{team_id}/projects")

    async def get_project_files(self, project_id: str) -> dict:
        return await self._request("GET", f"/projects/{project_id}/files")

    # === COMPONENTS ===

    async def get_team_components(
        self,
        team_id: str,
        page_size: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if page_size is not None:
            params["page_size"] = page_size
        if cursor:
            params["after"] = cursor
        return await self._request("GET", f"/teams/{team_id}/components", params=params or None)

    async def get_file_components(self, file_key: str) -> dict:
        return await self._request("GET", f"/files/{file_key}/components")

    async def get_component(self, component_key: str) -> dict:
        return await self._request("GET", f"/components/{component_key}")

    # === STYLES ===

    async def get_team_styles(
        self,
        team_id: str,
        page_size: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if page_size is not None:
            params["page_size"] = page_size
        if cursor:
            params["after"] = cursor
        return await self._request("GET", f"/teams/{team_id}/styles", params=params or None)

    async def get_file_styles(self, file_key: str) -> dict:
        return await self._request("GET", f"/files/{file_key}/styles")

    async def get_style(self, style_key: str) -> dict:
        return await self._request("GET", f"/styles/{style_key}")
