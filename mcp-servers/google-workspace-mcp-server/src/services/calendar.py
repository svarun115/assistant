"""Google Calendar service tools."""

import logging
from typing import List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser
from mcp.server.fastmcp import FastMCP

from ..auth import get_calendar_service
from ..cache import cache

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = 'Asia/Kolkata'


def get_user_timezone() -> str:
    """Get user's timezone from their primary calendar settings."""
    cached = cache.get('calendar:user_timezone')
    if cached:
        return cached
    try:
        service = get_calendar_service()
        cal = service.calendars().get(calendarId='primary').execute()
        tz = cal.get('timeZone', DEFAULT_TIMEZONE)
        cache.set('calendar:user_timezone', tz, ttl=3600)  # Cache 1 hour
        return tz
    except Exception:
        return DEFAULT_TIMEZONE


def parse_datetime_to_rfc3339(date_str: str, timezone: str = None) -> Optional[str]:
    """Parse a date string to RFC 3339 format required by Google Calendar API."""
    if not date_str:
        return None
    tz = timezone or get_user_timezone()
    dt = dateparser.parse(date_str, settings={'TIMEZONE': tz, 'RETURN_AS_TIMEZONE_AWARE': True})
    if dt:
        return dt.isoformat()
    return None


def format_event_time(event: dict) -> str:
    """Format event start/end time for display."""
    start = event.get('start', {})
    end = event.get('end', {})
    if 'dateTime' in start:
        start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
        return f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}"
    elif 'date' in start:
        return f"{start['date']} (All day)"
    return "Unknown time"


