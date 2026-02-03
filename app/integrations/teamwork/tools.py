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
            if isinstance(value, dict):
                for nested_value in value.values():
                    if isinstance(nested_value, list) and nested_value and isinstance(nested_value[0], dict):
                        return nested_value
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


async def _resolve_existing_tags(
    client: TeamworkClient,
    names: list[str],
    project_id: Optional[int] = None,
) -> tuple[list[int], list[str]]:
    """Find existing tags by name. Returns (found_ids, not_found_names)."""
    if not names:
        return [], []

    tag_items: list[dict] = []

    # If project_id is provided, Teamwork may return only project-specific tags.
    # Merge with global tags so we can resolve both scopes.
    try:
        tags_data = await client.list_tags(project_id=project_id)
        tag_items.extend(_normalize_items(_extract_items(tags_data, ["tags", "tag"])))
    except Exception:
        pass

    try:
        global_tags_data = await client.list_tags(project_id=None)
        tag_items.extend(_normalize_items(_extract_items(global_tags_data, ["tags", "tag"])))
    except Exception:
        pass
    existing = {}
    for item in tag_items:
        name = item.get("name")
        if name and item.get("id") is not None:
            existing[name.strip().lower()] = int(item["id"])

    tag_ids: list[int] = []
    not_found: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key in existing:
            tag_ids.append(existing[key])
        else:
            not_found.append(name)

    return tag_ids, not_found


