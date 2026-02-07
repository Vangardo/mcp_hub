import json
import uuid
from typing import Optional, Any

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from fastapi.security import HTTPAuthorizationCredentials
from app.auth.deps import security
from app.auth.token_utils import get_user_from_token
from app.db import get_db
from app.integrations.registry import integration_registry
from app.mcp_gateway.routing import execute_tool, parse_tool_name
from app.mcp_gateway.audit import log_tool_call
from app.integrations.connections import list_connected_providers
from app.integrations.registry import integration_registry


mcp_router = APIRouter(tags=["mcp"])


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    method: str
    params: Optional[dict] = None


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    result: Optional[Any] = None
    error: Optional[dict] = None


def safe_audit_log(
    user_id: int,
    provider: Optional[str],
    action: str,
    request_data: Optional[dict],
    response_data: Optional[Any],
    status: str,
    tool_name: Optional[str] = None,
    error_text: Optional[str] = None,
):
    try:
        log_tool_call(
            user_id=user_id,
            provider=provider,
            action=action,
            tool_name=tool_name,
            request_data=request_data,
            response_data=response_data,
            status=status,
            error_text=error_text,
        )
    except Exception:
        pass


def get_user_connected_providers(user_id: int) -> list[str]:
    with get_db() as conn:
        return list_connected_providers(conn, user_id)


def normalize_tool_name_format(value: Optional[str]) -> str:
    if not value:
        return "dot"
    value = value.strip().lower()
    if value in {"flat", "underscore", "underscored", "snake"}:
        return "flat"
    return "dot"


def is_claude_user_agent(user_agent: str) -> bool:
    if not user_agent:
        return False
    ua = user_agent.lower()
    return "claude" in ua or "anthropic" in ua


def resolve_tool_name_format(request: Request) -> str:
    header_format = request.headers.get("X-MCP-Tool-Format")
    if header_format:
        return normalize_tool_name_format(header_format)
    if is_claude_user_agent(request.headers.get("User-Agent", "")):
        return "flat"
    return "dot"


def format_tool_name(name: str, name_format: str) -> str:
    if name_format == "flat":
        return name.replace(".", "__")
    return name


def unformat_tool_name(name: str, name_format: str) -> str:
    if name_format == "flat" and "." not in name:
        return name.replace("__", ".")
    return name


HUB_TOOLS = [
    {
        "name": "hub.integrations.list",
        "description": "Step 1/3: List integrations connected for the current user. Use this first to discover which providers are available. Set include_tools=false to keep the response small.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_tools": {"type": "boolean", "default": False},
                "connected_only": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "hub.tools.list",
        "description": "Step 2/3: List tools for a specific provider (e.g., teamwork, slack, telegram, miro). Call this after hub.integrations.list to get provider-specific commands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Integration name (e.g., teamwork, slack, telegram, miro)"},
            },
            "required": ["provider"],
        },
    },
    {
        "name": "hub.tools.call",
        "description": "Step 3/3: Call a provider tool via the hub. Use tool_name from hub.tools.list and pass arguments as-is. This avoids loading all tools into context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Integration name (e.g., teamwork, slack, telegram, miro)"},
                "tool_name": {"type": "string", "description": "Tool name to call (e.g., teamwork.tasks.create)"},
                "arguments": {"type": "object", "description": "Arguments for the tool"},
            },
            "required": ["provider", "tool_name"],
        },
    },
]


def get_available_tools(
    user_id: int,
    provider_filter: Optional[str] = None,
    name_format: str = "dot",
) -> list[dict]:
    tools = []

    for tool in HUB_TOOLS:
        tools.append(
            {
                "name": format_tool_name(tool["name"], name_format),
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
            }
        )

    return tools


async def handle_initialize(
    user: dict,
    params: Optional[dict],
    provider_filter: Optional[str] = None,
    name_format: str = "dot",
) -> dict:
    safe_audit_log(
        user_id=user["id"],
        provider=provider_filter,
        action="mcp.initialize",
        request_data=params,
        response_data=None,
        status="ok",
    )
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {
            "name": "mcp-hub",
            "version": "1.0.0",
        },
    }


async def handle_list_tools(
    user: dict,
    params: Optional[dict],
    provider_filter: Optional[str] = None,
    name_format: str = "dot",
) -> dict:
    tools = get_available_tools(user["id"], provider_filter, name_format=name_format)
    safe_audit_log(
        user_id=user["id"],
        provider=provider_filter,
        action="mcp.tools.list",
        request_data=params,
        response_data={"count": len(tools)},
        status="ok",
    )
    return {"tools": tools}

