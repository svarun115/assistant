"""
Tests for error message enhancement utility (Issues #101, #102)
"""

import pytest
from utils.error_messages import enhance_error_message, get_enum_values, format_enum_hint


class TestEnhanceErrorMessage:
    """Test error message enhancement for various error types."""
    
    def test_enum_error_with_valid_enum(self):
        """Test that enum errors show valid values."""
        error = Exception('invalid input value for enum event_category_enum: "fitness"')
        result = enhance_error_message(error)
        
        assert "Invalid value 'fitness'" in result
        assert "event_category_enum" in result
        assert "health" in result
        assert "social" in result
        assert "work" in result
    
    def test_enum_error_workout_category(self):
        """Test workout category enum error."""
        error = Exception('invalid input value for enum workout_category_enum: "cardio_strength"')
        result = enhance_error_message(error)
        
        assert "Invalid value 'cardio_strength'" in result
        assert "STRENGTH" in result
        assert "CARDIO" in result
        assert "MIXED" in result
    
    def test_enum_error_unknown_enum(self):
        """Test enum error for unknown enum type returns original."""
        error = Exception('invalid input value for enum unknown_enum: "bad_value"')
        result = enhance_error_message(error)
        
        # Should return original since we don't know the valid values
        assert "invalid input value" in result
    
    def test_constraint_violation_reps_or_interval(self):
        """Test check_reps_or_interval constraint explanation."""
        error = Exception('new row for relation "exercise_sets" violates check constraint "check_reps_or_interval"')
        result = enhance_error_message(error)
        
        assert "check_reps_or_interval" in result
        assert "reps" in result
        assert "interval_description" in result
        assert "Tabata" in result or "HIIT" in result
    
    def test_constraint_violation_unknown(self):
        """Test unknown constraint returns original with highlight."""
        error = Exception('violates check constraint "some_unknown_constraint"')
        result = enhance_error_message(error)
        
        assert "some_unknown_constraint" in result
        assert "Constraint violation" in result
    
    def test_unique_constraint_violation(self):
        """Test unique constraint error."""
        error = Exception('duplicate key value violates unique constraint "people_pkey"')
        result = enhance_error_message(error)
        
        assert "Duplicate entry" in result
        assert "already exists" in result
    
    def test_foreign_key_violation(self):
        """Test foreign key constraint error."""
        error = Exception('violates foreign key constraint "fk_event_location"')
        result = enhance_error_message(error)
        
        assert "Foreign key violation" in result
        assert "does not exist" in result
    
    def test_not_null_violation(self):
        """Test not-null constraint error."""
        error = Exception('null value in column "title" of relation "events" violates not-null constraint')
        result = enhance_error_message(error)
        
        assert "Required field missing" in result
        assert "title" in result
        assert "cannot be null" in result
    
    def test_unrecognized_error_passes_through(self):
        """Test that unrecognized errors pass through unchanged."""
        error = Exception('Some random database error occurred')
        result = enhance_error_message(error)
        
        assert result == 'Some random database error occurred'


class TestGetEnumValues:
    """Test enum value lookup."""
    
    def test_known_enum(self):
        """Test getting values for known enum."""
        values = get_enum_values("event_category_enum")
        
        assert values is not None
        assert "health" in values
        assert "social" in values
        assert len(values) == 12
    
    def test_unknown_enum(self):
        """Test getting values for unknown enum returns None."""
        values = get_enum_values("nonexistent_enum")
        
        assert values is None


class TestFormatEnumHint:
    """Test enum hint formatting."""
    
    def test_known_enum_hint(self):
        """Test hint for known enum."""
        hint = format_enum_hint("transport_mode_enum")
        
        assert "transport_mode_enum" in hint
        assert "driving" in hint
        assert "walking" in hint
    
    def test_unknown_enum_hint(self):
        """Test hint for unknown enum returns empty."""
        hint = format_enum_hint("nonexistent_enum")
        
        assert hint == ""
