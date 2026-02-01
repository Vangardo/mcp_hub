from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None


class BaseIntegration(ABC):
    name: str
    display_name: str
    description: str
    auth_type: str = "oauth2"

    @abstractmethod
    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        pass

    @abstractmethod
    async def handle_oauth_callback(
        self, code: str, redirect_uri: str
    ) -> dict:
        pass

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> dict:
        pass

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        pass

    @abstractmethod
    async def execute_tool(
        self, tool_name: str, args: dict, access_token: str, meta: Optional[dict] = None
    ) -> ToolResult:
        pass

    def is_configured(self) -> bool:
        return True
