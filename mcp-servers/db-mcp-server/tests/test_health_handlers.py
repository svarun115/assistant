"""
Tests for health handlers - specifically log_health_condition fix for issue #84
"""

import pytest
import json
from uuid import UUID

from handlers.health_handlers import handle_log_health_condition


class TestLogHealthCondition:
    """Test the log_health_condition handler"""
    
    @pytest.mark.asyncio
    async def test_log_health_condition_creates_event_and_condition(self, db, repos):
        """Test that log_health_condition properly creates both event and condition records"""
        arguments = {
            "condition_type": "illness",
            "condition_name": "test headache",
            "severity": "home_remedy",
            "severity_score": 5,
            "start_date": "2025-12-02",
            "end_date": "2025-12-02",
            "notes": "Test health condition from automated test"
        }
        
        # Call the handler
        result = await handle_log_health_condition(db, repos, arguments)
        
        # Parse the result
        assert len(result) == 1
        result_data = json.loads(result[0].text)
        
        # Verify success
        assert result_data.get("status") == "success", f"Expected success but got: {result_data}"
        assert "condition_id" in result_data
        assert "event_id" in result_data
        assert result_data["condition_name"] == "test headache"
        assert result_data["condition_type"] == "illness"
        assert result_data["message"] == "✅ Health condition logged"
        
        # Verify the event was created in the database
        event_id = result_data["event_id"]
        event_row = await db.fetchrow("SELECT * FROM events WHERE id = $1", UUID(event_id))
        assert event_row is not None
        assert event_row["title"] == "Illness: test headache"
        assert event_row["category"] == "health"
        
        # Verify the health condition was created
        condition_id = result_data["condition_id"]
        condition_row = await db.fetchrow("SELECT * FROM health_conditions WHERE id = $1", UUID(condition_id))
        assert condition_row is not None
        assert condition_row["condition_name"] == "test headache"
        assert condition_row["condition_type"] == "illness"
        assert condition_row["event_id"] == UUID(event_id)
        
    @pytest.mark.asyncio
    async def test_log_health_condition_with_partial_date(self, db, repos):
        """Test that partial dates (YYYY-MM) are handled correctly"""
        arguments = {
            "condition_type": "injury",
            "condition_name": "sprained ankle",
            "severity": "clinic_visit",  # Valid severity value
            "start_date": "2025-08",  # Partial date
            "notes": "Partial date test"
        }
        
        result = await handle_log_health_condition(db, repos, arguments)
        result_data = json.loads(result[0].text)
        
        assert result_data.get("status") == "success", f"Expected success but got: {result_data}"
        assert "condition_id" in result_data
        
    @pytest.mark.asyncio
    async def test_log_health_condition_without_end_date(self, db, repos):
        """Test ongoing conditions (no end date)"""
        arguments = {
            "condition_type": "illness",
            "condition_name": "ongoing cold",
            "severity": "home_remedy",
            "start_date": "2025-12-01"
        }
        
        result = await handle_log_health_condition(db, repos, arguments)
        result_data = json.loads(result[0].text)
        
        assert result_data.get("status") == "success"
        assert "(ongoing)" in result_data["date_range"]
