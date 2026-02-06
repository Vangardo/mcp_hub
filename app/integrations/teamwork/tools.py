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
    # ==================== SETUP / DISCOVERY ====================
    # Call these first to get IDs needed for other operations
    ToolDefinition(
        name="teamwork.projects.list",
        description="""List all projects. CALL THIS FIRST to get project_id needed for most operations.
Returns: id, name, description, status for each project.""",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.list",
        description="""List task lists in a project. REQUIRED before creating tasks - you need tasklist_id.
Returns: id, name for each task list.""",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID (from projects.list)"},
            },
            "required": ["project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.people.list",
        description="""List all users. Need user IDs for: assignee_ids, filtering tasks by person.
Returns: id, firstName, lastName, email for each user.""",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.people.me",
        description="Get current user's ID and info. Use for 'assign to me' or 'my tasks'.",
        input_schema={"type": "object", "properties": {}},
    ),

    # ==================== TASKS - READ ====================
    ToolDefinition(
        name="teamwork.tasks.list",
        description="""List tasks with filters. Common filters: project_id, assignee_ids, status, due dates.
For actionable tasks only (not blocked): use include_blocked=false""",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Filter by project"},
                "assignee_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Filter by assignees (user IDs)",
                },
                "status": {
                    "type": "string",
                    "enum": ["all", "active", "completed", "late", "overdue"],
                },
                "due_after": {"type": "string", "description": "Tasks due on/after this date (YYYYMMDD)"},
                "due_before": {"type": "string", "description": "Tasks due on/before this date (YYYYMMDD)"},
                "include_blocked": {
                    "type": "boolean",
                    "description": "true=only blocked, false=only actionable, omit=all",
                },
                "include_dependencies": {
                    "type": "boolean",
                    "description": "Include dependency info (predecessorIds, isBlocked)",
                    "default": False,
                },
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.get",
        description="Get full details of a single task: description, assignees, tags, dates, subtasks count.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.due_today",
        description="Shortcut: get tasks due today.",
        input_schema={
            "type": "object",
            "properties": {
                "assignee_ids": {"type": "array", "items": {"type": "integer"}, "description": "Filter by assignees"},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.overdue",
        description="Shortcut: get overdue tasks (past due date, not completed).",
        input_schema={
            "type": "object",
            "properties": {
                "assignee_ids": {"type": "array", "items": {"type": "integer"}, "description": "Filter by assignees"},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.actionable",
        description="Shortcut: get tasks ready to work on (NOT blocked by dependencies).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "assignee_ids": {"type": "array", "items": {"type": "integer"}},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.blocked",
        description="Shortcut: get blocked tasks (waiting for predecessor tasks to complete).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "assignee_ids": {"type": "array", "items": {"type": "integer"}},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 50},
            },
        },
    ),

    # ==================== TASKS - CREATE/UPDATE ====================
    ToolDefinition(
        name="teamwork.tasks.bulk_create",
        description="""Create up to 10 tasks/subtasks at once. Supports:
- SUBTASKS: use parent_ref="$0" to make subtask of item with temp_id="$0"
- DEPENDENCIES: use predecessor_refs=["$0"] to block until $0 completes

EXAMPLE: {"project_id":1, "tasklist_id":2, "items":[
  {"temp_id":"$0", "content":"Parent"},
  {"temp_id":"$1", "content":"Subtask 1", "parent_ref":"$0"},
  {"content":"Subtask 2 (blocked by 1)", "parent_ref":"$0", "predecessor_refs":["$1"]}
]}""",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Default project ID for all items (from projects.list)"},
                "tasklist_id": {"type": "integer", "description": "Default task list ID for all items (from tasklists.list)"},
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
                            "temp_id": {
                                "type": "string",
                                "description": "Temporary ID for this task (e.g., '$0', '$1'). Used to reference this task in parent_ref or predecessor_refs of other items.",
                            },
                            "parent_task_id": {
                                "type": "integer",
                                "description": "Create as subtask under this existing parent task ID",
                            },
                            "parent_ref": {
                                "type": "string",
                                "description": "Create as subtask under task with this temp_id (e.g., '$0'). The parent must be defined earlier in the items array.",
                            },
                            "project_id": {"type": "integer", "description": "Project ID (overrides default, ignored for subtasks)"},
                            "tasklist_id": {"type": "integer", "description": "Task list ID (overrides default, ignored for subtasks)"},
                            "content": {"type": "string", "description": "Task title/content"},
                            "description": {"type": "string", "description": "Task description"},
                            "assignee_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "User IDs to assign (supports multiple assignees)",
                            },
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
                            "predecessor_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "IDs of existing tasks that must complete before this task",
                            },
                            "predecessor_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Temp IDs of tasks in THIS batch that must complete before this task (e.g., ['$0', '$1'])",
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
        name="teamwork.tasks.bulk_update",
        description="Update up to 10 tasks at once. Pass task_id + fields to change (content, description, assignee_ids, due_date, priority, tags).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Default project ID for tag resolution"},
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
                            "assignee_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "New assignee user IDs (supports multiple assignees)",
                            },
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
    # ==================== TASK LISTS ====================
    ToolDefinition(
        name="teamwork.tasklists.get",
        description="Get single task list details.",
        input_schema={
            "type": "object",
            "properties": {"tasklist_id": {"type": "integer"}},
            "required": ["tasklist_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.create",
        description="Create new task list in a project.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "milestone_id": {"type": "integer"},
                "private": {"type": "boolean", "default": False},
                "pinned": {"type": "boolean", "default": False},
                "add_to_top": {"type": "boolean", "default": False},
            },
            "required": ["project_id", "name"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.update",
        description="Update task list (name, description, pinned, private).",
        input_schema={
            "type": "object",
            "properties": {
                "tasklist_id": {"type": "integer"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "milestone_id": {"type": "integer", "description": "0 to unlink"},
                "private": {"type": "boolean"},
                "pinned": {"type": "boolean"},
            },
            "required": ["tasklist_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.delete",
        description="Delete task list. WARNING: Deletes all tasks in it!",
        input_schema={
            "type": "object",
            "properties": {"tasklist_id": {"type": "integer"}},
            "required": ["tasklist_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.copy",
        description="Copy task list to another project.",
        input_schema={
            "type": "object",
            "properties": {
                "tasklist_id": {"type": "integer"},
                "target_project_id": {"type": "integer"},
                "copy_tasks": {"type": "boolean", "default": True},
            },
            "required": ["tasklist_id", "target_project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.move",
        description="Move task list to another project (with all tasks).",
        input_schema={
            "type": "object",
            "properties": {
                "tasklist_id": {"type": "integer"},
                "target_project_id": {"type": "integer"},
            },
            "required": ["tasklist_id", "target_project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tags.list",
        description="List all tags (id, name, color). Use tags.ensure to assign by name instead of IDs.",
        input_schema={
            "type": "object",
            "properties": {"project_id": {"type": "integer", "description": "Filter by project"}},
        },
    ),
    ToolDefinition(
        name="teamwork.tags.ensure",
        description="Get/create tags by name. PREFERRED for assigning tags - pass names, get IDs back.",
        input_schema={
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}},
                "project_id": {"type": "integer"},
                "tag_colors": {"type": "object", "description": "tag_name -> #RRGGBB"},
            },
            "required": ["names"],
        },
    ),

    # ==================== SUBTASKS ====================
    ToolDefinition(
        name="teamwork.subtasks.create",
        description="Create subtask under existing parent task. For bulk creation with dependencies, use tasks.bulk_create with parent_ref.",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "integer", "description": "Parent task ID"},
                "content": {"type": "string", "description": "Subtask title"},
                "description": {"type": "string"},
                "assignee_ids": {"type": "array", "items": {"type": "integer"}},
                "due_date": {"type": "string", "description": "YYYYMMDD"},
                "estimated_minutes": {"type": "integer"},
            },
            "required": ["parent_task_id", "content"],
        },
    ),
    ToolDefinition(
        name="teamwork.subtasks.list",
        description="List subtasks of a parent task.",
        input_schema={
            "type": "object",
            "properties": {"parent_task_id": {"type": "integer"}},
            "required": ["parent_task_id"],
        },
    ),

    # ==================== TIME TRACKING ====================
    ToolDefinition(
        name="teamwork.time.log",
        description="Log time spent on a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "hours": {"type": "integer"},
                "minutes": {"type": "integer"},
                "date": {"type": "string", "description": "YYYYMMDD"},
                "description": {"type": "string", "description": "Work description"},
                "user_id": {"type": "integer", "description": "Default: current user"},
                "is_billable": {"type": "boolean", "default": False},
            },
            "required": ["task_id", "hours", "minutes", "date"],
        },
    ),
    ToolDefinition(
        name="teamwork.time.list",
        description="List time entries. Filter by task_id, project_id, user_id, date range.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "project_id": {"type": "integer"},
                "user_id": {"type": "integer"},
                "from_date": {"type": "string", "description": "YYYYMMDD"},
                "to_date": {"type": "string", "description": "YYYYMMDD"},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.time.totals",
        description="Get time totals summary for reporting.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "user_id": {"type": "integer"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
            },
        },
    ),

    # ==================== COMMENTS ====================
    ToolDefinition(
        name="teamwork.comments.add",
        description="Add comment to a task. Optionally notify users.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "body": {"type": "string", "description": "Comment text"},
                "notify": {"type": "array", "items": {"type": "integer"}, "description": "User IDs to notify"},
            },
            "required": ["task_id", "body"],
        },
    ),
    ToolDefinition(
        name="teamwork.comments.list",
        description="List comments on a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 50},
            },
            "required": ["task_id"],
        },
    ),

    # ==================== TAGS ====================
    ToolDefinition(
        name="teamwork.tags.create",
        description="Create new tag. Use tags.ensure for auto-create by name.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "color": {"type": "string", "description": "#RRGGBB"},
                "project_id": {"type": "integer", "description": "Omit for global tag"},
            },
            "required": ["name"],
        },
    ),
    ToolDefinition(
        name="teamwork.tags.update",
        description="Update tag name or color.",
        input_schema={
            "type": "object",
            "properties": {
                "tag_id": {"type": "integer"},
                "name": {"type": "string"},
                "color": {"type": "string"},
            },
            "required": ["tag_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tags.delete",
        description="Delete a tag.",
        input_schema={
            "type": "object",
            "properties": {"tag_id": {"type": "integer"}},
            "required": ["tag_id"],
        },
    ),
    # ==================== BOARD / STAGES ====================
    ToolDefinition(
        name="teamwork.stages.list",
        description="List board columns/stages (e.g., 'To Do', 'In Progress', 'Done'). Returns stage names and IDs.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.set_stage_by_name",
        description="Move task to a board column by name. PREFERRED - no need to look up IDs.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "project_id": {"type": "integer", "description": "Project ID"},
                "stage_name": {"type": "string", "description": "Column name: 'To Do', 'In Progress', 'Done', etc."},
            },
            "required": ["task_id", "project_id", "stage_name"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.set_stage",
        description="Move task to a board column by ID (use set_stage_by_name instead if possible).",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "stage_id": {"type": "integer", "description": "From stages.list"},
                "workflow_id": {"type": "integer", "description": "From stages.list"},
                "project_id": {"type": "integer", "description": "Alternative to workflow_id"},
            },
            "required": ["task_id", "stage_id"],
        },
    ),

    # ==================== DEPENDENCIES ====================
    ToolDefinition(
        name="teamwork.dependencies.get",
        description="Get task's dependencies: predecessors (blocks this task), dependents (blocked by this task), isBlocked status.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.dependencies.set",
        description="Set predecessors for a task (REPLACES all existing). Task will be BLOCKED until all predecessors complete. Empty array = unblock.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task to block"},
                "predecessor_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Tasks that must complete first",
                },
            },
            "required": ["task_id", "predecessor_ids"],
        },
    ),
    ToolDefinition(
        name="teamwork.dependencies.add",
        description="Add ONE predecessor (keeps existing). Use when adding to existing dependencies.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task to block"},
                "predecessor_id": {"type": "integer", "description": "Task that must complete first"},
            },
            "required": ["task_id", "predecessor_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.dependencies.remove",
        description="Remove ONE predecessor (unblock partially).",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "predecessor_id": {"type": "integer", "description": "Predecessor to remove"},
            },
            "required": ["task_id", "predecessor_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.dependencies.clear",
        description="Remove ALL predecessors (fully unblock task).",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.dependencies.bulk_set",
        description="""Set dependencies for multiple tasks. Example sequence A->B->C:
{"dependencies":[{"task_id":B,"predecessor_ids":[A]},{"task_id":C,"predecessor_ids":[B]}]}""",
        input_schema={
            "type": "object",
            "properties": {
                "dependencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer"},
                            "predecessor_ids": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["task_id", "predecessor_ids"],
                    },
                },
            },
            "required": ["dependencies"],
        },
    ),

    # ==================== ALIASES (for compatibility) ====================
    # These are kept for backwards compatibility but prefer the main tools above
    ToolDefinition(
        name="teamwork.columns.list",
        description="Alias for stages.list",
        input_schema={"type": "object", "properties": {"project_id": {"type": "integer"}}, "required": ["project_id"]},
    ),
    ToolDefinition(
        name="teamwork.tasks.move_to_column",
        description="Alias for tasks.set_stage",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "column_id": {"type": "integer"},
                "workflow_id": {"type": "integer"},
                "project_id": {"type": "integer"},
            },
            "required": ["task_id", "column_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.move_to_column_by_name",
        description="Alias for tasks.set_stage_by_name",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "project_id": {"type": "integer"},
                "column_name": {"type": "string"},
            },
            "required": ["task_id", "project_id", "column_name"],
        },
    ),
    ToolDefinition(
        name="teamwork.workflows.list",
        description="List workflows (rarely needed - use stages.list instead).",
        input_schema={"type": "object", "properties": {"project_id": {"type": "integer"}}, "required": ["project_id"]},
    ),
]


