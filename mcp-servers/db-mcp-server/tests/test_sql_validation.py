#!/usr/bin/env python3
"""
Test script for SQL query validation (Issue #56)
Tests that legitimate read-only SELECT queries are allowed
"""

import sys
from handlers.core_handlers import validate_query_security

# Test cases: (query, should_pass, description)
test_cases = [
    # Issue #56 failing cases (should all pass now)
    (
        "SELECT COUNT(*) as total FROM events WHERE is_deleted = false",
        True,
        "COUNT with WHERE is_deleted filter"
    ),
    (
        "SELECT id, title, start_time FROM events WHERE is_deleted = false ORDER BY start_time",
        True,
        "ORDER BY clause"
    ),
    (
        "SELECT COUNT(DISTINCT DATE(start_time)) as days_migrated FROM events WHERE is_deleted = false",
        True,
        "COUNT(DISTINCT ...) aggregation"
    ),
    (
        "SELECT * FROM events WHERE is_deleted = false LIMIT 20",
        True,
        "Complex filtering with LIMIT"
    ),
    
    # Simple queries that were working
    (
        "SELECT * FROM workouts LIMIT 10",
        True,
        "Simple SELECT with LIMIT"
    ),
    (
        "SELECT * FROM workout_events LIMIT 20",
        True,
        "SELECT from view with LIMIT"
    ),
    (
        "SELECT * FROM events LIMIT 1",
        True,
        "Simple SELECT LIMIT 1"
    ),
    
    # Additional complex but legitimate queries
    (
        "SELECT e.id, e.title, COUNT(p.id) as participant_count FROM events e LEFT JOIN event_participants p ON e.id = p.event_id WHERE e.is_deleted = false GROUP BY e.id ORDER BY participant_count DESC",
        True,
        "Complex join with aggregation"
    ),
    (
        "WITH recent_events AS (SELECT * FROM events WHERE is_deleted = false ORDER BY start_time DESC LIMIT 10) SELECT * FROM recent_events",
        True,
        "CTE with SELECT"
    ),
    (
        "SELECT DATE(start_time) as event_date, COUNT(*) as count FROM events WHERE is_deleted = false GROUP BY DATE(start_time) ORDER BY event_date DESC",
        True,
        "Grouping by computed expression"
    ),
    (
        "EXPLAIN SELECT * FROM events WHERE id = '123'",
        True,
        "EXPLAIN query"
    ),
    
    # Should still be blocked - write operations
    (
        "INSERT INTO events (title) VALUES ('test')",
        False,
        "INSERT blocked"
    ),
    (
        "UPDATE events SET title = 'new' WHERE id = '1'",
        False,
        "UPDATE blocked"
    ),
    (
        "DELETE FROM events WHERE id = '1'",
        False,
        "DELETE blocked"
    ),
    (
        "CREATE TABLE test (id UUID)",
        False,
        "CREATE TABLE blocked"
    ),
    (
        "DROP TABLE events",
        False,
        "DROP TABLE blocked"
    ),
    (
        "ALTER TABLE events ADD COLUMN test TEXT",
        False,
        "ALTER blocked"
    ),
    (
        "GRANT SELECT ON events TO user",
        False,
        "GRANT blocked"
    ),
    (
        "TRUNCATE events",
        False,
        "TRUNCATE blocked"
    ),
    (
        "VACUUM events",
        False,
        "VACUUM blocked"
    ),
]


def run_tests():
    """Run all test cases and report results"""
    passed = 0
    failed = 0
    
    print("=" * 80)
    print("SQL Query Validation Tests (Issue #56)")
    print("=" * 80)
    
    for query, should_pass, description in test_cases:
        is_safe, error_msg = validate_query_security(query)
        
        # Check if result matches expectation
        test_passed = is_safe == should_pass
        
        status = "✅ PASS" if test_passed else "❌ FAIL"
        print(f"\n{status}: {description}")
        print(f"   Query: {query[:70]}{'...' if len(query) > 70 else ''}")
        print(f"   Expected: {'ALLOWED' if should_pass else 'BLOCKED'}")
        print(f"   Got: {'ALLOWED' if is_safe else 'BLOCKED'}")
        if not is_safe:
            print(f"   Error: {error_msg}")
        
        if test_passed:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
