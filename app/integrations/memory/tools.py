"""MCP tools for the Memory provider."""

import json
from datetime import datetime, timezone
from typing import Optional

from app.db.database import get_db
from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.memory import store, evaluate


MEMORY_TOOLS = [
    # =====================================================
    # CONTEXT — read user's stored context
    # =====================================================
    ToolDefinition(
        name="memory.summarize_context",
        description=(
            "Get the user's context pack — pinned items, preferences, constraints, "
            "active projects/goals, watchlist, contacts, and recent notes.\n"
            "\n"
            "WORKFLOW: Call this at the start of a conversation to load the user's "
            "persistent context. Use scope to filter by integration (e.g. 'binance', "
            "'teamwork', 'slack') or 'auto'/'global' for everything.\n"
            "\n"
            "Returns grouped sections with up to max_per_section items each."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": (
                        "Filter scope: 'auto' (all), 'global', or integration name "
                        "(binance, teamwork, slack, telegram, figma, miro). Default: auto"
                    ),
                    "default": "auto",
                },
                "max_per_section": {
                    "type": "integer",
                    "description": "Max items per section (default: 10)",
                    "default": 10,
                },
            },
        },
    ),
    # =====================================================
    # SEARCH — full-text search across memory
    # =====================================================
    ToolDefinition(
        name="memory.search",
        description=(
            "Full-text search across all memory items.\n"
            "Uses SQLite FTS5 — supports AND, OR, NOT, phrase queries.\n"
            "\n"
            "Examples:\n"
            '  query: "risk management" — phrase match\n'
            "  query: bitcoin OR ethereum — either term\n"
            "  query: portfolio NOT crypto — exclude term\n"
            "\n"
            "Combine with filters to narrow by type, scope, pinned, sensitivity."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "FTS5 search query",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional filters to narrow results",
                    "properties": {
                        "type": {
                            "description": "Filter by type(s): preference, constraint, decision, goal, project, contact, asset, note",
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                        },
                        "scope": {
                            "type": "string",
                            "description": "Filter by scope (global, binance, teamwork, etc.)",
                        },
                        "pinned": {
                            "type": "boolean",
                            "description": "Filter by pinned status",
                        },
                        "sensitivity": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Filter by sensitivity level",
                        },
                    },
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results (default: 20)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    # =====================================================
    # WRITE — create or update a memory item
    # =====================================================
    ToolDefinition(
        name="memory.upsert",
        description=(
            "Create or update a memory item. Deduplicates by (type + scope + title).\n"
            "\n"
            "Types:\n"
            "  preference — user preferences (permanent)\n"
            "  constraint — rules/limits the user set (permanent)\n"
            "  decision   — important decisions made (permanent)\n"
            "  goal       — goals/objectives (TTL 30 days)\n"
            "  project    — active projects (permanent)\n"
            "  contact    — people/entities (permanent)\n"
            "  asset      — tracked assets/positions (permanent)\n"
            "  note       — general notes (TTL 7 days unless pinned)\n"
            "\n"
            "The system auto-evaluates items (secret detection, sensitivity) and may "
            "adjust TTL. Set explicit=true when the user explicitly asked to remember.\n"
            "\n"
            "value_json: structured data (object or string). Use objects for machine-readable data."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short descriptive title (used as unique key with type+scope)",
                },
                "type": {
                    "type": "string",
                    "enum": ["preference", "constraint", "decision", "goal", "project", "contact", "asset", "note"],
                    "description": "Memory item type",
                },
                "scope": {
                    "type": "string",
                    "description": "Integration scope: global, binance, teamwork, slack, telegram, figma, miro (default: global)",
                    "default": "global",
                },
                "value_json": {
                    "description": "Structured value — object or string",
                },
                "tags_json": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Pin this item (prevents TTL expiry)",
                    "default": False,
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Sensitivity level (default: low)",
                    "default": "low",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0 (default: 1.0)",
                    "default": 1.0,
                },
                "explicit": {
                    "type": "boolean",
                    "description": "Set true when the user explicitly asked to remember this",
                    "default": False,
                },
                "source_json": {
                    "type": "object",
                    "description": "Source metadata: {tool, timestamp, message_id}",
                },
            },
            "required": ["title", "type"],
        },
    ),
    # =====================================================
    # DELETE — remove a memory item
    # =====================================================
    ToolDefinition(
        name="memory.delete",
        description=(
            "Delete a memory item by ID or by title.\n"
            "Provide 'id' (UUID) for exact match, or 'title' (+ optional type/scope) "
            "to delete by title. At least one of id or title is required."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Memory item ID (UUID). Takes priority over title.",
                },
                "title": {
                    "type": "string",
                    "description": "Memory item title (fallback if id not provided)",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by type when deleting by title",
                },
                "scope": {
                    "type": "string",
                    "description": "Filter by scope when deleting by title",
                },
            },
        },
    ),
    # =====================================================
    # PIN — toggle pinned status
    # =====================================================
    ToolDefinition(
        name="memory.pin",
        description=(
            "Toggle the pinned status of a memory item.\n"
            "Pinned items appear in the context pack and never expire (TTL ignored)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Memory item ID",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Pin (true) or unpin (false)",
                },
            },
            "required": ["id", "pinned"],
        },
    ),
    # =====================================================
    # SET TTL — configure expiration
    # =====================================================
    ToolDefinition(
        name="memory.set_ttl",
        description=(
            "Set the time-to-live for a memory item.\n"
            "null = permanent (never expires), integer = days until expiry."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Memory item ID",
                },
                "ttl_days": {
                    "type": ["integer", "null"],
                    "description": "Days until expiry, or null for permanent",
                },
            },
            "required": ["id", "ttl_days"],
        },
    ),
    # =====================================================
    # EVALUATE — check before auto-saving
    # =====================================================
    ToolDefinition(
        name="memory.evaluate_write",
        description=(
            "Evaluate a candidate memory item before saving.\n"
            "Returns whether the item should be saved, with what type, TTL, "
            "sensitivity, and a reason code.\n"
            "\n"
            "Use this to check before auto-saving — it detects secrets, "
            "validates sensitivity levels, and suggests appropriate TTLs.\n"
            "\n"
            "Reason codes: SECRET_REJECTED, HIGH_SENSITIVITY_NEEDS_EXPLICIT, "
            "PREFERENCE_STABLE, DURABLE_ENTITY, GOAL_MEDIUM_TERM, SHORT_TERM_NOTE, "
            "USER_PINNED, DEFAULT_SHORT_TERM"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Candidate title",
                },
                "type": {
                    "type": "string",
                    "description": "Candidate type",
                },
                "value_json": {
                    "description": "Candidate value",
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "default": "low",
                },
                "pinned": {
                    "type": "boolean",
                    "default": False,
                },
                "explicit": {
                    "type": "boolean",
                    "description": "Whether user explicitly asked to remember",
                    "default": False,
                },
            },
            "required": ["title", "type"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    """Execute a memory tool. access_token is str(user_id)."""
    user_id = int(access_token)

    try:
        with get_db() as conn:
            # ── Context ──

            if tool_name == "memory.summarize_context":
                pack = store.get_context_pack(
                    conn,
                    user_id,
                    scope=args.get("scope", "auto"),
                    max_per_section=args.get("max_per_section", 10),
                )
                total = store.count_items(conn, user_id)
                return ToolResult(
                    success=True,
                    data={
                        "total_items": total,
                        "context": pack,
                    },
                )

            # ── Search ──

            elif tool_name == "memory.search":
                results = store.search_items(
                    conn,
                    user_id,
                    query=args["query"],
                    filters=args.get("filters"),
                    top_k=args.get("top_k", 20),
                )
                return ToolResult(
                    success=True,
                    data={
                        "count": len(results),
                        "results": results,
                    },
                )

            # ── Upsert ──

            elif tool_name == "memory.upsert":
                # Run evaluation first
                eval_result = evaluate.evaluate_write(args)
                if not eval_result["allow"]:
                    return ToolResult(
                        success=False,
                        error=f"Write rejected: {eval_result['reason_code']}",
                        data=eval_result,
                    )

                # Auto-populate source if not provided
                source = args.get("source_json")
                if not source:
                    source = {
                        "tool": "mcp",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                # Apply evaluated parameters
                item = {
                    "title": args["title"],
                    "type": eval_result["type"],
                    "scope": args.get("scope", "global"),
                    "value_json": args.get("value_json", "{}"),
                    "tags_json": args.get("tags_json", "[]"),
                    "pinned": args.get("pinned", False),
                    "ttl_days": eval_result["ttl_days"],
                    "sensitivity": eval_result["sensitivity"],
                    "confidence": args.get("confidence", 1.0),
                    "source_json": source,
                }
                saved = store.upsert_item(conn, user_id, item)
                return ToolResult(
                    success=True,
                    data={
                        "item": saved,
                        "evaluation": eval_result,
                    },
                )

            # ── Delete ──

            elif tool_name == "memory.delete":
                item_id = args.get("id")
                title = args.get("title")

                if not item_id and not title:
                    return ToolResult(success=False, error="Provide 'id' or 'title' to delete")

                deleted = False
                if item_id:
                    deleted = store.delete_item(conn, user_id, item_id)

                if not deleted and title:
                    deleted = store.delete_by_title(
                        conn, user_id, title,
                        item_type=args.get("type"),
                        scope=args.get("scope"),
                    )

                if deleted:
                    return ToolResult(success=True, data={"deleted": True})

                hint = f"id={item_id}" if item_id else f"title={title}"
                return ToolResult(
                    success=False,
                    error=f"Item not found ({hint}). Use memory.search or memory.summarize_context to find items first.",
                )

            # ── Pin ──

            elif tool_name == "memory.pin":
                updated = store.pin_item(conn, user_id, args["id"], args["pinned"])
                if updated:
                    return ToolResult(
                        success=True,
                        data={"id": args["id"], "pinned": args["pinned"]},
                    )
                return ToolResult(success=False, error="Item not found")

            # ── Set TTL ──

            elif tool_name == "memory.set_ttl":
                updated = store.set_ttl(conn, user_id, args["id"], args.get("ttl_days"))
                if updated:
                    return ToolResult(
                        success=True,
                        data={"id": args["id"], "ttl_days": args.get("ttl_days")},
                    )
                return ToolResult(success=False, error="Item not found")

            # ── Evaluate Write ──

            elif tool_name == "memory.evaluate_write":
                result = evaluate.evaluate_write(args)
                return ToolResult(success=True, data=result)

            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