def register_tools(mcp: FastMCP):
    """Register all Calendar tools on the shared MCP server."""

    @mcp.tool()
    def list_calendars() -> str:
        """List all calendars for the authenticated user."""
        service = get_calendar_service()
        try:
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            if not calendars:
                return "No calendars found."
            output = ["--- Calendars ---"]
            for cal in calendars:
                primary = " (Primary)" if cal.get('primary') else ""
                access = cal.get('accessRole', 'unknown')
                output.append(f"ID: {cal['id']}\nName: {cal['summary']}{primary}\nAccess: {access}\n---")
            return "\n".join(output)
        except Exception as e:
            return f"Error listing calendars: {str(e)}"

    @mcp.tool()
    def get_calendar(calendar_id: str = "primary") -> str:
        """
        Get detailed information about a specific calendar.

        Args:
            calendar_id: The calendar ID (use 'primary' for main calendar).
        """
        service = get_calendar_service()
        try:
            cal = service.calendars().get(calendarId=calendar_id).execute()
            return f"""Calendar Details:
ID: {cal['id']}
Name: {cal.get('summary', 'Unnamed')}
Description: {cal.get('description', '(No description)')}
Timezone: {cal.get('timeZone', 'Unknown')}
Location: {cal.get('location', '(No location)')}"""
        except Exception as e:
            return f"Error getting calendar '{calendar_id}': {str(e)}"

    @mcp.tool()
    def list_events(
        calendar_id: str = "primary",
        start_date: str = None,
        end_date: str = None,
        max_results: int = 50,
        search_query: str = None
    ) -> str:
        """
        List events from a calendar within a date range.

        Args:
            calendar_id: The calendar ID.
            start_date: Start of date range (e.g., 'today', '2024-01-15').
            end_date: End of date range. If start_date == end_date, the query
                     automatically includes the full day (00:00 to 23:59).
            max_results: Maximum events to return.
            search_query: Text to search in events.
        """
        service = get_calendar_service()
        tz = get_user_timezone()
        try:
            if start_date:
                time_min = parse_datetime_to_rfc3339(start_date, tz)
            else:
                time_min = datetime.now(ZoneInfo(tz)).isoformat()

            if end_date:
                # Fix: If start_date == end_date, extend end_date to end of day
                # to avoid zero-length range (since dateparser parses to midnight)
                if start_date and start_date == end_date:
                    # Parse end_date and add 1 day to make it inclusive
                    end_dt = dateparser.parse(end_date, settings={'TIMEZONE': tz})
                    if end_dt:
                        end_dt = end_dt + timedelta(days=1)
                        time_max = end_dt.replace(tzinfo=ZoneInfo(tz)).isoformat()
                    else:
                        time_max = parse_datetime_to_rfc3339(end_date, tz)
                else:
                    time_max = parse_datetime_to_rfc3339(end_date, tz)
            else:
                start_dt = dateparser.parse(start_date) if start_date else datetime.now()
                end_dt = start_dt + timedelta(days=7)
                time_max = end_dt.replace(tzinfo=ZoneInfo(tz)).isoformat()

            params = {
                'calendarId': calendar_id,
                'timeMin': time_min,
                'timeMax': time_max,
                'maxResults': max_results,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            if search_query:
                params['q'] = search_query

            events_result = service.events().list(**params).execute()
            events = events_result.get('items', [])

            if not events:
                return f"No events found between {start_date or 'now'} and {end_date or '7 days'}."

            output = [f"--- Events ({len(events)} found) ---"]
            for event in events:
                title = event.get('summary', '(No title)')
                time_str = format_event_time(event)
                location = event.get('location', '')
                location_str = f"\n   Location: {location}" if location else ""
                attendees = event.get('attendees', [])
                attendee_str = f"\n   Attendees: {len(attendees)}" if attendees else ""
                output.append(f"""* {title}
   ID: {event['id']}
   Time: {time_str}{location_str}{attendee_str}
---""")
            return "\n".join(output)
        except Exception as e:
            return f"Error listing events: {str(e)}"

    @mcp.tool()
    def get_event(calendar_id: str, event_id: str) -> str:
        """
        Get detailed information about a specific event.

        Args:
            calendar_id: The calendar ID.
            event_id: The event ID.
        """
        service = get_calendar_service()
        try:
            event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            time_str = format_event_time(event)
            attendees = event.get('attendees', [])
            attendee_list = "\n".join([f"   - {a.get('email')} ({a.get('responseStatus', 'unknown')})" for a in attendees])
            attendee_str = f"\nAttendees:\n{attendee_list}" if attendees else "\nAttendees: None (solo event)"
            recurrence = event.get('recurrence', [])
            recurrence_str = f"\nRecurrence: {', '.join(recurrence)}" if recurrence else ""
            return f"""Event Details:
ID: {event['id']}
Title: {event.get('summary', '(No title)')}
Time: {time_str}
Location: {event.get('location', '(No location)')}
Description: {event.get('description', '(No description)')}
Status: {event.get('status', 'unknown')}
Created: {event.get('created', 'unknown')}
Updated: {event.get('updated', 'unknown')}
Organizer: {event.get('organizer', {}).get('email', 'unknown')}{attendee_str}{recurrence_str}
HTML Link: {event.get('htmlLink', 'N/A')}"""
        except Exception as e:
            return f"Error getting event '{event_id}': {str(e)}"

    @mcp.tool()
    def create_event(
        title: str,
        start_time: str,
        end_time: str = None,
        duration_minutes: int = 60,
        calendar_id: str = "primary",
        description: str = None,
        location: str = None,
        all_day: bool = False
    ) -> str:
        """
        Create a new calendar event.

        Args:
            title: Event title.
            start_time: Start time (e.g., 'tomorrow at 2pm').
            end_time: End time (optional).
            duration_minutes: Duration in minutes (default 60).
            calendar_id: Calendar ID (default 'primary').
            description: Event description.
            location: Event location.
            all_day: Create as all-day event.
        """
        service = get_calendar_service()
        tz = get_user_timezone()
        try:
            event_body = {'summary': title}
            if all_day:
                start_dt = dateparser.parse(start_time)
                event_body['start'] = {'date': start_dt.strftime('%Y-%m-%d')}
                event_body['end'] = {'date': (start_dt + timedelta(days=1)).strftime('%Y-%m-%d')}
            else:
                start_rfc = parse_datetime_to_rfc3339(start_time, tz)
                if not start_rfc:
                    return f"Could not parse start time: {start_time}"
                event_body['start'] = {'dateTime': start_rfc, 'timeZone': tz}
                if end_time:
                    end_rfc = parse_datetime_to_rfc3339(end_time, tz)
                    if not end_rfc:
                        return f"Could not parse end time: {end_time}"
                    event_body['end'] = {'dateTime': end_rfc, 'timeZone': tz}
                else:
                    start_dt = dateparser.parse(start_time, settings={'TIMEZONE': tz, 'RETURN_AS_TIMEZONE_AWARE': True})
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                    event_body['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': tz}
            if description:
                event_body['description'] = description
            if location:
                event_body['location'] = location

            created_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            cache.invalidate_prefix('calendar:')
            return f"""Event created successfully!
ID: {created_event['id']}
Title: {created_event.get('summary')}
Time: {format_event_time(created_event)}
Link: {created_event.get('htmlLink')}"""
        except Exception as e:
            return f"Error creating event '{title}': {str(e)}"

    @mcp.tool()
    def update_event(
        calendar_id: str,
        event_id: str,
        title: str = None,
        start_time: str = None,
        end_time: str = None,
        description: str = None,
        location: str = None
    ) -> str:
        """
        Update an existing calendar event.

        Args:
            calendar_id: The calendar ID.
            event_id: The event ID.
            title: New title.
            start_time: New start time.
            end_time: New end time.
            description: New description.
            location: New location.
        """
        service = get_calendar_service()
        tz = get_user_timezone()
        try:
            event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            if title is not None:
                event['summary'] = title
            if description is not None:
                event['description'] = description
            if location is not None:
                event['location'] = location
            if start_time is not None:
                start_rfc = parse_datetime_to_rfc3339(start_time, tz)
                if start_rfc:
                    event['start'] = {'dateTime': start_rfc, 'timeZone': tz}
            if end_time is not None:
                end_rfc = parse_datetime_to_rfc3339(end_time, tz)
                if end_rfc:
                    event['end'] = {'dateTime': end_rfc, 'timeZone': tz}

            updated_event = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
            cache.invalidate_prefix('calendar:')
            return f"""Event updated successfully!
ID: {updated_event['id']}
Title: {updated_event.get('summary')}
Time: {format_event_time(updated_event)}"""
        except Exception as e:
            return f"Error updating event '{event_id}': {str(e)}"

    @mcp.tool()
    def delete_event(calendar_id: str, event_id: str) -> str:
        """
        Delete a calendar event.

        Args:
            calendar_id: The calendar ID.
            event_id: The event ID.
        """
        service = get_calendar_service()
        try:
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            cache.invalidate_prefix('calendar:')
            return f"Event '{event_id}' deleted successfully."
        except Exception as e:
            return f"Error deleting event '{event_id}': {str(e)}"

    @mcp.tool()
    def get_free_busy(
        start_time: str,
        end_time: str,
        calendar_ids: List[str] = None
    ) -> str:
        """
        Check free/busy status for calendars.

        Args:
            start_time: Start of time range.
            end_time: End of time range.
            calendar_ids: Calendar IDs to check.
        """
        service = get_calendar_service()
        tz = get_user_timezone()
        try:
            time_min = parse_datetime_to_rfc3339(start_time, tz)
            time_max = parse_datetime_to_rfc3339(end_time, tz)
            if not time_min or not time_max:
                return "Could not parse time range."
            if calendar_ids is None:
                calendar_ids = ['primary']
            body = {
                'timeMin': time_min,
                'timeMax': time_max,
                'items': [{'id': cal_id} for cal_id in calendar_ids]
            }
            result = service.freebusy().query(body=body).execute()
            calendars = result.get('calendars', {})
            output = [f"--- Free/Busy: {start_time} to {end_time} ---"]
            for cal_id, cal_data in calendars.items():
                busy_periods = cal_data.get('busy', [])
                if not busy_periods:
                    output.append(f"\n{cal_id}: Completely free!")
                else:
                    output.append(f"\n{cal_id}: {len(busy_periods)} busy period(s)")
                    for period in busy_periods:
                        start = datetime.fromisoformat(period['start'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(period['end'].replace('Z', '+00:00'))
                        output.append(f"   - {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%H:%M')}")
            return "\n".join(output)
        except Exception as e:
            return f"Error checking free/busy: {str(e)}"

    @mcp.tool()
    def quick_add(text: str, calendar_id: str = "primary") -> str:
        """
        Create event using natural language.

        Args:
            text: Natural language event (e.g., 'Meeting tomorrow at 3pm').
            calendar_id: Calendar ID (default 'primary').
        """
        service = get_calendar_service()
        try:
            created_event = service.events().quickAdd(calendarId=calendar_id, text=text).execute()
            cache.invalidate_prefix('calendar:')
            return f"""Event created via Quick Add!
ID: {created_event['id']}
Title: {created_event.get('summary')}
Time: {format_event_time(created_event)}
Link: {created_event.get('htmlLink')}"""
        except Exception as e:
            return f"Error with quick add '{text}': {str(e)}"
