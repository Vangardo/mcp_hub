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
    error_text: Optional[str] = None,
):
    try:
        log_tool_call(
            user_id=user_id,
            provider=provider,
            action=action,
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

HUB_TOOLS = [
    {
        "name": "hub.integrations.list",
        "description": "List connected integrations and available tools",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_tools": {"type": "boolean", "default": True},
                "connected_only": {"type": "boolean", "default": True},
            },
        },
    },
]


def get_available_tools(user_id: int, provider_filter: Optional[str] = None) -> list[dict]:
    connected_providers = get_user_connected_providers(user_id)
    tools = []

    if provider_filter:
        connected_providers = [p for p in connected_providers if p == provider_filter]

    if not provider_filter:
        tools.extend(HUB_TOOLS)

    for integration in integration_registry.list_configured():
        if integration.name not in connected_providers:
            continue

        for tool in integration.get_tools():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            })

    return tools


async def handle_initialize(user: dict, params: Optional[dict], provider_filter: Optional[str] = None) -> dict:
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


async def handle_list_tools(user: dict, params: Optional[dict], provider_filter: Optional[str] = None) -> dict:
    tools = get_available_tools(user["id"], provider_filter)
    safe_audit_log(
        user_id=user["id"],
        provider=provider_filter,
        action="mcp.tools.list",
        request_data=params,
        response_data={"count": len(tools)},
        status="ok",
    )
    return {"tools": tools}

async def handle_call_tool(user: dict, params: Optional[dict], provider_filter: Optional[str] = None) -> dict:
    if not params:
        raise ValueError("Missing params")

    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        raise ValueError("Missing tool name")

    if tool_name == "hub.integrations.list":
        connected_providers = set(get_user_connected_providers(user["id"]))
        include_tools = True
        connected_only = True
        if params:
            include_tools = params.get("include_tools", True)
            connected_only = params.get("connected_only", True)

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
            request_data=params,
            response_data={"count": len(integrations)},
            status="ok",
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"integrations": integrations}, default=str),
                }
            ],
        }

    if provider_filter:
        if not tool_name.startswith(f"{provider_filter}."):
            raise ValueError(f"Tool not allowed for provider filter: {provider_filter}")

    provider, _ = parse_tool_name(tool_name)

    result = await execute_tool(user["id"], tool_name, arguments)

    safe_audit_log(
        user_id=user["id"],
        provider=provider,
        action=tool_name,
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
                    "text": json.dumps(result.data, default=str),
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
        result = await handler(user, request.params, provider_filter)
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

    body = await request.json()
    mcp_request = MCPRequest(**body)
    response = await process_mcp_request(user, mcp_request, provider_filter)

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