async def handle_call_tool(
    user: dict,
    params: Optional[dict],
    provider_filter: Optional[str] = None,
    name_format: str = "dot",
) -> dict:
    if not params:
        raise ValueError("Missing params")

    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        raise ValueError("Missing tool name")

    tool_name = unformat_tool_name(tool_name, name_format)

    if tool_name == "hub.integrations.list":
        connected_providers = set(get_user_connected_providers(user["id"]))
        connected_providers.add("memory")
        include_tools = False
        connected_only = True
        if arguments:
            include_tools = arguments.get("include_tools", False)
            connected_only = arguments.get("connected_only", True)

        integrations = []
        for integration in integration_registry.list_all():
            connected = integration.name in connected_providers
            if connected_only and not connected:
                continue
            item = {
                "name": integration.name,
                "display_name": integration.display_name,
                "description": integration.description,
                "auth_type": getattr(integration, "auth_type", "oauth2"),
                "is_configured": integration.is_configured(),
                "is_connected": connected,
            }
            if include_tools:
                item["tools"] = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in integration.get_tools()
                ]
            integrations.append(item)

        safe_audit_log(
            user_id=user["id"],
            provider="hub",
            action="hub.integrations.list",
            request_data=arguments,
            response_data={"count": len(integrations)},
            status="ok",
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"integrations": integrations}, default=str, ensure_ascii=False),
                }
            ],
        }

    if tool_name == "hub.tools.list":
        provider = (arguments or {}).get("provider")
        if not provider:
            raise ValueError("Missing provider")
        if provider_filter and provider != provider_filter:
            raise ValueError(f"Provider not allowed for provider filter: {provider_filter}")

        connected_providers = set(get_user_connected_providers(user["id"]))
        connected_providers.add("memory")
        integration = integration_registry.get(provider)
        if not integration:
            raise ValueError(f"Unknown provider: {provider}")
        if provider not in connected_providers:
            raise ValueError(f"Provider not connected: {provider}")
        if not integration.is_configured():
            raise ValueError(f"Provider not configured: {provider}")

        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in integration.get_tools()
        ]

        safe_audit_log(
            user_id=user["id"],
            provider="hub",
            action="hub.tools.list",
            request_data=arguments,
            response_data={"count": len(tools), "provider": provider},
            status="ok",
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"provider": provider, "tools": tools}, default=str, ensure_ascii=False),
                }
            ],
        }

    if tool_name == "hub.tools.call":
        provider = (arguments or {}).get("provider")
        raw_tool_name = (arguments or {}).get("tool_name")
        nested_arguments = (arguments or {}).get("arguments", {})
        if not provider or not raw_tool_name:
            raise ValueError("Missing provider or tool_name")
        if provider_filter and provider != provider_filter:
            raise ValueError(f"Provider not allowed for provider filter: {provider_filter}")

        connected_providers = set(get_user_connected_providers(user["id"]))
        connected_providers.add("memory")
        integration = integration_registry.get(provider)
        if not integration:
            raise ValueError(f"Unknown provider: {provider}")
        if provider not in connected_providers:
            raise ValueError(f"Provider not connected: {provider}")
        if not integration.is_configured():
            raise ValueError(f"Provider not configured: {provider}")

        tool_name = raw_tool_name.replace("__", ".")
        if not tool_name.startswith(f"{provider}."):
            raise ValueError("tool_name must be prefixed with provider (e.g., teamwork.tasks.list)")

        result = await execute_tool(user["id"], tool_name, nested_arguments)

        safe_audit_log(
            user_id=user["id"],
            provider=provider,
            action="hub.tools.call",
            tool_name=tool_name,
            request_data={"tool_name": tool_name, "arguments": nested_arguments},
            response_data=result.data if result.success else None,
            status="ok" if result.success else "error",
            error_text=result.error if not result.success else None,
        )

        if result.success:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result.data, default=str, ensure_ascii=False),
                    }
                ],
            }
        return {"content": [{"type": "text", "text": f"Error: {result.error}"}]}

    if provider_filter:
        if not tool_name.startswith(f"{provider_filter}."):
            raise ValueError(f"Tool not allowed for provider filter: {provider_filter}")

    provider, _ = parse_tool_name(tool_name)

    result = await execute_tool(user["id"], tool_name, arguments)

    safe_audit_log(
        user_id=user["id"],
        provider=provider,
        action=tool_name,
        tool_name=tool_name,
        request_data=arguments,
        response_data=result.data if result.success else None,
        status="ok" if result.success else "error",
        error_text=result.error if not result.success else None,
    )

    if result.success:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result.data, default=str, ensure_ascii=False),
                }
            ],
        }
    else:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: {result.error}",
                }
            ],
            "isError": True,
        }


