from typing import Optional

from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.telegram.client import (
    get_client,
    list_dialogs,
    send_message,
    search_messages,
    message_history,
)


TELEGRAM_TOOLS = [
    ToolDefinition(
        name="telegram.users.me",
        description="Get the current authenticated Telegram user (id, username, phone).",
        input_schema={"type": "object", "properties": {}},
    ),
    ToolDefinition(
        name="telegram.dialogs.list",
        description="List Telegram dialogs for the authenticated user",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max dialogs to return", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="telegram.messages.send",
        description="Send a message to a Telegram user or chat",
        input_schema={
            "type": "object",
            "properties": {
                "peer": {"type": "string", "description": "Username, phone, or chat ID"},
                "text": {"type": "string", "description": "Message text"},
            },
            "required": ["peer", "text"],
        },
    ),
    ToolDefinition(
        name="telegram.messages.search",
        description="Search messages in Telegram",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "peer": {"type": "string", "description": "Optional peer to search in"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="telegram.messages.history",
        description="Fetch recent message history for a peer",
        input_schema={
            "type": "object",
            "properties": {
                "peer": {"type": "string", "description": "Username, phone, or chat ID"},
                "limit": {"type": "integer", "description": "Max messages", "default": 20},
                "before_id": {"type": "integer", "description": "Return messages before this ID"},
            },
            "required": ["peer"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    session_string: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    try:
        client = await get_client(session_string)

        if tool_name == "telegram.users.me":
            if meta and meta.get("telegram_user_id"):
                return ToolResult(success=True, data=meta)
            me = await client.get_me()
            return ToolResult(
                success=True,
                data={
                    "telegram_user_id": getattr(me, "id", None),
                    "username": getattr(me, "username", None),
                    "phone": getattr(me, "phone", None),
                },
            )

        if tool_name == "telegram.dialogs.list":
            result = await list_dialogs(client, limit=args.get("limit", 50))
            return ToolResult(success=True, data=result)

        if tool_name == "telegram.messages.send":
            result = await send_message(
                client,
                peer=args["peer"],
                text=args["text"],
            )
            return ToolResult(success=True, data=result)

        if tool_name == "telegram.messages.search":
            result = await search_messages(
                client,
                peer=args.get("peer"),
                query=args["query"],
                limit=args.get("limit", 20),
            )
            return ToolResult(success=True, data=result)

        if tool_name == "telegram.messages.history":
            result = await message_history(
                client,
                peer=args["peer"],
                limit=args.get("limit", 20),
                before_id=args.get("before_id"),
            )
            return ToolResult(success=True, data=result)

        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
    except Exception as e:
        return ToolResult(success=False, error=str(e))
