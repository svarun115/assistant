"""
Timeline Skeleton Builder - Unified view of a day from all sources.

Fetches data from Garmin, Gmail, and the journal DB, then merges into
a coherent timeline with explicit gaps and unplaced events.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Confidence(Enum):
    """Confidence level for timeline entries."""
    HIGH = "high"       # Device-confirmed (Garmin GPS) or user-logged (DB)
    MEDIUM = "medium"   # Receipt/transaction anchored
    LOW = "low"         # Inferred or backfilled


@dataclass
class TimeBlock:
    """A block of time with a known activity."""
    start_time: datetime
    end_time: Optional[datetime]
    block_type: str           # "workout", "meal", "work", "sleep", "commute", etc.
    title: str
    source: str               # "garmin", "gmail", "db", "inferred"
    confidence: Confidence
    db_event_id: Optional[str] = None    # If already logged in DB
    external_id: Optional[str] = None    # Garmin activity ID, etc.
    details: dict = field(default_factory=dict)
    
    @property
    def duration_minutes(self) -> Optional[int]:
        if self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return None


@dataclass
class TimeGap:
    """An unaccounted period of time."""
    start_time: datetime
    end_time: datetime
    likely_type: Optional[str] = None   # "lunch", "commute", "unknown"
    
    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class AnchorEvent:
    """An event from external source not yet placed in timeline."""
    timestamp: datetime
    event_type: str           # "receipt", "transaction", "expense"
    source: str               # "gmail", "splitwise"
    description: str          # "Swiggy ₹450", "Uber ₹180"
    details: dict = field(default_factory=dict)


@dataclass
class TimelineSkeleton:
    """Complete skeleton for a day."""
    date: date
    blocks: list[TimeBlock] = field(default_factory=list)
    gaps: list[TimeGap] = field(default_factory=list)
    unplaced: list[AnchorEvent] = field(default_factory=list)
    wake_time: Optional[datetime] = None
    sleep_time: Optional[datetime] = None
    
    @property
    def total_gap_minutes(self) -> int:
        return sum(g.duration_minutes for g in self.gaps)
    
    @property
    def logged_event_count(self) -> int:
        return sum(1 for b in self.blocks if b.db_event_id)
    
    def to_summary(self) -> str:
        """Generate human-readable summary for LLM context."""
        lines = [f"Timeline for {self.date.strftime('%B %d, %Y')}"]
        lines.append("=" * 50)
        
        # Combine blocks and gaps, sort by time
        all_items = []
        for block in self.blocks:
            all_items.append(("block", block.start_time, block))
        for gap in self.gaps:
            all_items.append(("gap", gap.start_time, gap))
        all_items.sort(key=lambda x: x[1])
        
        for item_type, _, item in all_items:
            if item_type == "block":
                block = item
                time_str = block.start_time.strftime("%H:%M")
                if block.end_time:
                    time_str += f"-{block.end_time.strftime('%H:%M')}"
                
                status = "✓" if block.db_event_id else "○"
                source_tag = f"[{block.source}]"
                lines.append(f"{time_str}  {status} {block.title} {source_tag}")
            else:
                gap = item
                time_str = f"{gap.start_time.strftime('%H:%M')}-{gap.end_time.strftime('%H:%M')}"
                hint = f" — likely {gap.likely_type}" if gap.likely_type else ""
                lines.append(f"{time_str}  ❓ Gap ({gap.duration_minutes}m){hint}")
        
        if self.unplaced:
            lines.append("")
            lines.append("Unplaced transactions:")
            for anchor in self.unplaced:
                time_str = anchor.timestamp.strftime("%H:%M")
                lines.append(f"  • {time_str} {anchor.description} [{anchor.source}]")
        
        lines.append("")
        lines.append(f"Summary: {len(self.blocks)} blocks, {len(self.gaps)} gaps ({self.total_gap_minutes}m), {len(self.unplaced)} unplaced")
        
        return "\n".join(lines)


class TimelineSkeletonBuilder:
    """
    Builds a unified timeline skeleton from multiple data sources.
    
    Usage:
        builder = TimelineSkeletonBuilder(mcp_bridge)
        skeleton = await builder.build(date(2025, 12, 31))
    """
    
    def __init__(self, mcp_bridge):
        self.bridge = mcp_bridge
        self._owner_id: Optional[str] = None
    
    async def build(self, target_date: date) -> TimelineSkeleton:
        """Build complete skeleton for a date."""
        logger.info(f"Building skeleton for {target_date}")
        
        # Fetch from all sources in parallel
        garmin_task = self._fetch_garmin(target_date)
        gmail_task = self._fetch_gmail(target_date)
        db_task = self._fetch_db_events(target_date)
        splitwise_task = self._fetch_splitwise(target_date)
        
        garmin_data, gmail_data, db_events, splitwise_data = await asyncio.gather(
            garmin_task, gmail_task, db_task, splitwise_task,
            return_exceptions=True
        )
        
        # Handle any fetch errors gracefully
        if isinstance(garmin_data, Exception):
            logger.warning(f"Garmin fetch failed: {garmin_data}")
            garmin_data = {"activities": [], "sleep": None, "summary": None}
        if isinstance(gmail_data, Exception):
            logger.warning(f"Gmail fetch failed: {gmail_data}")
            gmail_data = {"receipts": []}
        if isinstance(db_events, Exception):
            logger.warning(f"DB fetch failed: {db_events}")
            db_events = []
        if isinstance(splitwise_data, Exception):
            logger.warning(f"Splitwise fetch failed: {splitwise_data}")
            splitwise_data = {"expenses": []}
        
        # Build skeleton
        skeleton = TimelineSkeleton(date=target_date)
        
        # Extract wake/sleep times from Garmin
        if garmin_data.get("summary"):
            skeleton.wake_time = self._parse_garmin_time(
                garmin_data["summary"].get("wakeTime"), target_date
            )
            skeleton.sleep_time = self._parse_garmin_time(
                garmin_data["summary"].get("sleepTime"), target_date
            )
        
        # Add Garmin activities
        for activity in garmin_data.get("activities", []):
            block = self._garmin_activity_to_block(activity, db_events)
            if block:
                skeleton.blocks.append(block)
        
        # Add DB events (not already added from Garmin)
        for event in db_events:
            if not self._is_already_in_blocks(skeleton.blocks, event):
                block = self._db_event_to_block(event)
                if block:
                    skeleton.blocks.append(block)
        
        # Sort blocks by time
        skeleton.blocks.sort(key=lambda b: b.start_time)
        
        # Find gaps
        skeleton.gaps = self._find_gaps(
            skeleton.blocks, 
            skeleton.wake_time, 
            skeleton.sleep_time,
            target_date
        )
        
        # Collect unplaced receipts/transactions
        skeleton.unplaced = self._find_unplaced(
            gmail_data.get("receipts", []),
            splitwise_data.get("expenses", []),
            skeleton.blocks
        )
        
        logger.info(
            f"Skeleton built: {len(skeleton.blocks)} blocks, "
            f"{len(skeleton.gaps)} gaps, {len(skeleton.unplaced)} unplaced"
        )
        
        return skeleton
    
    async def _fetch_garmin(self, target_date: date) -> dict:
        """Fetch Garmin data for the date."""
        result = {"activities": [], "sleep": None, "summary": None}
        
        try:
            # Get activities
            date_str = target_date.isoformat()
            activities_result = await self.bridge.call_tool(
                "get_activities_by_date",
                {"start_date": date_str, "end_date": date_str}
            )
            if activities_result:
                result["activities"] = self._parse_garmin_activities(activities_result)
            
            # Get daily summary (wake/sleep times)
            summary_result = await self.bridge.call_tool(
                "get_user_summary",
                {"date": date_str}
            )
            if summary_result:
                result["summary"] = self._parse_garmin_summary(summary_result)
                
        except Exception as e:
            logger.warning(f"Garmin fetch error: {e}")
        
        return result
    
    async def _fetch_gmail(self, target_date: date) -> dict:
        """Fetch Gmail receipts for the date."""
        result = {"receipts": []}
        
        try:
            date_str = target_date.isoformat()
            next_date = (target_date + timedelta(days=1)).isoformat()
            
            emails_result = await self.bridge.call_tool(
                "search_emails",
                {
                    "start_date": date_str,
                    "end_date": next_date,
                    "query": "receipt OR order OR booking OR confirmation"
                }
            )
            if emails_result:
                result["receipts"] = self._parse_gmail_receipts(emails_result, target_date)
                
        except Exception as e:
            logger.warning(f"Gmail fetch error: {e}")
        
        return result
    
    async def _fetch_db_events(self, target_date: date) -> list[dict]:
        """Fetch already-logged events from journal DB."""
        try:
            date_str = target_date.isoformat()
            query = f"""
                SELECT 
                    e.id as event_id,
                    e.title,
                    e.event_type,
                    e.start_time,
                    e.end_time,
                    e.external_event_id,
                    e.external_event_source,
                    e.notes,
                    l.canonical_name as location_name
                FROM events e
                LEFT JOIN locations l ON e.location_id = l.id
                WHERE e.start_time::date = '{date_str}'
                  AND e.deleted_at IS NULL
                ORDER BY e.start_time
            """
            result = await self.bridge.call_tool("execute_sql_query", {"query": query})
            return self._parse_db_result(result)
        except Exception as e:
            logger.warning(f"DB fetch error: {e}")
            return []
    
    async def _fetch_splitwise(self, target_date: date) -> dict:
        """Fetch Splitwise expenses for the date."""
        result = {"expenses": []}
        
        try:
            date_str = target_date.isoformat()
            next_date = (target_date + timedelta(days=1)).isoformat()
            
            expenses_result = await self.bridge.call_tool(
                "splitwise_get_expenses",
                {
                    "dated_after": date_str,
                    "dated_before": next_date,
                    "limit": 50
                }
            )
            if expenses_result:
                result["expenses"] = self._parse_splitwise_expenses(expenses_result, target_date)
                
        except Exception as e:
            logger.warning(f"Splitwise fetch error: {e}")
        
        return result
    
    def _parse_garmin_activities(self, raw: str) -> list[dict]:
        """Parse Garmin activities response."""
        import json
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list):
                return data
            return data.get("activities", []) if isinstance(data, dict) else []
        except:
            return []
    
    def _parse_garmin_summary(self, raw: str) -> dict:
        """Parse Garmin daily summary."""
        import json
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except:
            return {}
    
    def _parse_garmin_time(self, time_val: Any, target_date: date) -> Optional[datetime]:
        """Parse Garmin time value to datetime."""
        if not time_val:
            return None
        try:
            if isinstance(time_val, int):
                # Milliseconds since midnight
                seconds = time_val // 1000
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                return datetime.combine(target_date, time(hours, minutes))
            elif isinstance(time_val, str):
                # ISO format
                return datetime.fromisoformat(time_val.replace("Z", "+00:00"))
        except:
            pass
        return None
    
    def _parse_gmail_receipts(self, raw: str, target_date: date) -> list[dict]:
        """Parse Gmail search results into receipt data."""
        import json
        receipts = []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list):
                for email in data:
                    receipt = {
                        "id": email.get("id"),
                        "subject": email.get("subject", ""),
                        "sender": email.get("sender", ""),
                        "snippet": email.get("snippet", ""),
                        "date": email.get("date"),
                    }
                    receipts.append(receipt)
        except:
            pass
        return receipts
    
    def _parse_splitwise_expenses(self, raw: str, target_date: date) -> list[dict]:
        """Parse Splitwise expenses."""
        import json
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list):
                return data
            return data.get("expenses", []) if isinstance(data, dict) else []
        except:
            return []
    
    def _parse_db_result(self, raw: str) -> list[dict]:
        """Parse SQL query result."""
        import json
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list):
                return data
            return data.get("rows", []) if isinstance(data, dict) else []
        except:
            return []
    
    def _garmin_activity_to_block(self, activity: dict, db_events: list[dict]) -> Optional[TimeBlock]:
        """Convert Garmin activity to TimeBlock."""
        try:
            # Parse start time
            start_str = activity.get("startTimeLocal") or activity.get("startTime")
            if not start_str:
                return None
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            
            # Calculate end time
            duration_seconds = activity.get("duration", 0)
            end_time = start_time + timedelta(seconds=duration_seconds) if duration_seconds else None
            
            # Activity type mapping
            activity_type = activity.get("activityType", {})
            type_key = activity_type.get("typeKey", "unknown") if isinstance(activity_type, dict) else str(activity_type)
            
            # Check if linked to DB event
            activity_id = str(activity.get("activityId", ""))
            db_event_id = None
            for event in db_events:
                if event.get("external_event_id") == activity_id:
                    db_event_id = event.get("event_id")
                    break
            
            # Build title
            activity_name = activity.get("activityName") or type_key.replace("_", " ").title()
            distance_km = activity.get("distance", 0) / 1000 if activity.get("distance") else None
            if distance_km and distance_km > 0:
                activity_name += f" ({distance_km:.1f}K)"
            
            return TimeBlock(
                start_time=start_time,
                end_time=end_time,
                block_type="workout",
                title=activity_name,
                source="garmin",
                confidence=Confidence.HIGH,
                db_event_id=db_event_id,
                external_id=activity_id,
                details={
                    "activity_type": type_key,
                    "distance_km": distance_km,
                    "duration_minutes": duration_seconds // 60 if duration_seconds else None,
                    "calories": activity.get("calories"),
                }
            )
        except Exception as e:
            logger.warning(f"Error parsing Garmin activity: {e}")
            return None
    
    def _db_event_to_block(self, event: dict) -> Optional[TimeBlock]:
        """Convert DB event to TimeBlock."""
        try:
            start_time = event.get("start_time")
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            if not start_time:
                return None
            
            end_time = event.get("end_time")
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time)
            
            # Map event type to block type
            event_type = event.get("event_type", "generic")
            block_type_map = {
                "workout": "workout",
                "meal": "meal",
                "sleep": "sleep",
                "work": "work",
                "commute": "commute",
                "entertainment": "entertainment",
                "generic": "event",
            }
            block_type = block_type_map.get(event_type, "event")
            
            # Build title
            title = event.get("title", "Untitled")
            location = event.get("location_name")
            if location:
                title += f" at {location}"
            
            return TimeBlock(
                start_time=start_time,
                end_time=end_time,
                block_type=block_type,
                title=title,
                source="db",
                confidence=Confidence.HIGH,
                db_event_id=event.get("event_id"),
                external_id=event.get("external_event_id"),
                details={
                    "event_type": event_type,
                    "notes": event.get("notes"),
                }
            )
        except Exception as e:
            logger.warning(f"Error parsing DB event: {e}")
            return None
    
    def _is_already_in_blocks(self, blocks: list[TimeBlock], event: dict) -> bool:
        """Check if event is already represented in blocks (via Garmin link)."""
        event_id = event.get("event_id")
        external_id = event.get("external_event_id")
        
        for block in blocks:
            if block.db_event_id == event_id:
                return True
            if external_id and block.external_id == external_id:
                return True
        return False
    
    def _find_gaps(
        self, 
        blocks: list[TimeBlock], 
        wake_time: Optional[datetime],
        sleep_time: Optional[datetime],
        target_date: date
    ) -> list[TimeGap]:
        """Find gaps in the timeline."""
        gaps = []
        
        # Default wake/sleep if not available
        if not wake_time:
            wake_time = datetime.combine(target_date, time(7, 0))
        if not sleep_time:
            sleep_time = datetime.combine(target_date, time(23, 0))
        
        # Minimum gap to report (30 minutes)
        MIN_GAP_MINUTES = 30
        
        current_time = wake_time
        
        for block in blocks:
            if block.start_time > current_time:
                gap_minutes = (block.start_time - current_time).total_seconds() / 60
                if gap_minutes >= MIN_GAP_MINUTES:
                    # Infer likely type based on time of day
                    likely_type = self._infer_gap_type(current_time, block.start_time)
                    gaps.append(TimeGap(
                        start_time=current_time,
                        end_time=block.start_time,
                        likely_type=likely_type
                    ))
            
            # Move current time to end of this block
            if block.end_time and block.end_time > current_time:
                current_time = block.end_time
            elif block.start_time > current_time:
                # If no end time, assume 30 min duration
                current_time = block.start_time + timedelta(minutes=30)
        
        # Gap until sleep
        if sleep_time > current_time:
            gap_minutes = (sleep_time - current_time).total_seconds() / 60
            if gap_minutes >= MIN_GAP_MINUTES:
                likely_type = self._infer_gap_type(current_time, sleep_time)
                gaps.append(TimeGap(
                    start_time=current_time,
                    end_time=sleep_time,
                    likely_type=likely_type
                ))
        
        return gaps
    
    def _infer_gap_type(self, start: datetime, end: datetime) -> Optional[str]:
        """Infer what a gap might be based on time of day."""
        mid_hour = (start.hour + end.hour) // 2
        
        if 7 <= mid_hour <= 9:
            return "breakfast/morning routine"
        elif 12 <= mid_hour <= 14:
            return "lunch"
        elif 18 <= mid_hour <= 20:
            return "dinner"
        elif 20 <= mid_hour <= 23:
            return "evening"
        return None
    
    def _find_unplaced(
        self,
        gmail_receipts: list[dict],
        splitwise_expenses: list[dict],
        blocks: list[TimeBlock]
    ) -> list[AnchorEvent]:
        """Find receipts/transactions not yet matched to logged events."""
        unplaced = []
        
        # Process Gmail receipts
        for receipt in gmail_receipts:
            # Simple sender-based categorization
            sender = receipt.get("sender", "").lower()
            subject = receipt.get("subject", "")
            
            description = subject[:50] if subject else sender
            
            # Try to parse date
            date_str = receipt.get("date")
            timestamp = None
            if date_str:
                try:
                    timestamp = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass
            
            if timestamp:
                unplaced.append(AnchorEvent(
                    timestamp=timestamp,
                    event_type="receipt",
                    source="gmail",
                    description=description,
                    details={"email_id": receipt.get("id")}
                ))
        
        # Process Splitwise expenses
        for expense in splitwise_expenses:
            description = expense.get("description", "Expense")
            cost = expense.get("cost", "")
            if cost:
                description += f" ({cost})"
            
            date_str = expense.get("date") or expense.get("created_at")
            timestamp = None
            if date_str:
                try:
                    timestamp = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass
            
            if timestamp:
                unplaced.append(AnchorEvent(
                    timestamp=timestamp,
                    event_type="expense",
                    source="splitwise",
                    description=description,
                    details={"expense_id": expense.get("id")}
                ))
        
        # Sort by time
        unplaced.sort(key=lambda x: x.timestamp)
        
        return unplaced