def _resolve_assignee_ids(args: dict) -> Optional[list[int]]:
    """Extract assignee_ids from args, with backward compat for assignee_id."""
    ids = args.get("assignee_ids")
    if ids:
        return [int(uid) for uid in ids]
    # Backward compat: single assignee_id
    single = args.get("assignee_id")
    if single:
        return [int(single)]
    return None


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

        elif tool_name == "teamwork.people.me":
            if meta and meta.get("user_id"):
                return ToolResult(
                    success=True,
                    data={
                        "user_id": meta.get("user_id"),
                        "first_name": meta.get("first_name"),
                        "last_name": meta.get("last_name"),
                        "email": meta.get("email"),
                        "user_name": meta.get("user_name"),
                        "raw_meta": meta,
                    },
                )
            result = await client.get_current_user()
            person = result.get("person") if isinstance(result, dict) else None
            if isinstance(person, dict):
                return ToolResult(
                    success=True,
                    data={
                        "user_id": person.get("id"),
                        "first_name": person.get("first-name"),
                        "last_name": person.get("last-name"),
                        "email": person.get("email-address"),
                        "user_name": person.get("user-name"),
                        "raw": result,
                    },
                )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.list":
            include_blocked = args.get("include_blocked")
            include_dependencies = args.get("include_dependencies", False)

            # Use V3 API if filtering by blocked status or requesting dependency info
            if include_blocked is not None or include_dependencies:
                result = await client.list_tasks_v3(
                    project_id=args.get("project_id"),
                    assignee_ids=_resolve_assignee_ids(args),
                    include_blocked=include_blocked,
                    include_related_tasks=include_dependencies,
                    page=args.get("page", 1),
                    page_size=args.get("page_size", 50),
                )
            else:
                result = await client.list_tasks(
                    project_id=args.get("project_id"),
                    assignee_ids=_resolve_assignee_ids(args),
                    status=args.get("status"),
                    due_after=args.get("due_after"),
                    due_before=args.get("due_before"),
                    page=args.get("page", 1),
                    page_size=args.get("page_size", 50),
                )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.due_today":
            result = await client.list_tasks_due_today(
                assignee_ids=_resolve_assignee_ids(args),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.overdue":
            result = await client.list_overdue_tasks(
                assignee_ids=_resolve_assignee_ids(args),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.workflows.list":
            result = await client.list_workflows(args["project_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")

            default_project_id = args.get("project_id")
            default_tasklist_id = args.get("tasklist_id")
            default_tag_colors = args.get("tag_colors") or {}

            # Map temp_id -> created task ID for subtask/dependency linking
            temp_id_map: dict[str, int] = {}
            # Items that need predecessor linking after creation
            # (task_id, refs, existing_ids)
            pending_links: list[tuple[int, list[str], list[int]]] = []

            results = []
            for idx, item in enumerate(items):
                try:
                    # Check if this is a subtask
                    parent_task_id = item.get("parent_task_id")
                    parent_ref = item.get("parent_ref")

                    # Resolve parent_ref to actual parent_task_id
                    if parent_ref:
                        if parent_ref not in temp_id_map:
                            raise ValueError(
                                f"parent_ref '{parent_ref}' not found. "
                                f"Parent task must be defined earlier in items array. "
                                f"Available temp_ids: {list(temp_id_map.keys())}"
                            )
                        parent_task_id = temp_id_map[parent_ref]

                    is_subtask = parent_task_id is not None

                    # For subtasks, we don't need project_id/tasklist_id
                    if is_subtask:
                        result = await client.create_subtask(
                            parent_task_id=int(parent_task_id),
                            content=item["content"],
                            description=item.get("description"),
                            assignee_ids=_resolve_assignee_ids(item),
                            due_date=item.get("due_date"),
                            estimated_minutes=item.get("estimated_minutes"),
                        )
                    else:
                        # Regular task - needs project_id and tasklist_id
                        project_id = item.get("project_id") or default_project_id
                        tasklist_id = item.get("tasklist_id") or default_tasklist_id
                        if project_id is not None:
                            project_id = int(project_id)
                        if tasklist_id is not None:
                            tasklist_id = int(tasklist_id)
                        if not project_id or not tasklist_id:
                            raise ValueError("project_id and tasklist_id required for regular tasks (use parent_ref for subtasks)")
                        if not item.get("content"):
                            raise ValueError("content is required")

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
                            tasklist_id=tasklist_id,
                            content=item["content"],
                            description=item.get("description"),
                            assignee_ids=_resolve_assignee_ids(item),
                            due_date=item.get("due_date"),
                            priority=item.get("priority"),
                            tags=tag_ids,
                            estimated_minutes=item.get("estimated_minutes"),
                        )

                    # Extract created task ID
                    created_id = None
                    if isinstance(result, dict):
                        # V1 API returns {"id": "123"} or {"todo-item": {"id": ...}}
                        if "id" in result:
                            created_id = int(result["id"])
                        elif "todo-item" in result:
                            created_id = int(result["todo-item"].get("id", 0))

                    # Store temp_id mapping
                    temp_id = item.get("temp_id")
                    if temp_id and created_id:
                        temp_id_map[temp_id] = created_id

                    # Queue predecessor refs for later linking
                    predecessor_refs = item.get("predecessor_refs") or []
                    predecessor_ids = item.get("predecessor_ids") or []
                    if created_id and (predecessor_refs or predecessor_ids):
                        pending_links.append((created_id, predecessor_refs, predecessor_ids))

                    results.append({
                        "index": idx,
                        "success": True,
                        "data": result,
                        "task_id": created_id,
                        "temp_id": temp_id,
                        "is_subtask": is_subtask,
                        "parent_task_id": parent_task_id if is_subtask else None,
                    })
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})

            # Second pass: set up dependencies using temp_id mappings
            dependency_results = []
            for task_id, refs, existing_ids in pending_links:
                try:
                    # Resolve temp_id refs to actual task IDs
                    all_predecessor_ids = list(existing_ids) if existing_ids else []
                    unresolved_refs = []
                    for ref in refs:
                        if ref in temp_id_map:
                            all_predecessor_ids.append(temp_id_map[ref])
                        else:
                            unresolved_refs.append(ref)

                    if unresolved_refs:
                        dependency_results.append({
                            "task_id": task_id,
                            "success": False,
                            "error": f"Unknown temp_id references: {unresolved_refs}",
                        })
                        continue

                    if all_predecessor_ids:
                        # V1 API with {id, type} format
                        dep_result = await client.set_task_predecessors(task_id, all_predecessor_ids)
                        dependency_results.append({
                            "task_id": task_id,
                            "success": True,
                            "predecessors": all_predecessor_ids,
                            "api_response": dep_result,
                        })
                except Exception as exc:
                    dependency_results.append({
                        "task_id": task_id,
                        "success": False,
                        "error": str(exc),
                    })

            return ToolResult(success=True, data={
                "count": len(results),
                "results": results,
                "temp_id_map": temp_id_map,
                "dependencies_set": dependency_results,
            })

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
                        if k not in ("task_id", "assignee_id", "assignee_ids", "tags", "tag_names", "tag_colors") and v is not None
                    }
                    # Resolve assignee_ids
                    resolved_assignees = _resolve_assignee_ids(item)
                    if resolved_assignees:
                        update_fields["assignee_ids"] = resolved_assignees

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

        elif tool_name == "teamwork.tasklists.get":
            result = await client.get_tasklist(args["tasklist_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.create":
            result = await client.create_tasklist(
                project_id=args["project_id"],
                name=args["name"],
                description=args.get("description"),
                milestone_id=args.get("milestone_id"),
                private=args.get("private", False),
                pinned=args.get("pinned", False),
                add_to_top=args.get("add_to_top", False),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.update":
            result = await client.update_tasklist(
                tasklist_id=args["tasklist_id"],
                name=args.get("name"),
                description=args.get("description"),
                milestone_id=args.get("milestone_id"),
                private=args.get("private"),
                pinned=args.get("pinned"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.delete":
            result = await client.delete_tasklist(args["tasklist_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.copy":
            result = await client.copy_tasklist(
                tasklist_id=args["tasklist_id"],
                target_project_id=args["target_project_id"],
                copy_tasks=args.get("copy_tasks", True),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.move":
            result = await client.move_tasklist(
                tasklist_id=args["tasklist_id"],
                target_project_id=args["target_project_id"],
            )
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
                assignee_ids=_resolve_assignee_ids(args),
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

        # === DEPENDENCIES ===
        elif tool_name == "teamwork.tasks.actionable":
            # Shortcut for getting unblocked tasks
            result = await client.list_tasks_v3(
                project_id=args.get("project_id"),
                assignee_ids=_resolve_assignee_ids(args),
                include_blocked=False,
                include_related_tasks=True,
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.blocked":
            # Shortcut for getting blocked tasks
            result = await client.list_tasks_v3(
                project_id=args.get("project_id"),
                assignee_ids=_resolve_assignee_ids(args),
                include_blocked=True,
                include_related_tasks=True,
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.dependencies.get":
            # Get full dependency info for a task
            task_data = await client.get_task_with_dependencies(args["task_id"])
            task = task_data.get("task", {})

            # Also get predecessors via V1 for more detail
            predecessors_data = await client.get_task_predecessors(args["task_id"])
            dependencies_data = await client.get_task_dependencies(args["task_id"])

            return ToolResult(success=True, data={
                "task_id": args["task_id"],
                "isBlocked": task.get("isBlocked", False),
                "predecessorIds": task.get("predecessorIds", []),
                "dependencyIds": task.get("dependencyIds", []),
                "predecessors_detail": predecessors_data,
                "dependencies_detail": dependencies_data,
            })

        elif tool_name == "teamwork.dependencies.set":
            predecessor_ids = args.get("predecessor_ids") or []
            # V3 API uses simple predecessorIds array (type not supported via API)
            result = await client.set_task_predecessors(args["task_id"], predecessor_ids)
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.dependencies.add":
            result = await client.add_predecessor(
                task_id=args["task_id"],
                predecessor_id=args["predecessor_id"],
                predecessor_type=args.get("predecessor_type", "start"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.dependencies.remove":
            result = await client.remove_predecessor(
                task_id=args["task_id"],
                predecessor_id=args["predecessor_id"],
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.dependencies.clear":
            result = await client.clear_predecessors(args["task_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.dependencies.bulk_set":
            dependencies_list = args.get("dependencies") or []
            if len(dependencies_list) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_set")

            results = []
            for dep in dependencies_list:
                try:
                    task_id = dep["task_id"]
                    predecessor_ids = dep.get("predecessor_ids") or []
                    # V3 API uses simple predecessorIds array
                    result = await client.set_task_predecessors(task_id, predecessor_ids)
                    results.append({
                        "task_id": task_id,
                        "success": True,
                        "predecessors": predecessor_ids,
                    })
                except Exception as exc:
                    results.append({
                        "task_id": dep.get("task_id"),
                        "success": False,
                        "error": str(exc),
                    })

            return ToolResult(success=True, data={"results": results})

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
