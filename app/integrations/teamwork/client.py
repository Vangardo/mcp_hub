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
            return response.json()

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
        assignee_id: Optional[int] = None,
        status: Optional[str] = None,
        due_after: Optional[str] = None,
        due_before: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "pageSize": page_size}

        if project_id:
            params["projectId"] = project_id
        if assignee_id:
            params["responsiblePartyId"] = assignee_id
        if status:
            params["filter"] = status
        if due_after:
            params["startDate"] = due_after
        if due_before:
            params["endDate"] = due_before

        return await self._request("GET", "/tasks.json", params=params)

    async def create_task(
        self,
        project_id: int,
        tasklist_id: int,
        content: str,
        description: Optional[str] = None,
        assignee_id: Optional[int] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[list[int]] = None,
        estimated_minutes: Optional[int] = None,
    ) -> dict:
        task_data: dict[str, Any] = {"content": content}

        if description:
            task_data["description"] = description
        if assignee_id:
            task_data["responsible-party-id"] = str(assignee_id)
        if due_date:
            task_data["due-date"] = due_date
        if priority:
            task_data["priority"] = priority
        if tags:
            task_data["tag-ids"] = ",".join(str(t) for t in tags)
        if estimated_minutes:
            task_data["estimated-minutes"] = estimated_minutes

        return await self._request(
            "POST",
            f"/tasklists/{tasklist_id}/tasks.json",
            json_data={"todo-item": task_data},
        )

    async def update_task(self, task_id: int, **fields) -> dict:
        task_data = {}
        if "content" in fields:
            task_data["content"] = fields["content"]
        if "description" in fields:
            task_data["description"] = fields["description"]
        if "assignee_id" in fields:
            task_data["responsible-party-id"] = str(fields["assignee_id"])
        if "due_date" in fields:
            task_data["due-date"] = fields["due_date"]
        if "priority" in fields:
            task_data["priority"] = fields["priority"]
        if "tags" in fields:
            task_data["tag-ids"] = ",".join(str(t) for t in fields["tags"])
        if "estimated_minutes" in fields:
            task_data["estimated-minutes"] = fields["estimated_minutes"]

        return await self._request(
            "PUT",
            f"/tasks/{task_id}.json",
            json_data={"todo-item": task_data},
        )

    async def complete_task(self, task_id: int) -> dict:
        return await self._request("PUT", f"/tasks/{task_id}/complete.json")

    async def get_tasklists(self, project_id: int) -> dict:
        return await self._request(
            "GET", f"/projects/{project_id}/tasklists.json"
        )

    async def list_tags(self, project_id: Optional[int] = None) -> dict:
        """List all tags, optionally filtered by project"""
        if project_id:
            return await self._request(
                "GET", f"/projects/{project_id}/tags.json"
            )
        return await self._request("GET", "/tags.json")

    async def get_task(self, task_id: int) -> dict:
        """Get single task details"""
        return await self._request("GET", f"/tasks/{task_id}.json")

    # === SUBTASKS ===
    async def create_subtask(
        self,
        parent_task_id: int,
        content: str,
        description: Optional[str] = None,
        assignee_id: Optional[int] = None,
        due_date: Optional[str] = None,
        estimated_minutes: Optional[int] = None,
    ) -> dict:
        """Create a subtask under a parent task"""
        task_data: dict[str, Any] = {"content": content}
        if description:
            task_data["description"] = description
        if assignee_id:
            task_data["responsible-party-id"] = str(assignee_id)
        if due_date:
            task_data["due-date"] = due_date
        if estimated_minutes:
            task_data["estimated-minutes"] = estimated_minutes

        return await self._request(
            "POST",
            f"/tasks/{parent_task_id}/subtasks.json",
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