async def _ensure_tags(
    client: TeamworkClient,
    names: list[str],
    project_id: Optional[int] = None,
    color_map: Optional[dict] = None,
) -> list[int]:
    """Resolve tag names to IDs. Only uses existing tags (creation often blocked by 403)."""
    if not names:
        return []

    tag_ids, not_found = await _resolve_existing_tags(client, names, project_id)

    # Try to create missing tags, but don't fail if 403
    if not_found:
        color_map = color_map or {}
        for name in not_found:
            try:
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
            except Exception:
                # 403 Forbidden or other error - skip tag creation
                pass

        # Re-check for any tags that might have been created
        if not_found:
            new_ids, still_missing = await _resolve_existing_tags(client, not_found, project_id)
            tag_ids.extend(new_ids)
            # Don't raise error for missing tags - just skip them
            if still_missing:
                pass  # Tags not found and can't be created - silently skip

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
        description="List tasks in Teamwork with optional filters. Use dueDateFrom/dueDateTo for deadline filtering",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "assignee_id": {"type": "integer", "description": "Filter by assignee ID"},
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["all", "active", "completed", "late", "overdue"],
                },
                "due_after": {"type": "string", "description": "Due date FROM (YYYYMMDD) - tasks due on or after this date"},
                "due_before": {"type": "string", "description": "Due date TO (YYYYMMDD) - tasks due on or before this date"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.due_today",
        description="Get tasks due today (shortcut for filtering by today's date)",
        input_schema={
            "type": "object",
            "properties": {
                "assignee_id": {"type": "integer", "description": "Filter by assignee ID"},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.overdue",
        description="Get overdue tasks (tasks past their due date)",
        input_schema={
            "type": "object",
            "properties": {
                "assignee_id": {"type": "integer", "description": "Filter by assignee ID"},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.workflows.list",
        description="List all workflows (board views) in a project. Use this to get workflow IDs for stages",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
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
        name="teamwork.tasks.bulk_create",
        description="Create up to 10 tasks in Teamwork (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Default project ID for items"},
                "tasklist_id": {"type": "integer", "description": "Default task list ID for items"},
                "tag_colors": {
                    "type": "object",
                    "description": "Optional map of tag name -> hex color (#RRGGBB) for all items",
                },
                "items": {
                    "type": "array",
                    "description": "Tasks to create (max 10)",
                    "items": {
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
                        "required": ["content"],
                    },
                },
            },
            "required": ["items"],
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
        name="teamwork.tasks.bulk_update",
        description="Update up to 10 tasks in Teamwork (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Default project ID for items"},
                "tag_colors": {
                    "type": "object",
                    "description": "Optional map of tag name -> hex color (#RRGGBB) for all items",
                },
                "items": {
                    "type": "array",
                    "description": "Tasks to update (max 10)",
                    "items": {
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
                },
            },
            "required": ["items"],
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
    # === WORKFLOW STAGES (Board View) ===
    # Teamwork uses Workflows API v3 for board columns/stages
    # First get stages list, then use stage_id to move tasks
    ToolDefinition(
        name="teamwork.stages.list",
        description="List workflow stages (board columns like 'To Do', 'In Progress', 'Done') for a project. Returns stage IDs needed for moving tasks.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.columns.list",
        description="Alias for stages.list - List workflow stages/columns for a project",
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
        description="Move a task to a workflow stage by ID. REQUIRES workflow_id from stages.list result!",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "stage_id": {"type": "integer", "description": "Target stage ID (from stages.list)"},
                "workflow_id": {"type": "integer", "description": "Workflow ID (from stages.list result)"},
                "project_id": {"type": "integer", "description": "Project ID (alternative to workflow_id)"},
            },
            "required": ["task_id", "stage_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.set_stage_by_name",
        description="Move a task to a workflow stage by name (e.g., 'In Progress', 'Done'). Easier to use than set_stage.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "project_id": {"type": "integer", "description": "Project ID"},
                "stage_name": {"type": "string", "description": "Stage name (e.g., 'To Do', 'In Progress', 'Done')"},
            },
            "required": ["task_id", "project_id", "stage_name"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.move_to_column",
        description="Alias for set_stage - Move a task to a different stage/column by ID",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "column_id": {"type": "integer", "description": "Target stage/column ID"},
                "workflow_id": {"type": "integer", "description": "Workflow ID"},
                "project_id": {"type": "integer", "description": "Project ID (alternative to workflow_id)"},
            },
            "required": ["task_id", "column_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.move_to_column_by_name",
        description="Alias for set_stage_by_name - Move a task to a stage/column by name",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "project_id": {"type": "integer", "description": "Project ID"},
                "column_name": {"type": "string", "description": "Stage/column name"},
            },
            "required": ["task_id", "project_id", "column_name"],
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

        elif tool_name == "teamwork.tasks.due_today":
            result = await client.list_tasks_due_today(
                assignee_id=args.get("assignee_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.overdue":
            result = await client.list_overdue_tasks(
                assignee_id=args.get("assignee_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.workflows.list":
            result = await client.list_workflows(args["project_id"])
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

        elif tool_name == "teamwork.tasks.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")

            default_project_id = args.get("project_id")
            default_tasklist_id = args.get("tasklist_id")
            default_tag_colors = args.get("tag_colors") or {}

            results = []
            for idx, item in enumerate(items):
                try:
                    project_id = item.get("project_id") or default_project_id
                    tasklist_id = item.get("tasklist_id") or default_tasklist_id
                    if not project_id or not tasklist_id or not item.get("content"):
                        raise ValueError("project_id, tasklist_id and content are required")

                    tag_ids = item.get("tags") or []
                    tag_names = item.get("tag_names") or []
                    tag_colors = item.get("tag_colors") or default_tag_colors
                    if tag_names:
                        resolved = await _ensure_tags(
                            client,
                            names=tag_names,
                            project_id=project_id,
                            color_map=tag_colors,
                        )
                        tag_ids = list({*tag_ids, *resolved})

                    result = await client.create_task(
                        project_id=project_id,
                        tasklist_id=tasklist_id,
                        content=item["content"],
                        description=item.get("description"),
                        assignee_id=item.get("assignee_id"),
                        due_date=item.get("due_date"),
                        priority=item.get("priority"),
                        tags=tag_ids,
                        estimated_minutes=item.get("estimated_minutes"),
                    )
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})

            return ToolResult(success=True, data={"count": len(results), "results": results})

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

        elif tool_name == "teamwork.tasks.bulk_update":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_update")

            default_project_id = args.get("project_id")
            default_tag_colors = args.get("tag_colors") or {}

            results = []
            for idx, item in enumerate(items):
                try:
                    task_id = item.get("task_id")
                    if not task_id:
                        raise ValueError("task_id is required")

                    update_fields = {
                        k: v for k, v in item.items()
                        if k not in ("task_id", "tags", "tag_names", "tag_colors") and v is not None
                    }

                    tag_ids = item.get("tags") or []
                    tag_names = item.get("tag_names") or []
                    if tag_names:
                        project_id = item.get("project_id") or default_project_id
                        resolved = await _ensure_tags(
                            client,
                            names=tag_names,
                            project_id=project_id,
                            color_map=item.get("tag_colors") or default_tag_colors,
                        )
                        tag_ids = list({*tag_ids, *resolved})
                    if tag_ids:
                        update_fields["tags"] = tag_ids

                    result = await client.update_task(task_id, **update_fields)
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})

            return ToolResult(success=True, data={"count": len(results), "results": results})

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
            # Alias for stages.list - uses workflow stages API
            result = await client.list_project_stages(args["project_id"])
            items = _normalize_items(_extract_items(result, ["stages", "stage", "workflowStages"]))
            return ToolResult(success=True, data={"items": items, "raw": result})

        elif tool_name == "teamwork.tasks.move_to_column":
            # Alias for set_stage - uses workflow stages API
            result = await client.move_task_to_stage(
                task_id=args["task_id"],
                stage_id=args["column_id"],
                workflow_id=args.get("workflow_id"),
                project_id=args.get("project_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.move_to_column_by_name":
            # Get stages and find by name
            stages = await client.list_project_stages(args["project_id"])
            workflow_id = stages.get("workflow_id")
            items = _normalize_items(_extract_items(stages, ["stages", "stage", "workflowStages"]))
            matches = _find_by_name(items, args["column_name"])
            if not matches:
                available = [item.get("name") for item in items if item.get("name")]
                raise ValueError(f"Stage/column not found. Available: {available}")
            if len(matches) > 1:
                raise ValueError(f"Multiple stages matched: {[m.get('name') for m in matches]}")
            stage_id = matches[0].get("id")
            if stage_id is None:
                raise ValueError("Stage ID not found for matched stage")
            if not workflow_id:
                raise ValueError("Could not determine workflow_id for this project")
            result = await client.move_task_to_stage(
                task_id=args["task_id"],
                stage_id=stage_id,
                workflow_id=workflow_id,
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.stages.list":
            result = await client.list_project_stages(args["project_id"])
            items = _normalize_items(_extract_items(result, ["stages", "stage", "workflowStages"]))
            return ToolResult(success=True, data={"items": items, "raw": result})

        elif tool_name == "teamwork.tasks.set_stage":
            result = await client.update_task_stage(
                task_id=args["task_id"],
                stage_id=args["stage_id"],
                workflow_id=args.get("workflow_id"),
                project_id=args.get("project_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.set_stage_by_name":
            stages = await client.list_project_stages(args["project_id"])
            workflow_id = stages.get("workflow_id")
            items = _normalize_items(_extract_items(stages, ["stages", "stage", "workflowStages"]))
            matches = _find_by_name(items, args["stage_name"])
            if not matches:
                available = [item.get("name") for item in items if item.get("name")]
                raise ValueError(f"Stage not found. Available: {available}")
            if len(matches) > 1:
                raise ValueError(f"Multiple stages matched: {[m.get('name') for m in matches]}")
            stage_id = matches[0].get("id")
            if stage_id is None:
                raise ValueError("Stage ID not found for matched stage")
            if not workflow_id:
                raise ValueError("Could not determine workflow_id for this project")
            result = await client.move_task_to_stage(
                task_id=args["task_id"],
                stage_id=stage_id,
                workflow_id=workflow_id,
            )
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