METHOD_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_list_tools,
    "tools/call": handle_call_tool,
}


async def process_mcp_request(
    user: dict,
    request: MCPRequest,
    provider_filter: Optional[str] = None,
    name_format: str = "dot",
) -> MCPResponse:
    handler = METHOD_HANDLERS.get(request.method)

    if not handler:
        return MCPResponse(
            id=request.id,
            error={
                "code": -32601,
                "message": f"Method not found: {request.method}",
            },
        )

    try:
        result = await handler(user, request.params, provider_filter, name_format)
        return MCPResponse(id=request.id, result=result)
    except Exception as e:
        return MCPResponse(
            id=request.id,
            error={
                "code": -32000,
                "message": str(e),
            },
        )


def extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> Optional[str]:
    if credentials:
        return credentials.credentials
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


@mcp_router.post(
    "/mcp",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "tools_list": {
                            "summary": "List available tools",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 1,
                                "result": {
                                    "tools": [
                                        {
                                            "name": "slack.channels.list",
                                            "description": "List all channels in Slack workspace",
                                            "inputSchema": {"type": "object"},
                                        }
                                    ]
                                },
                            },
                        },
                        "tools_call": {
                            "summary": "Call a tool",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 2,
                                "result": {
                                    "content": [
                                        {"type": "text", "text": "{\"ok\": true}"}
                                    ]
                                },
                            },
                        },
                        "error": {
                            "summary": "Error response",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 3,
                                "error": {"code": -32000, "message": "Missing tool name"},
                            },
                        },
                    }
                }
            }
        }
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "tools_list": {
                            "summary": "List tools",
                            "value": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        },
                        "tools_call": {
                            "summary": "Call a tool",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 2,
                                "method": "tools/call",
                                "params": {
                                    "name": "telegram.messages.history",
                                    "arguments": {"peer": "+1234567890", "limit": 5},
                                },
                            },
                        },
                        "hub_integrations": {
                            "summary": "List integrations",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 3,
                                "method": "tools/call",
                                "params": {"name": "hub.integrations.list", "arguments": {}},
                            },
                        },
                    }
                }
            }
        }
    },
)
async def mcp_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    token = extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    user = get_user_from_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    provider_filter = request.headers.get("X-MCP-Provider")
    name_format = resolve_tool_name_format(request)

    body = await request.json()
    mcp_request = MCPRequest(**body)
    response = await process_mcp_request(user, mcp_request, provider_filter, name_format)

    return response.model_dump(exclude_none=True)


@mcp_router.get(
    "/mcp",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "sse_info": {
                            "summary": "SSE endpoint hint",
                            "value": {
                                "endpoint": "http://localhost:8000/mcp/messages",
                                "note": "Use Accept: text/event-stream for SSE",
                            },
                        }
                    }
                }
            }
        }
    },
)
async def mcp_sse_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    token = extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    user = get_user_from_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    provider_filter = request.headers.get("X-MCP-Provider")
    _ = resolve_tool_name_format(request)

    accept_header = request.headers.get("accept", "")
    if "text/event-stream" not in accept_header.lower():
        endpoint_url = str(request.url).replace("/mcp", "/mcp/messages")
        return JSONResponse(
            {"endpoint": endpoint_url, "note": "Use Accept: text/event-stream for SSE"}
        )

    async def event_generator():
        endpoint_url = str(request.url).replace("/mcp", "/mcp/messages")
        event_data = json.dumps({"endpoint": endpoint_url})
        yield f"event: endpoint\ndata: {event_data}\n\n"

        while True:
            if await request.is_disconnected():
                break
            yield ": keepalive\n\n"
            import asyncio
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@mcp_router.post(
    "/mcp/messages",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "tools_call": {
                            "summary": "Call a tool over SSE messages endpoint",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 2,
                                "result": {
                                    "content": [
                                        {"type": "text", "text": "{\"ok\": true}"}
                                    ]
                                },
                            },
                        }
                    }
                }
            }
        }
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "tools_call": {
                            "summary": "Call a tool",
                            "value": {
                                "jsonrpc": "2.0",
                                "id": 2,
                                "method": "tools/call",
                                "params": {
                                    "name": "slack.messages.history",
                                    "arguments": {"channel": "C123456", "limit": 5},
                                },
                            },
                        }
                    }
                }
            }
        }
    },
)
async def mcp_messages_endpoint(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    return await mcp_endpoint(request, credentials)
