"""
Planning Handlers

Handles: create_daily_plan, update_plan_item, get_plan_vs_actual, get_planning_insights

All handlers use direct database access (needs_db=True, needs_repos=False).
"""

import json
from datetime import datetime, date
from typing import Any
from uuid import UUID

from mcp import types


async def handle_create_daily_plan(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Create a daily plan with its planned items. Auto-increments version."""
    try:
        plan_date_str = arguments.get("plan_date")
        if not plan_date_str:
            raise ValueError("plan_date is required")

        plan_date = date.fromisoformat(plan_date_str)
        source = arguments.get("source", "daily_tracker")
        time_budget = arguments.get("time_budget")
        notes = arguments.get("notes")
        items = arguments.get("items", [])

        # Auto-calculate version: max existing version + 1
        version_row = await db.fetchrow(
            """
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM daily_plans
            WHERE plan_date = $1 AND is_deleted = FALSE
            """,
            plan_date
        )
        version = version_row["next_version"]

        # Create plan record
        plan_row = await db.fetchrow(
            """
            INSERT INTO daily_plans (plan_date, version, source, time_budget, notes)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id, version
            """,
            plan_date,
            version,
            source,
            json.dumps(time_budget) if time_budget else None,
            notes
        )
        plan_id = plan_row["id"]

        # Create planned items
        item_ids = []
        for item in items:
            start_time = None
            end_time = None
            if item.get("start_time"):
                start_time = datetime.fromisoformat(item["start_time"])
            if item.get("end_time"):
                end_time = datetime.fromisoformat(item["end_time"])

            # Calculate duration_minutes if both times provided
            duration_minutes = None
            if start_time and end_time:
                duration_minutes = int((end_time - start_time).total_seconds() / 60)

            item_row = await db.fetchrow(
                """
                INSERT INTO planned_items (
                    plan_id, title, start_time, end_time, duration_minutes,
                    category, item_type, priority, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                plan_id,
                item["title"],
                start_time,
                end_time,
                duration_minutes,
                item.get("category"),
                item.get("item_type"),
                item.get("priority", "medium"),
                item.get("notes")
            )
            item_ids.append(str(item_row["id"]))

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "plan_id": str(plan_id),
                "plan_date": plan_date_str,
                "version": version,
                "item_count": len(item_ids),
                "item_ids": item_ids,
                "message": f"Daily plan created for {plan_date_str} (v{version})"
            })
        )]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error creating daily plan: {str(e)}")]


async def handle_update_plan_item(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update the status of a planned item."""
    try:
        item_id_str = arguments.get("item_id")
        if not item_id_str:
            raise ValueError("item_id is required")

        status = arguments.get("status")
        if not status:
            raise ValueError("status is required")

        valid_statuses = {"planned", "in-progress", "completed", "skipped", "modified", "replaced"}
        if status not in valid_statuses:
            raise ValueError(f"status must be one of: {', '.join(sorted(valid_statuses))}")

        item_id = UUID(item_id_str)
        actual_event_id_str = arguments.get("actual_event_id")
        actual_event_id = UUID(actual_event_id_str) if actual_event_id_str else None
        status_notes = arguments.get("status_notes")

        row = await db.fetchrow(
            """
            UPDATE planned_items
            SET
                status = $2,
                actual_event_id = COALESCE($3, actual_event_id),
                status_notes = COALESCE($4, status_notes),
                updated_at = NOW()
            WHERE id = $1
            RETURNING id, title, status
            """,
            item_id,
            status,
            actual_event_id,
            status_notes
        )

        if not row:
            raise ValueError(f"Planned item {item_id_str} not found")

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "item_id": str(row["id"]),
                "title": row["title"],
                "status": row["status"],
                "message": f"Item '{row['title']}' updated to '{status}'"
            })
        )]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error updating plan item: {str(e)}")]


async def handle_get_plan_vs_actual(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Get plan vs. actual comparison for a date."""
    try:
        plan_date_str = arguments.get("plan_date")
        if not plan_date_str:
            raise ValueError("plan_date is required")

        plan_date = date.fromisoformat(plan_date_str)
        version = arguments.get("version")

        # Resolve to latest version if not specified
        if not version:
            version_row = await db.fetchrow(
                "SELECT MAX(version) AS max_version FROM daily_plans WHERE plan_date = $1 AND is_deleted = FALSE",
                plan_date
            )
            version = version_row["max_version"] if version_row else None

        if not version:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"No plan found for {plan_date_str}"})
            )]

        # Get plan metadata
        plan_row = await db.fetchrow(
            "SELECT * FROM daily_plans WHERE plan_date = $1 AND version = $2 AND is_deleted = FALSE",
            plan_date, version
        )
        if not plan_row:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Plan not found for {plan_date_str} v{version}"})
            )]

        # Get plan vs actual rows from view
        items_rows = await db.fetch(
            "SELECT * FROM plan_vs_actual WHERE plan_date = $1 AND plan_version = $2",
            plan_date, version
        )

        items = []
        for row in items_rows:
            item = {}
            for key in row.keys():
                val = row[key]
                if isinstance(val, datetime):
                    val = val.isoformat()
                elif isinstance(val, date):
                    val = val.isoformat()
                elif isinstance(val, UUID):
                    val = str(val)
                item[key] = val
            items.append(item)

        # Compute summary stats
        total = len(items)
        completed = sum(1 for i in items if i["status"] in ("completed", "modified"))
        skipped = sum(1 for i in items if i["status"] == "skipped")
        pending = sum(1 for i in items if i["status"] == "planned")
        in_progress = sum(1 for i in items if i["status"] == "in-progress")
        completion_rate = round(completed / total * 100, 1) if total > 0 else 0.0

        linked_deltas = [
            i["end_time_delta_minutes"] for i in items
            if i.get("end_time_delta_minutes") is not None
        ]
        avg_delta = round(sum(linked_deltas) / len(linked_deltas), 1) if linked_deltas else None

        plan_meta = {
            "plan_id": str(plan_row["id"]),
            "plan_date": plan_date_str,
            "version": version,
            "source": plan_row["source"],
            "time_budget": plan_row["time_budget"],
            "notes": plan_row["notes"],
        }

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "plan": plan_meta,
                "items": items,
                "summary": {
                    "total": total,
                    "completed": completed,
                    "skipped": skipped,
                    "pending": pending,
                    "in_progress": in_progress,
                    "completion_rate_pct": completion_rate,
                    "avg_end_time_delta_minutes": avg_delta
                }
            }, default=str)
        )]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error getting plan vs actual: {str(e)}")]


