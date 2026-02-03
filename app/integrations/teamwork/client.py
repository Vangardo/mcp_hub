from typing import Optional, Any
import httpx


class TeamworkClient:
    def __init__(self, access_token: str, site_url: str):
        self.access_token = access_token
        self.base_url = site_url.rstrip("/")

    def _headers(self) -> dict:
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
        url = f"{self.base_url}{endpoint}"
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

            # Handle empty response (204 No Content or empty body)
            if response.status_code == 204 or not response.content:
                return {"success": True, "status_code": response.status_code}

            # Try to parse JSON
            try:
                return response.json()
            except Exception:
                # If JSON parsing fails, return raw text
                return {"success": True, "status_code": response.status_code, "text": response.text}

    async def list_projects(self, page: int = 1, page_size: int = 50) -> dict:
        return await self._request(
            "GET",
            "/projects.json",
            params={"page": page, "pageSize": page_size},
        )

    async def list_people(self, page: int = 1, page_size: int = 50) -> dict:
        return await self._request(
            "GET",
            "/people.json",
            params={"page": page, "pageSize": page_size},
        )

    async def list_tasks(
        self,
        project_id: Optional[int] = None,
        assignee_ids: Optional[list[int]] = None,
        status: Optional[str] = None,
        due_after: Optional[str] = None,
        due_before: Optional[str] = None,
        include_today: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "pageSize": page_size}

        if project_id:
            params["projectId"] = project_id
        if assignee_ids:
            params["responsible-party-ids"] = ",".join(str(uid) for uid in assignee_ids)
        if status:
            params["filter"] = status
        # Teamwork uses different date filter params
        if due_after:
            params["dueDateFrom"] = due_after
        if due_before:
            params["dueDateTo"] = due_before
        if include_today:
            params["includeToday"] = "true"
        # Include completed optionally
        params["includeCompletedTasks"] = "false"

        return await self._request("GET", "/tasks.json", params=params)

    async def list_tasks_due_today(self, assignee_ids: Optional[list[int]] = None) -> dict:
        """Get tasks due today"""
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        return await self.list_tasks(
            due_after=today,
            due_before=today,
            assignee_ids=assignee_ids,
            include_today=True,
        )

    async def list_overdue_tasks(self, assignee_ids: Optional[list[int]] = None) -> dict:
        """Get overdue tasks"""
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        params: dict[str, Any] = {
            "filter": "overdue",
            "includeCompletedTasks": "false",
        }
        if assignee_ids:
            params["responsible-party-ids"] = ",".join(str(uid) for uid in assignee_ids)
        return await self._request("GET", "/tasks.json", params=params)

    async def create_task(
        self,
        project_id: int,
        tasklist_id: int,
        content: str,
        description: Optional[str] = None,
        assignee_ids: Optional[list[int]] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[list[int]] = None,
        estimated_minutes: Optional[int] = None,
    ) -> dict:
        task_data: dict[str, Any] = {"content": content}

        if description:
            task_data["description"] = description
        if assignee_ids:
            task_data["responsible-party-ids"] = ",".join(str(uid) for uid in assignee_ids)
        if due_date:
            task_data["due-date"] = due_date
        if priority:
            task_data["priority"] = priority
        if tags:
            # Teamwork API expects tagIds (comma-separated)
            task_data["tagIds"] = ",".join(str(t) for t in tags)
        if estimated_minutes:
            task_data["estimated-minutes"] = estimated_minutes

        return await self._request(
            "POST",
            f"/tasklists/{tasklist_id}/tasks.json",
            json_data={"todo-item": task_data},
        )

    async def update_task(self, task_id: int, **fields) -> dict:
        # Assignees must go through V3 PATCH — V1 PUT adds instead of replacing
        assignee_ids = fields.pop("assignee_ids", None)

        task_data = {}
        if "content" in fields:
            task_data["content"] = fields["content"]
        if "description" in fields:
            task_data["description"] = fields["description"]
        if "due_date" in fields:
            task_data["due-date"] = fields["due_date"]
        if "priority" in fields:
            task_data["priority"] = fields["priority"]
        if "tags" in fields:
            task_data["tagIds"] = ",".join(str(t) for t in fields["tags"])
        if "estimated_minutes" in fields:
            task_data["estimated-minutes"] = fields["estimated_minutes"]

        result = {}
        # V1 PUT for non-assignee fields
        if task_data:
            result = await self._request(
                "PUT",
                f"/tasks/{task_id}.json",
                json_data={"todo-item": task_data},
            )

        # V3 PATCH for assignees — properly replaces the full list
        if assignee_ids is not None:
            result = await self._request(
                "PATCH",
                f"/projects/api/v3/tasks/{task_id}.json",
                json_data={
                    "task": {
                        "assignees": {
                            "userIds": assignee_ids,
                        },
                    },
                },
            )

        return result or {"STATUS": "OK"}

    async def complete_task(self, task_id: int) -> dict:
        return await self._request("PUT", f"/tasks/{task_id}/complete.json")

    async def get_tasklists(self, project_id: int) -> dict:
        return await self._request(
            "GET", f"/projects/{project_id}/tasklists.json"
        )

    async def list_tags(self, project_id: Optional[int] = None) -> dict:
        """List all tags, optionally filtered by project"""
        if project_id:
            try:
                return await self._request(
                    "GET", f"/projects/{project_id}/tags.json"
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 404):
                    return await self._request(
                        "GET",
                        "/projects/api/v3/tags.json",
                        params={"projectId": project_id},
                    )
                raise
        try:
            return await self._request("GET", "/tags.json")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                return await self._request("GET", "/projects/api/v3/tags.json")
            raise

    async def get_task(self, task_id: int) -> dict:
        """Get single task details"""
        return await self._request("GET", f"/tasks/{task_id}.json")

    # === SUBTASKS ===
    async def create_subtask(
        self,
        parent_task_id: int,
        content: str,
        description: Optional[str] = None,
        assignee_ids: Optional[list[int]] = None,
        due_date: Optional[str] = None,
        estimated_minutes: Optional[int] = None,
    ) -> dict:
        """Create a subtask under a parent task"""
        task_data: dict[str, Any] = {"content": content}
        if description:
            task_data["description"] = description
        if assignee_ids:
            task_data["responsible-party-ids"] = ",".join(str(uid) for uid in assignee_ids)
        if due_date:
            task_data["due-date"] = due_date
        if estimated_minutes:
            task_data["estimated-minutes"] = estimated_minutes

        return await self._request(
            "POST",
            f"/tasks/{parent_task_id}.json",
            json_data={"todo-item": task_data},
        )

    async def list_subtasks(self, parent_task_id: int) -> dict:
        """List subtasks of a task"""
        return await self._request("GET", f"/tasks/{parent_task_id}/subtasks.json")

    # === TIME ENTRIES ===
    async def log_time(
        self,
        task_id: int,
        hours: int,
        minutes: int,
        date: str,
        description: Optional[str] = None,
        user_id: Optional[int] = None,
        is_billable: bool = False,
    ) -> dict:
        """Log time entry for a task"""
        time_data: dict[str, Any] = {
            "hours": str(hours),
            "minutes": str(minutes),
            "date": date,
            "isbillable": "1" if is_billable else "0",
        }
        if description:
            time_data["description"] = description
        if user_id:
            time_data["person-id"] = str(user_id)

        return await self._request(
            "POST",
            f"/tasks/{task_id}/time_entries.json",
            json_data={"time-entry": time_data},
        )

    async def list_time_entries(
        self,
        task_id: Optional[int] = None,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """List time entries with optional filters"""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}

        if from_date:
            params["fromdate"] = from_date
        if to_date:
            params["todate"] = to_date
        if user_id:
            params["userId"] = user_id

        if task_id:
            return await self._request("GET", f"/tasks/{task_id}/time_entries.json", params=params)
        elif project_id:
            return await self._request("GET", f"/projects/{project_id}/time_entries.json", params=params)
        else:
            return await self._request("GET", "/time_entries.json", params=params)

    async def get_time_totals(
        self,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict:
        """Get time totals summary"""
        params: dict[str, Any] = {}
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date
        if user_id:
            params["userId"] = user_id
        if project_id:
            params["projectId"] = project_id

        return await self._request("GET", "/time/total.json", params=params)

    # === COMMENTS ===
    async def add_comment(
        self,
        task_id: int,
        body: str,
        notify: Optional[list[int]] = None,
    ) -> dict:
        """Add a comment to a task"""
        comment_data: dict[str, Any] = {
            "body": body,
            "content-type": "text",
        }
        if notify:
            comment_data["notify"] = ",".join(str(u) for u in notify)

        return await self._request(
            "POST",
            f"/tasks/{task_id}/comments.json",
            json_data={"comment": comment_data},
        )

    async def list_comments(self, task_id: int, page: int = 1, page_size: int = 50) -> dict:
        """List comments for a task"""
        return await self._request(
            "GET",
            f"/tasks/{task_id}/comments.json",
            params={"page": page, "pageSize": page_size},
        )

    # === TAGS MANAGEMENT ===
    async def create_tag(
        self,
        name: str,
        color: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> dict:
        """Create a new tag. Color format: #RRGGBB"""
        tag_data: dict[str, Any] = {"name": name}
        if color:
            tag_data["color"] = color

        if project_id:
            try:
                return await self._request(
                    "POST",
                    f"/projects/{project_id}/tags.json",
                    json_data={"tag": tag_data},
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 404):
                    tag_data["projectId"] = project_id
                    return await self._request(
                        "POST",
                        "/projects/api/v3/tags.json",
                        json_data={"tag": tag_data},
                    )
                raise
        try:
            return await self._request(
                "POST",
                "/tags.json",
                json_data={"tag": tag_data},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                return await self._request(
                    "POST",
                    "/projects/api/v3/tags.json",
                    json_data={"tag": tag_data},
                )
            raise

    async def update_tag(
        self,
        tag_id: int,
        name: Optional[str] = None,
        color: Optional[str] = None,
    ) -> dict:
        """Update an existing tag"""
        tag_data: dict[str, Any] = {}
        if name:
            tag_data["name"] = name
        if color:
            tag_data["color"] = color

        try:
            return await self._request(
                "PUT",
                f"/tags/{tag_id}.json",
                json_data={"tag": tag_data},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                return await self._request(
                    "PUT",
                    f"/projects/api/v3/tags/{tag_id}.json",
                    json_data={"tag": tag_data},
                )
            raise

    async def delete_tag(self, tag_id: int) -> dict:
        """Delete a tag"""
        try:
            return await self._request("DELETE", f"/tags/{tag_id}.json")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                return await self._request(
                    "DELETE",
                    f"/projects/api/v3/tags/{tag_id}.json",
                )
            raise

    # === WORKFLOWS / STAGES ===
    # Teamwork использует Workflows API для board view
    # https://apidocs.teamwork.com/guides/teamwork/workflows-api-getting-started-guide

    async def list_workflows(self, project_id: int) -> dict:
        """List all workflows in a project"""
        return await self._request(
            "GET",
            f"/projects/api/v3/projects/{project_id}/workflows.json",
        )

    async def get_workflow_stages(self, workflow_id: int) -> dict:
        """Get stages for a specific workflow"""
        return await self._request(
            "GET",
            f"/projects/api/v3/workflows/{workflow_id}/stages.json",
        )

    async def list_project_stages(self, project_id: int) -> dict:
        """List all stages (columns) for a project's workflow.

        Returns stages with workflow_id included for use in move operations.
        """
        # Сначала получаем workflows проекта
        workflows = await self.list_workflows(project_id)

        # Извлекаем workflow ID
        workflow_list = workflows.get("workflows", [])
        if not workflow_list:
            # Попробуем другой формат ответа
            workflow_list = workflows.get("data", [])

        if not workflow_list:
            return {"stages": [], "workflow_id": None, "message": "No workflows found for this project"}

        # Берём первый (обычно единственный) workflow
        workflow_id = None
        if isinstance(workflow_list, list) and workflow_list:
            workflow_id = workflow_list[0].get("id")
        elif isinstance(workflow_list, dict):
            workflow_id = workflow_list.get("id")

        if not workflow_id:
            return {"stages": [], "workflow_id": None, "message": "Could not find workflow ID"}

        # Получаем stages этого workflow
        stages_result = await self.get_workflow_stages(workflow_id)

        # Добавляем workflow_id в результат для удобства
        stages_result["workflow_id"] = workflow_id
        return stages_result

    async def list_columns(self, project_id: int) -> dict:
        """Alias for list_project_stages"""
        return await self.list_project_stages(project_id)

    async def get_task_with_stage(self, task_id: int) -> dict:
        """Get task details including workflow stage info (API v3)"""
        return await self._request(
            "GET",
            f"/projects/api/v3/tasks/{task_id}.json",
        )

    async def move_task_to_stage(
        self,
        task_id: int,
        stage_id: int,
        workflow_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> dict:
        """Move a task to a different workflow stage.

        Uses POST /projects/api/v3/workflows/{workflowId}/stages/{stageId}/tasks.json
        with body: {"taskIds": [taskId]}

        This is the correct endpoint for actually moving cards on the board!
        """
        # Если workflow_id не передан, нужно его получить
        if not workflow_id:
            if project_id:
                workflows = await self.list_workflows(project_id)
                workflow_list = workflows.get("workflows", []) or workflows.get("data", [])
                if workflow_list:
                    workflow_id = workflow_list[0].get("id")

            if not workflow_id:
                raise ValueError("workflow_id is required. Get it from workflows.list first.")

        # POST к stages endpoint - это реально двигает карточки!
        return await self._request(
            "POST",
            f"/projects/api/v3/workflows/{workflow_id}/stages/{stage_id}/tasks.json",
            json_data={
                "taskIds": [task_id],
            },
        )

    async def move_tasks_to_stage(
        self,
        task_ids: list[int],
        stage_id: int,
        workflow_id: int,
    ) -> dict:
        """Move multiple tasks to a workflow stage at once"""
        # Для нескольких задач используем POST к stages endpoint
        return await self._request(
            "POST",
            f"/projects/api/v3/workflows/{workflow_id}/stages/{stage_id}/tasks.json",
            json_data={
                "taskIds": task_ids,
            },
        )

    async def update_task_stage(self, task_id: int, stage_id: int, workflow_id: Optional[int] = None, project_id: Optional[int] = None) -> dict:
        """Update task's workflow stage (alias for move_task_to_stage)"""
        return await self.move_task_to_stage(task_id, stage_id, workflow_id, project_id)

    # Aliases для совместимости
    async def list_boards(self, project_id: int) -> dict:
        """Alias - в Teamwork это называется workflows"""
        return await self.list_workflows(project_id)

    async def move_task_to_column(self, task_id: int, column_id: int) -> dict:
        """Alias - columns это stages в workflows"""
        return await self.move_task_to_stage(task_id, column_id)
