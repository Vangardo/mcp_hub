import json
import uuid
from typing import Optional, Any

import httpx


class MCPProxyClient:
    """Communicates with an external MCP server using JSON-RPC over HTTP."""

    def __init__(
        self,
        server_url: str,
        auth_type: str = "none",
        auth_secret: Optional[str] = None,
        auth_header_name: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.auth_type = auth_type
        self.auth_secret = auth_secret
        self.auth_header_name = auth_header_name
        self.timeout = timeout

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_type == "bearer" and self.auth_secret:
            headers["Authorization"] = f"Bearer {self.auth_secret}"
        elif self.auth_type == "custom_header" and self.auth_header_name and self.auth_secret:
            headers[self.auth_header_name] = self.auth_secret
        return headers

    async def _send_request(self, method: str, params: Optional[dict] = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.server_url,
                json=payload,
                headers=self._build_headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def initialize(self) -> dict:
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-hub-proxy", "version": "1.0.0"},
        })
        return result.get("result", {})

    async def list_tools(self) -> list[dict]:
        result = await self._send_request("tools/list")
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        if "error" in result and result["error"]:
            return {
                "content": [{"type": "text", "text": f"Error: {result['error'].get('message', 'Unknown error')}"}],
                "isError": True,
            }
        return result.get("result", {})

    async def health_check(self) -> bool:
        try:
            await self.initialize()
            return True
        except Exception:
            return False
