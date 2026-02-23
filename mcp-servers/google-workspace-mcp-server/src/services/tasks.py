"""Google Tasks service tools."""

import logging
from typing import Optional
from datetime import datetime, timezone

import dateparser
from mcp.server.fastmcp import FastMCP

from ..auth import get_tasks_service
from ..cache import cache

logger = logging.getLogger(__name__)


def parse_datetime(date_str: str) -> Optional[str]:
    """Parse a date string to RFC 3339 format for Google Tasks API."""
    if not date_str:
        return None
    dt = dateparser.parse(date_str)
    if dt:
        return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    return None


def register_tools(mcp: FastMCP):
    """Register all Tasks tools on the shared MCP server."""

    @mcp.tool()
    def list_tasklists() -> str:
        """List all task lists for the authenticated user."""
        service = get_tasks_service()
        try:
            results = service.tasklists().list(maxResults=100).execute()
            tasklists = results.get('items', [])
            if not tasklists:
                return "No task lists found."
            output = ["--- Task Lists ---"]
            for tl in tasklists:
                updated = tl.get('updated', 'Unknown')
                output.append(f"ID: {tl['id']}\nTitle: {tl['title']}\nUpdated: {updated}\n---")
            return "\n".join(output)
        except Exception as e:
            return f"Error listing task lists: {str(e)}"

    @mcp.tool()
    def get_tasklist(tasklist_id: str) -> str:
        """
        Get detailed information about a specific task list.

        Args:
            tasklist_id: The task list ID (from list_tasklists).
        """
        service = get_tasks_service()
        try:
            tl = service.tasklists().get(tasklist=tasklist_id).execute()
            return f"""Task List Details:
ID: {tl['id']}
Title: {tl['title']}
Updated: {tl.get('updated', 'Unknown')}
Self Link: {tl.get('selfLink', 'N/A')}"""
        except Exception as e:
            return f"Error getting task list '{tasklist_id}': {str(e)}"

    @mcp.tool()
    def create_tasklist(title: str) -> str:
        """
        Create a new task list.

        Args:
            title: The title for the new task list.
        """
        service = get_tasks_service()
        try:
            result = service.tasklists().insert(body={'title': title}).execute()
            return f"Task list created successfully!\nID: {result['id']}\nTitle: {result['title']}"
        except Exception as e:
            return f"Error creating task list '{title}': {str(e)}"

    @mcp.tool()
    def update_tasklist(tasklist_id: str, title: str) -> str:
        """
        Update a task list's title.

        Args:
            tasklist_id: The task list ID to update.
            title: The new title for the task list.
        """
        service = get_tasks_service()
        try:
            result = service.tasklists().update(tasklist=tasklist_id, body={'title': title}).execute()
            return f"Task list updated successfully!\nID: {result['id']}\nTitle: {result['title']}"
        except Exception as e:
            return f"Error updating task list '{tasklist_id}': {str(e)}"

    @mcp.tool()
    def delete_tasklist(tasklist_id: str) -> str:
        """
        Delete a task list. WARNING: This also deletes all tasks in the list.

        Args:
            tasklist_id: The task list ID to delete.
        """
        service = get_tasks_service()
        try:
            service.tasklists().delete(tasklist=tasklist_id).execute()
            return f"Task list '{tasklist_id}' deleted successfully."
        except Exception as e:
            return f"Error deleting task list '{tasklist_id}': {str(e)}"

    @mcp.tool()
    def list_tasks(
        tasklist_id: str = "@default",
        show_completed: bool = False,
        show_hidden: bool = False,
        due_min: str = None,
        due_max: str = None,
        max_results: int = 100
    ) -> str:
        """
        List tasks in a task list with optional filters.

        Args:
            tasklist_id: The task list ID (use '@default' for the default list).
            show_completed: Whether to include completed tasks.
            show_hidden: Whether to include hidden tasks.
            due_min: Minimum due date filter (e.g., 'today', '2024-01-01').
            due_max: Maximum due date filter (e.g., 'next week', '2024-12-31').
            max_results: Maximum number of tasks to return (default 100).
        """
        service = get_tasks_service()
        try:
            params = {
                'tasklist': tasklist_id,
                'maxResults': max_results,
                'showCompleted': show_completed,
                'showHidden': show_hidden
            }
            if due_min:
                parsed = parse_datetime(due_min)
                if parsed:
                    params['dueMin'] = parsed
            if due_max:
                parsed = parse_datetime(due_max)
                if parsed:
                    params['dueMax'] = parsed

            results = service.tasks().list(**params).execute()
            tasks = results.get('items', [])
            if not tasks:
                return "No tasks found."
            output = [f"--- Tasks in {tasklist_id} ---"]
            for task in tasks:
                status_icon = "\u2713" if task.get('status') == 'completed' else "\u25CB"
                due = task.get('due', 'No due date')
                if due != 'No due date':
                    try:
                        due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
                        due = due_dt.strftime('%Y-%m-%d')
                    except Exception:
                        pass
                notes = task.get('notes', '')
                notes_preview = f"\n   Notes: {notes[:50]}..." if notes and len(notes) > 50 else f"\n   Notes: {notes}" if notes else ""
                output.append(f"""{status_icon} {task['title']}
   ID: {task['id']}
   Status: {task.get('status', 'needsAction')}
   Due: {due}{notes_preview}
---""")
            return "\n".join(output)
        except Exception as e:
            return f"Error listing tasks: {str(e)}"

    @mcp.tool()
    def get_task(tasklist_id: str, task_id: str) -> str:
        """
        Get detailed information about a specific task.

        Args:
            tasklist_id: The task list ID.
            task_id: The task ID.
        """
        service = get_tasks_service()
        try:
            task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
            due = task.get('due', 'No due date')
            if due != 'No due date':
                try:
                    due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
                    due = due_dt.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pass
            completed = task.get('completed', 'N/A')
            if completed != 'N/A':
                try:
                    comp_dt = datetime.fromisoformat(completed.replace('Z', '+00:00'))
                    completed = comp_dt.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pass
            return f"""Task Details:
ID: {task['id']}
Title: {task['title']}
Status: {task.get('status', 'needsAction')}
Due: {due}
Completed: {completed}
Notes: {task.get('notes', '(No notes)')}
Updated: {task.get('updated', 'Unknown')}
Parent: {task.get('parent', 'None (top-level)')}
Position: {task.get('position', 'N/A')}"""
        except Exception as e:
            return f"Error getting task '{task_id}': {str(e)}"

    @mcp.tool()
    def create_task(
        title: str,
        tasklist_id: str = "@default",
        notes: str = None,
        due: str = None,
        parent: str = None,
        previous: str = None
    ) -> str:
        """
        Create a new task with optional due date, notes, and positioning.

        Args:
            title: The title of the task.
            tasklist_id: The task list ID (use '@default' for the default list).
            notes: Optional notes/description for the task.
            due: Optional due date (e.g., 'tomorrow', '2024-12-25', 'next Friday').
            parent: Optional parent task ID to create a subtask.
            previous: Optional previous sibling task ID for positioning.
        """
        service = get_tasks_service()
        try:
            task_body = {'title': title}
            if notes:
                task_body['notes'] = notes
            if due:
                parsed_due = parse_datetime(due)
                if parsed_due:
                    task_body['due'] = parsed_due
            params = {'tasklist': tasklist_id, 'body': task_body}
            if parent:
                params['parent'] = parent
            if previous:
                params['previous'] = previous
            result = service.tasks().insert(**params).execute()
            due_str = result.get('due', 'No due date')
            if due_str != 'No due date':
                try:
                    due_dt = datetime.fromisoformat(due_str.replace('Z', '+00:00'))
                    due_str = due_dt.strftime('%Y-%m-%d')
                except Exception:
                    pass
            return f"""Task created successfully!
ID: {result['id']}
Title: {result['title']}
Due: {due_str}
Notes: {result.get('notes', '(No notes)')}
Status: {result.get('status', 'needsAction')}"""
        except Exception as e:
            return f"Error creating task '{title}': {str(e)}"

    @mcp.tool()
    def update_task(
        tasklist_id: str,
        task_id: str,
        title: str = None,
        notes: str = None,
        due: str = None,
        status: str = None
    ) -> str:
        """
        Update an existing task's title, notes, due date, or status.

        Args:
            tasklist_id: The task list ID.
            task_id: The task ID to update.
            title: New title for the task.
            notes: New notes for the task.
            due: New due date. Use 'none' to clear.
            status: New status - 'needsAction' or 'completed'.
        """
        service = get_tasks_service()
        try:
            current = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
            if title is not None:
                current['title'] = title
            if notes is not None:
                current['notes'] = notes
            if due is not None:
                if due.lower() == 'none':
                    current.pop('due', None)
                else:
                    parsed_due = parse_datetime(due)
                    if parsed_due:
                        current['due'] = parsed_due
            if status is not None:
                current['status'] = status
                if status == 'completed':
                    current['completed'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                else:
                    current.pop('completed', None)
            result = service.tasks().update(tasklist=tasklist_id, task=task_id, body=current).execute()
            return f"""Task updated successfully!
ID: {result['id']}
Title: {result['title']}
Status: {result.get('status', 'needsAction')}
Due: {result.get('due', 'No due date')}
Notes: {result.get('notes', '(No notes)')}"""
        except Exception as e:
            return f"Error updating task '{task_id}': {str(e)}"

    @mcp.tool()
    def complete_task(tasklist_id: str, task_id: str) -> str:
        """
        Mark a task as completed.

        Args:
            tasklist_id: The task list ID.
            task_id: The task ID to complete.
        """
        service = get_tasks_service()
        try:
            current = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
            current['status'] = 'completed'
            current['completed'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            result = service.tasks().update(tasklist=tasklist_id, task=task_id, body=current).execute()
            return f"Task '{result['title']}' marked as completed!"
        except Exception as e:
            return f"Error completing task '{task_id}': {str(e)}"

    @mcp.tool()
    def uncomplete_task(tasklist_id: str, task_id: str) -> str:
        """
        Mark a completed task as incomplete.

        Args:
            tasklist_id: The task list ID.
            task_id: The task ID to mark as incomplete.
        """
        service = get_tasks_service()
        try:
            current = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
            current['status'] = 'needsAction'
            current.pop('completed', None)
            result = service.tasks().update(tasklist=tasklist_id, task=task_id, body=current).execute()
            return f"Task '{result['title']}' marked as incomplete."
        except Exception as e:
            return f"Error uncompleting task '{task_id}': {str(e)}"

    @mcp.tool()
    def delete_task(tasklist_id: str, task_id: str) -> str:
        """
        Delete a task.

        Args:
            tasklist_id: The task list ID.
            task_id: The task ID to delete.
        """
        service = get_tasks_service()
        try:
            service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
            return f"Task '{task_id}' deleted successfully."
        except Exception as e:
            return f"Error deleting task '{task_id}': {str(e)}"

    @mcp.tool()
    def move_task(
        tasklist_id: str,
        task_id: str,
        parent: str = None,
        previous: str = None
    ) -> str:
        """
        Move a task to a different position or make it a subtask.

        Args:
            tasklist_id: The task list ID.
            task_id: The task ID to move.
            parent: New parent task ID (to make it a subtask).
            previous: Previous sibling task ID for positioning.
        """
        service = get_tasks_service()
        try:
            params = {'tasklist': tasklist_id, 'task': task_id}
            if parent:
                params['parent'] = parent
            if previous:
                params['previous'] = previous
            result = service.tasks().move(**params).execute()
            return f"""Task moved successfully!
ID: {result['id']}
Title: {result['title']}
New Parent: {result.get('parent', 'None (top-level)')}
New Position: {result.get('position', 'N/A')}"""
        except Exception as e:
            return f"Error moving task '{task_id}': {str(e)}"

    @mcp.tool()
    def clear_completed_tasks(tasklist_id: str = "@default") -> str:
        """
        Clear all completed tasks from a task list.

        Args:
            tasklist_id: The task list ID.
        """
        service = get_tasks_service()
        try:
            service.tasks().clear(tasklist=tasklist_id).execute()
            return f"Completed tasks cleared from task list '{tasklist_id}'."
        except Exception as e:
            return f"Error clearing completed tasks: {str(e)}"