async def handle_get_planning_insights(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Get planning analytics over a date range."""
    try:
        start_date_str = arguments.get("start_date")
        end_date_str = arguments.get("end_date")

        if not start_date_str or not end_date_str:
            raise ValueError("start_date and end_date are required")

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        # Overall stats
        overall_row = await db.fetchrow(
            """
            SELECT
                COUNT(DISTINCT dp.plan_date) AS days_with_plans,
                COUNT(pi.id) AS total_items,
                COUNT(CASE WHEN pi.status IN ('completed', 'modified') THEN 1 END) AS completed_items,
                COUNT(CASE WHEN pi.status = 'skipped' THEN 1 END) AS skipped_items
            FROM daily_plans dp
            JOIN planned_items pi ON pi.plan_id = dp.id
            WHERE dp.plan_date BETWEEN $1 AND $2 AND dp.is_deleted = FALSE
            """,
            start_date, end_date
        )

        days_with_plans = overall_row["days_with_plans"] or 0
        total_items = overall_row["total_items"] or 0
        completed_items = overall_row["completed_items"] or 0
        completion_rate = round(completed_items / total_items * 100, 1) if total_items > 0 else 0.0
        avg_items_per_day = round(total_items / days_with_plans, 1) if days_with_plans > 0 else 0.0

        # Category breakdown
        category_rows = await db.fetch(
            """
            SELECT
                pi.category,
                COUNT(*) AS total,
                COUNT(CASE WHEN pi.status IN ('completed', 'modified') THEN 1 END) AS completed
            FROM daily_plans dp
            JOIN planned_items pi ON pi.plan_id = dp.id
            WHERE dp.plan_date BETWEEN $1 AND $2
              AND dp.is_deleted = FALSE
              AND pi.category IS NOT NULL
            GROUP BY pi.category
            ORDER BY total DESC
            """,
            start_date, end_date
        )
        category_breakdown = [
            {
                "category": row["category"],
                "total": row["total"],
                "completed": row["completed"],
                "completion_rate_pct": round(row["completed"] / row["total"] * 100, 1) if row["total"] > 0 else 0.0
            }
            for row in category_rows
        ]

        # Day-of-week breakdown
        dow_rows = await db.fetch(
            """
            SELECT
                TRIM(TO_CHAR(dp.plan_date, 'Day')) AS day_name,
                EXTRACT(DOW FROM dp.plan_date) AS dow_num,
                COUNT(pi.id) AS total_items,
                COUNT(CASE WHEN pi.status IN ('completed', 'modified') THEN 1 END) AS completed_items
            FROM daily_plans dp
            JOIN planned_items pi ON pi.plan_id = dp.id
            WHERE dp.plan_date BETWEEN $1 AND $2 AND dp.is_deleted = FALSE
            GROUP BY dow_num, day_name
            ORDER BY dow_num
            """,
            start_date, end_date
        )
        dow_patterns = [
            {
                "day": row["day_name"],
                "total_items": row["total_items"],
                "completed_items": row["completed_items"],
                "completion_rate_pct": round(row["completed_items"] / row["total_items"] * 100, 1) if row["total_items"] > 0 else 0.0
            }
            for row in dow_rows
        ]

        # Generate insights
        insights = []
        if completion_rate >= 80:
            insights.append(f"Strong completion rate of {completion_rate}% over this period.")
        elif completion_rate < 50 and total_items >= 5:
            insights.append(f"Low completion rate of {completion_rate}%. Consider scheduling fewer items per day.")
        if avg_items_per_day > 8:
            insights.append(f"Averaging {avg_items_per_day} items/day — consider reducing to avoid overplanning.")
        if category_breakdown:
            worst = min(category_breakdown, key=lambda c: c["completion_rate_pct"])
            if worst["completion_rate_pct"] < 50 and worst["total"] >= 3:
                insights.append(
                    f"'{worst['category']}' items have low completion ({worst['completion_rate_pct']}%) "
                    f"— may need better time allocation."
                )

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "period": {"start_date": start_date_str, "end_date": end_date_str},
                "overview": {
                    "days_with_plans": days_with_plans,
                    "total_items": total_items,
                    "completed_items": completed_items,
                    "completion_rate_pct": completion_rate,
                    "avg_items_per_day": avg_items_per_day
                },
                "category_breakdown": category_breakdown,
                "day_of_week_patterns": dow_patterns,
                "insights": insights
            })
        )]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error getting planning insights: {str(e)}")]
