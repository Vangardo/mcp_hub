from typing import Optional, Any
from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.teamwork.client import TeamworkClient


def _extract_items(data: Any, keys: list[str]) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                value = data[key]
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    if "id" in value or "name" in value:
                        return [value]
                    for nested_key in ("items", "item", key[:-1], key):
                        nested = value.get(nested_key)
                        if isinstance(nested, list):
                            return [item for item in nested if isinstance(item, dict)]
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def _get_item_name(item: dict) -> Optional[str]:
    if "name" in item and isinstance(item["name"], str):
        return item["name"]
    if "title" in item and isinstance(item["title"], str):
        return item["title"]
    if "label" in item and isinstance(item["label"], str):
        return item["label"]
    if "tag" in item and isinstance(item["tag"], dict):
        name = item["tag"].get("name")
        if isinstance(name, str):
            return name
    return None


def _get_item_id(item: dict) -> Optional[int]:
    for key in ("id", "tagId", "stageId", "columnId"):
        if key in item:
            try:
                return int(item[key])
            except Exception:
                return None
    if "tag" in item and isinstance(item["tag"], dict):
        tag_id = item["tag"].get("id")
        if tag_id is not None:
            try:
                return int(tag_id)
            except Exception:
                return None
    return None


def _normalize_items(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        normalized.append({
            "id": _get_item_id(item),
            "name": _get_item_name(item),
            "color": item.get("color") or item.get("colour"),
            "raw": item,
        })
    return normalized


def _find_by_name(items: list[dict], target_name: str) -> list[dict]:
    target = target_name.strip().lower()
    matches = []
    for item in items:
        name = item.get("name")
        if not name and isinstance(item.get("raw"), dict):
            name = _get_item_name(item["raw"])
        if isinstance(name, str) and name.strip().lower() == target:
            matches.append(item)
    return matches


async def _ensure_tags(
    client: TeamworkClient,
    names: list[str],
    project_id: Optional[int] = None,
    color_map: Optional[dict] = None,
) -> list[int]:
    if not names:
        return []
    color_map = color_map or {}
    tags_data = await client.list_tags(project_id=project_id)
    tag_items = _normalize_items(_extract_items(tags_data, ["tags", "tag"]))
    existing = {}
    for item in tag_items:
        name = item.get("name")
        if name and item.get("id") is not None:
            existing[name.strip().lower()] = int(item["id"])

    missing = []
    tag_ids: list[int] = []
    for name in names:
        key = name.strip().lower()
        if key in existing:
            tag_ids.append(existing[key])
        else:
            missing.append(name)

    unresolved = []
    for name in missing:
        color = color_map.get(name) or color_map.get(name.lower())
        created = await client.create_tag(name=name, color=color, project_id=project_id)
        created_items = _extract_items(created, ["tags", "tag"])
        created_id = None
        if isinstance(created, dict) and "id" in created:
            try:
                created_id = int(created["id"])
            except Exception:
                created_id = None
        if created_id is None and created_items:
            created_id = _get_item_id(created_items[0])
        if created_id is not None:
            tag_ids.append(created_id)
        else:
            unresolved.append(name)

    if unresolved:
        tags_data = await client.list_tags(project_id=project_id)
        tag_items = _normalize_items(_extract_items(tags_data, ["tags", "tag"]))
        existing = {}
        for item in tag_items:
            name = item.get("name")
            if name and item.get("id") is not None:
                existing[name.strip().lower()] = int(item["id"])
        for name in unresolved:
            key = name.strip().lower()
            if key in existing:
                tag_ids.append(existing[key])
            else:
                raise ValueError(f"Failed to resolve tag ID for '{name}'")

    return tag_ids


TEAMWORK_TOOLS = [
    ToolDefinition(
        name="teamwork.projects.list",
        description="List all projects in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.people.list",
        description="List all people/users in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.list",
        description="List tasks in Teamwork with optional filters",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "assignee_id": {"type": "integer", "description": "Filter by assignee ID"},
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["all", "active", "completed", "late"],
                },
                "due_after": {"type": "string", "description": "Due date after (YYYYMMDD)"},
                "due_before": {"type": "string", "description": "Due date before (YYYYMMDD)"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.create",
        description="Create a new task in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
                "tasklist_id": {"type": "integer", "description": "Task list ID"},
                "content": {"type": "string", "description": "Task title/content"},
                "description": {"type": "string", "description": "Task description"},
                "assignee_id": {"type": "integer", "description": "Assignee user ID"},
                "due_date": {"type": "string", "description": "Due date (YYYYMMDD)"},
                "priority": {
                    "type": "string",
                    "description": "Task priority",
                    "enum": ["none", "low", "medium", "high"],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Array of tag IDs to assign",
                },
                "tag_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tag names to ensure and assign (uses colors if provided)",
                },
                "tag_colors": {
                    "type": "object",
                    "description": "Optional map of tag name -> hex color (#RRGGBB)",
                },
                "estimated_minutes": {
                    "type": "integer",
                    "description": "Estimated time in minutes",
                },
            },
            "required": ["project_id", "tasklist_id", "content"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.update",
        description="Update an existing task in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to update"},
                "content": {"type": "string", "description": "New task title"},
                "description": {"type": "string", "description": "New description"},
                "assignee_id": {"type": "integer", "description": "New assignee ID"},
                "due_date": {"type": "string", "description": "New due date (YYYYMMDD)"},
                "priority": {
                    "type": "string",
                    "description": "Task priority",
                    "enum": ["none", "low", "medium", "high"],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Array of tag IDs to assign",
                },
                "tag_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tag names to ensure and assign (uses colors if provided)",
                },
                "tag_colors": {
                    "type": "object",
                    "description": "Optional map of tag name -> hex color (#RRGGBB)",
                },
                "estimated_minutes": {
                    "type": "integer",
                    "description": "Estimated time in minutes",
                },
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.complete",
        description="Mark a task as complete in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to complete"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.list",
        description="List task lists for a project in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tags.list",
        description="List all available tags in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Optional: filter by project ID"},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tags.ensure",
        description="Ensure tags exist (create missing) and return IDs",
        input_schema={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tag names to ensure",
                },
                "project_id": {"type": "integer", "description": "Optional project ID"},
                "tag_colors": {
                    "type": "object",
                    "description": "Optional map of tag name -> hex color (#RRGGBB)",
                },
            },
            "required": ["names"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.get",
        description="Get details of a single task by ID",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    ),
    # === SUBTASKS ===
    ToolDefinition(
        name="teamwork.subtasks.create",
        description="Create a subtask under a parent task",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "integer", "description": "Parent task ID"},
                "content": {"type": "string", "description": "Subtask title"},
                "description": {"type": "string", "description": "Subtask description"},
                "assignee_id": {"type": "integer", "description": "Assignee user ID"},
                "due_date": {"type": "string", "description": "Due date (YYYYMMDD)"},
                "estimated_minutes": {"type": "integer", "description": "Estimated time in minutes"},
            },
            "required": ["parent_task_id", "content"],
        },
    ),
    ToolDefinition(
        name="teamwork.subtasks.list",
        description="List subtasks of a parent task",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "integer", "description": "Parent task ID"},
            },
            "required": ["parent_task_id"],
        },
    ),
    # === TIME ENTRIES ===
    ToolDefinition(
        name="teamwork.time.log",
        description="Log time entry for a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "hours": {"type": "integer", "description": "Hours spent"},
                "minutes": {"type": "integer", "description": "Minutes spent"},
                "date": {"type": "string", "description": "Date (YYYYMMDD)"},
                "description": {"type": "string", "description": "Description of work done"},
                "user_id": {"type": "integer", "description": "User ID (default: current user)"},
                "is_billable": {"type": "boolean", "description": "Is billable time", "default": False},
            },
            "required": ["task_id", "hours", "minutes", "date"],
        },
    ),
    ToolDefinition(
        name="teamwork.time.list",
        description="List time entries with optional filters",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Filter by task ID"},
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "user_id": {"type": "integer", "description": "Filter by user ID"},
                "from_date": {"type": "string", "description": "Start date (YYYYMMDD)"},
                "to_date": {"type": "string", "description": "End date (YYYYMMDD)"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.time.totals",
        description="Get time totals summary (useful for daily/weekly reports)",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "user_id": {"type": "integer", "description": "Filter by user ID"},
                "from_date": {"type": "string", "description": "Start date (YYYYMMDD)"},
                "to_date": {"type": "string", "description": "End date (YYYYMMDD)"},
            },
        },
    ),
    # === COMMENTS ===
    ToolDefinition(
        name="teamwork.comments.add",
        description="Add a comment to a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "body": {"type": "string", "description": "Comment text"},
                "notify": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "User IDs to notify",
                },
            },
            "required": ["task_id", "body"],
        },
    ),
    ToolDefinition(
        name="teamwork.comments.list",
        description="List comments for a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
            "required": ["task_id"],
        },
    ),
    # === TAGS MANAGEMENT ===
    ToolDefinition(
        name="teamwork.tags.create",
        description="Create a new tag with optional color",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tag name"},
                "color": {"type": "string", "description": "Color in hex format (#RRGGBB), e.g. #FF5733"},
                "project_id": {"type": "integer", "description": "Project ID (optional, creates global tag if omitted)"},
            },
            "required": ["name"],
        },
    ),
    ToolDefinition(
        name="teamwork.tags.update",
        description="Update an existing tag (name or color)",
        input_schema={
            "type": "object",
            "properties": {
                "tag_id": {"type": "integer", "description": "Tag ID"},
                "name": {"type": "string", "description": "New tag name"},
                "color": {"type": "string", "description": "New color (#RRGGBB)"},
            },
            "required": ["tag_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tags.delete",
        description="Delete a tag",
        input_schema={
            "type": "object",
            "properties": {
                "tag_id": {"type": "integer", "description": "Tag ID to delete"},
            },
            "required": ["tag_id"],
        },
    ),
    # === BOARD COLUMNS / STAGES ===
    ToolDefinition(
        name="teamwork.columns.list",
        description="List board columns (stages) for a project",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.move_to_column",
        description="Move a task to a different board column (stage)",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "column_id": {"type": "integer", "description": "Target column/stage ID"},
                "position_after_task": {"type": "integer", "description": "Position after this task ID (optional)"},
            },
            "required": ["task_id", "column_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.move_to_column_by_name",
        description="Move a task to a board column by name",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "project_id": {"type": "integer", "description": "Project ID"},
                "column_name": {"type": "string", "description": "Column/stage name"},
                "position_after_task": {"type": "integer", "description": "Position after this task ID (optional)"},
            },
            "required": ["task_id", "project_id", "column_name"],
        },
    ),
    ToolDefinition(
        name="teamwork.stages.list",
        description="List workflow stages for a project",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.set_stage",
        description="Set workflow stage for a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "stage_id": {"type": "integer", "description": "Stage ID"},
            },
            "required": ["task_id", "stage_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.set_stage_by_name",
        description="Set workflow stage for a task by stage name",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "project_id": {"type": "integer", "description": "Project ID"},
                "stage_name": {"type": "string", "description": "Stage name"},
            },
            "required": ["task_id", "project_id", "stage_name"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    site_url = meta.get("site_url", "") if meta else ""
    if not site_url:
        return ToolResult(success=False, error="Site URL not configured")

    client = TeamworkClient(access_token, site_url)

    try:
        if tool_name == "teamwork.projects.list":
            result = await client.list_projects(
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.people.list":
            result = await client.list_people(
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.list":
            result = await client.list_tasks(
                project_id=args.get("project_id"),
                assignee_id=args.get("assignee_id"),
                status=args.get("status"),
                due_after=args.get("due_after"),
                due_before=args.get("due_before"),
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.create":
            tag_ids = args.get("tags") or []
            tag_names = args.get("tag_names") or []
            tag_colors = args.get("tag_colors") or {}
            if tag_names:
                resolved = await _ensure_tags(
                    client,
                    names=tag_names,
                    project_id=args.get("project_id"),
                    color_map=tag_colors,
                )
                tag_ids = list({*tag_ids, *resolved})
            result = await client.create_task(
                project_id=args["project_id"],
                tasklist_id=args["tasklist_id"],
                content=args["content"],
                description=args.get("description"),
                assignee_id=args.get("assignee_id"),
                due_date=args.get("due_date"),
                priority=args.get("priority"),
                tags=tag_ids,
                estimated_minutes=args.get("estimated_minutes"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.update":
            update_fields = {
                k: v for k, v in args.items()
                if k != "task_id" and v is not None
            }
            tag_ids = args.get("tags") or []
            tag_names = args.get("tag_names") or []
            if tag_names:
                resolved = await _ensure_tags(
                    client,
                    names=tag_names,
                    project_id=args.get("project_id"),
                    color_map=args.get("tag_colors") or {},
                )
                tag_ids = list({*tag_ids, *resolved})
            if tag_ids:
                update_fields["tags"] = tag_ids
            result = await client.update_task(args["task_id"], **update_fields)
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.complete":
            result = await client.complete_task(args["task_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.list":
            result = await client.get_tasklists(args["project_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tags.list":
            result = await client.list_tags(project_id=args.get("project_id"))
            items = _normalize_items(_extract_items(result, ["tags", "tag"]))
            return ToolResult(success=True, data={"items": items, "raw": result})

        elif tool_name == "teamwork.tags.ensure":
            tag_ids = await _ensure_tags(
                client,
                names=args["names"],
                project_id=args.get("project_id"),
                color_map=args.get("tag_colors") or {},
            )
            return ToolResult(success=True, data={"tag_ids": tag_ids})

        elif tool_name == "teamwork.tasks.get":
            result = await client.get_task(args["task_id"])
            return ToolResult(success=True, data=result)

        # === SUBTASKS ===
        elif tool_name == "teamwork.subtasks.create":
            result = await client.create_subtask(
                parent_task_id=args["parent_task_id"],
                content=args["content"],
                description=args.get("description"),
                assignee_id=args.get("assignee_id"),
                due_date=args.get("due_date"),
                estimated_minutes=args.get("estimated_minutes"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.subtasks.list":
            result = await client.list_subtasks(args["parent_task_id"])
            return ToolResult(success=True, data=result)

        # === TIME ENTRIES ===
        elif tool_name == "teamwork.time.log":
            result = await client.log_time(
                task_id=args["task_id"],
                hours=args["hours"],
                minutes=args["minutes"],
                date=args["date"],
                description=args.get("description"),
                user_id=args.get("user_id"),
                is_billable=args.get("is_billable", False),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.time.list":
            result = await client.list_time_entries(
                task_id=args.get("task_id"),
                project_id=args.get("project_id"),
                user_id=args.get("user_id"),
                from_date=args.get("from_date"),
                to_date=args.get("to_date"),
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.time.totals":
            result = await client.get_time_totals(
                project_id=args.get("project_id"),
                user_id=args.get("user_id"),
                from_date=args.get("from_date"),
                to_date=args.get("to_date"),
            )
            return ToolResult(success=True, data=result)

        # === COMMENTS ===
        elif tool_name == "teamwork.comments.add":
            result = await client.add_comment(
                task_id=args["task_id"],
                body=args["body"],
                notify=args.get("notify"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.comments.list":
            result = await client.list_comments(
                task_id=args["task_id"],
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        # === TAGS MANAGEMENT ===
        elif tool_name == "teamwork.tags.create":
            result = await client.create_tag(
                name=args["name"],
                color=args.get("color"),
                project_id=args.get("project_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tags.update":
            result = await client.update_tag(
                tag_id=args["tag_id"],
                name=args.get("name"),
                color=args.get("color"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tags.delete":
            result = await client.delete_tag(args["tag_id"])
            return ToolResult(success=True, data=result)

        # === BOARD COLUMNS / STAGES ===
        elif tool_name == "teamwork.columns.list":
            result = await client.list_columns(args["project_id"])
            items = _normalize_items(_extract_items(result, ["columns", "column"]))
            return ToolResult(success=True, data={"items": items, "raw": result})

        elif tool_name == "teamwork.tasks.move_to_column":
            result = await client.move_task_to_column(
                task_id=args["task_id"],
                column_id=args["column_id"],
                position_after_task=args.get("position_after_task"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.move_to_column_by_name":
            columns = await client.list_columns(args["project_id"])
            items = _normalize_items(_extract_items(columns, ["columns", "column"]))
            matches = _find_by_name(items, args["column_name"])
            if not matches:
                available = [item.get("name") for item in items if item.get("name")]
                raise ValueError(f"Column not found. Available: {available}")
            if len(matches) > 1:
                raise ValueError(f"Multiple columns matched: {[m.get('name') for m in matches]}")
            column_id = matches[0].get("id")
            if column_id is None:
                raise ValueError("Column ID not found for matched column")
            result = await client.move_task_to_column(
                task_id=args["task_id"],
                column_id=column_id,
                position_after_task=args.get("position_after_task"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.stages.list":
            result = await client.list_project_stages(args["project_id"])
            items = _normalize_items(_extract_items(result, ["stages", "stage"]))
            return ToolResult(success=True, data={"items": items, "raw": result})

        elif tool_name == "teamwork.tasks.set_stage":
            result = await client.update_task_stage(
                task_id=args["task_id"],
                stage_id=args["stage_id"],
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.set_stage_by_name":
            stages = await client.list_project_stages(args["project_id"])
            items = _normalize_items(_extract_items(stages, ["stages", "stage"]))
            matches = _find_by_name(items, args["stage_name"])
            if not matches:
                available = [item.get("name") for item in items if item.get("name")]
                raise ValueError(f"Stage not found. Available: {available}")
            if len(matches) > 1:
                raise ValueError(f"Multiple stages matched: {[m.get('name') for m in matches]}")
            stage_id = matches[0].get("id")
            if stage_id is None:
                raise ValueError("Stage ID not found for matched stage")
            result = await client.update_task_stage(
                task_id=args["task_id"],
                stage_id=stage_id,
            )
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
