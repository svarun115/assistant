"""
Tests for automatic reciprocal relationship triggers

These tests verify that the database automatically creates, updates, and deletes
reciprocal relationships when person_relationships are modified.
"""

import pytest
import asyncio
import asyncpg
import sys
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.test_fixtures import TestDatabase
from database import DatabaseConnection
# Note: Shared fixtures (event_loop, setup_test_database, db_conn) 
# are defined in conftest.py and automatically available


@pytest.fixture
async def db_pool(db_conn):
    """Provide database pool for relationship trigger tests"""
    pool = db_conn.pool
    
    # Clean up test data before running test
    # Delete relationships first (before people to avoid FK violations)
    # Delete people WHERE they are NOT in the seed data
    async with pool.acquire() as conn:
        # Disable triggers during cleanup to avoid the "tuple already modified" error
        await conn.execute("SET session_replication_role = replica")
        await conn.execute("DELETE FROM person_relationships")
        await conn.execute("DELETE FROM people WHERE canonical_name NOT IN ('Gauri', 'Anmol', 'Ash')")  # Keep seed data
        await conn.execute("SET session_replication_role = DEFAULT")
    
    yield pool
    
    # Close pool after test
    await pool.close()


class TestTriggerExistence:
    """Test that triggers are properly created in the database"""
    
    @pytest.mark.asyncio
    async def test_triggers_exist(self, db_pool):
        """Verify all three relationship triggers exist"""
        async with db_pool.acquire() as conn:
            triggers = await conn.fetch("""
                SELECT trigger_name, event_manipulation, action_timing
                FROM information_schema.triggers
                WHERE event_object_table = 'person_relationships'
                ORDER BY trigger_name
            """)
        
        trigger_names = [t['trigger_name'] for t in triggers]
        
        # Verify all three triggers exist
        assert 'trigger_create_reciprocal_relationship' in trigger_names
        assert 'trigger_update_reciprocal_relationship' in trigger_names
        assert 'trigger_delete_reciprocal_relationship' in trigger_names
        
        # Verify trigger timings
        trigger_dict = {t['trigger_name']: t for t in triggers}
        
        assert trigger_dict['trigger_create_reciprocal_relationship']['event_manipulation'] == 'INSERT'
        assert trigger_dict['trigger_create_reciprocal_relationship']['action_timing'] == 'AFTER'
        
        assert trigger_dict['trigger_update_reciprocal_relationship']['event_manipulation'] == 'UPDATE'
        assert trigger_dict['trigger_update_reciprocal_relationship']['action_timing'] == 'AFTER'
        
        assert trigger_dict['trigger_delete_reciprocal_relationship']['event_manipulation'] == 'DELETE'
        assert trigger_dict['trigger_delete_reciprocal_relationship']['action_timing'] == 'BEFORE'
    
    @pytest.mark.asyncio
    async def test_helper_function_exists(self, db_pool):
        """Verify the reciprocal relationship type mapping function exists"""
        async with db_pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM pg_proc 
                    WHERE proname = 'get_reciprocal_relationship_type'
                )
            """)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_all_trigger_functions_exist(self, db_pool):
        """Verify all trigger functions are created"""
        async with db_pool.acquire() as conn:
            functions = await conn.fetch("""
                SELECT proname 
                FROM pg_proc 
                WHERE proname LIKE '%reciprocal%'
                ORDER BY proname
            """)
        
        function_names = [f['proname'] for f in functions]
        
        assert 'create_reciprocal_relationship' in function_names
        assert 'update_reciprocal_relationship' in function_names
        assert 'delete_reciprocal_relationship' in function_names
        assert 'get_reciprocal_relationship_type' in function_names


class TestAsymmetricRelationships:
    """Test asymmetric relationships (parent↔child, grandparent↔grandchild, etc.)"""
    
    @pytest.mark.asyncio
    async def test_parent_child_relationship(self, db_pool):
        """Test parent creates child reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            parent_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Alice Parent', 'family', 'family') RETURNING id"
            )
            child_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Bob Child', 'family', 'family') RETURNING id"
            )
            
            # Create parent relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type, notes)
                VALUES ($1, $2, 'parent', 'Alice is Bob''s parent')
            """, parent_id, child_id)
            
            # Check reciprocal was created
            relationships = await conn.fetch("""
                SELECT 
                    p1.canonical_name as person,
                    pr.relationship_type,
                    p2.canonical_name as related_to,
                    pr.notes
                FROM person_relationships pr
                JOIN people p1 ON pr.person_id = p1.id
                JOIN people p2 ON pr.related_person_id = p2.id
                WHERE p1.id IN ($1, $2) OR p2.id IN ($1, $2)
                ORDER BY p1.canonical_name
            """, parent_id, child_id)
            
            assert len(relationships) == 2
            
            # Find the manual and auto-created relationships
            manual = [r for r in relationships if 'Auto-created' not in r['notes']][0]
            auto = [r for r in relationships if 'Auto-created' in r['notes']][0]
            
            # Verify manual relationship
            assert manual['person'] == 'Alice Parent'
            assert manual['relationship_type'] == 'parent'
            assert manual['related_to'] == 'Bob Child'
            
            # Verify reciprocal
            assert auto['person'] == 'Bob Child'
            assert auto['relationship_type'] == 'child'
            assert auto['related_to'] == 'Alice Parent'
            assert auto['notes'] == 'Auto-created reciprocal relationship'
    
    @pytest.mark.asyncio
    async def test_grandparent_grandchild_relationship(self, db_pool):
        """Test grandparent creates grandchild reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            gp_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Grandma', 'family', 'family') RETURNING id"
            )
            gc_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Grandson', 'family', 'family') RETURNING id"
            )
            
            # Create grandparent relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'grandparent')
            """, gp_id, gc_id)
            
            # Check reciprocal - should have exactly 2 relationships between these two people
            relationships = await conn.fetch("""
                SELECT relationship_type, notes
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
                ORDER BY relationship_type
            """, gp_id, gc_id)
            
            assert len(relationships) == 2, f"Expected 2 relationships, found {len(relationships)}"
            assert relationships[0]['relationship_type'] == 'grandparent'
            assert relationships[1]['relationship_type'] == 'grandchild'
            
            # Verify one is auto-created
            auto_created = [r for r in relationships if r['notes'] == 'Auto-created reciprocal relationship']
            assert len(auto_created) == 1, "Should have exactly one auto-created relationship"
    
    @pytest.mark.asyncio
    async def test_aunt_uncle_niece_nephew_relationship(self, db_pool):
        """Test aunt_uncle creates niece_nephew reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            aunt_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Aunt Sarah', 'family', 'family') RETURNING id"
            )
            nephew_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Nephew Tom', 'family', 'family') RETURNING id"
            )
            
            # Create aunt_uncle relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'aunt_uncle')
            """, aunt_id, nephew_id)
            
            # Check reciprocal - should have exactly 2 relationships between these two people
            relationships = await conn.fetch("""
                SELECT person_id, relationship_type, notes
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
                ORDER BY relationship_type
            """, aunt_id, nephew_id)
            
            assert len(relationships) == 2, f"Expected 2 relationships, found {len(relationships)}"
            types = [r['relationship_type'] for r in relationships]
            assert 'aunt_uncle' in types
            assert 'niece_nephew' in types
            
            # Verify one is auto-created
            auto_created = [r for r in relationships if r['notes'] == 'Auto-created reciprocal relationship']
            assert len(auto_created) == 1, "Should have exactly one auto-created relationship"


class TestSymmetricRelationships:
    """Test symmetric relationships (spouse↔spouse, sibling↔sibling, cousin↔cousin)"""
    
    @pytest.mark.asyncio
    async def test_sibling_relationship(self, db_pool):
        """Test sibling creates sibling reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            sib1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Brother John', 'family', 'family') RETURNING id"
            )
            sib2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Sister Jane', 'family', 'family') RETURNING id"
            )
            
            # Create sibling relationship - trigger should fire
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'sibling')
            """, sib1_id, sib2_id)
            
            # Check reciprocal - should have exactly 2 relationships between these two people
            relationships = await conn.fetch("""
                SELECT person_id, relationship_type, notes
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
                ORDER BY person_id
            """, sib1_id, sib2_id)
            
            assert len(relationships) == 2, f"Expected 2 relationships, found {len(relationships)}"
            assert all(r['relationship_type'] == 'sibling' for r in relationships)
            
            # One should be manual, one auto
            manual = [r for r in relationships if 'Auto-created' not in (r['notes'] or '')]
            auto = [r for r in relationships if 'Auto-created' in (r['notes'] or '')]
            assert len(manual) == 1, f"Expected 1 manual relationship, found {len(manual)}"
            assert len(auto) == 1, f"Expected 1 auto relationship, found {len(auto)}"
    
    @pytest.mark.asyncio
    async def test_spouse_relationship(self, db_pool):
        """Test spouse creates spouse reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            spouse1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Husband', 'family', 'family') RETURNING id"
            )
            spouse2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Wife', 'family', 'family') RETURNING id"
            )
            
            # Create spouse relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'spouse')
            """, spouse1_id, spouse2_id)
            
            # Check reciprocal - should have exactly 2 relationships between these two people
            relationships = await conn.fetch("""
                SELECT person_id, relationship_type, notes
                FROM person_relationships
                WHERE relationship_type = 'spouse'
                  AND ((person_id = $1 AND related_person_id = $2)
                    OR (person_id = $2 AND related_person_id = $1))
            """, spouse1_id, spouse2_id)
            
            assert len(relationships) == 2, f"Expected 2 spouse relationships, found {len(relationships)}"
            
            # Verify one is auto-created
            auto_created = [r for r in relationships if r['notes'] == 'Auto-created reciprocal relationship']
            assert len(auto_created) == 1, "Should have exactly one auto-created relationship"
    
    @pytest.mark.asyncio
    async def test_cousin_relationship(self, db_pool):
        """Test cousin creates cousin reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            cousin1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Cousin Mike', 'family', 'family') RETURNING id"
            )
            cousin2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Cousin Lisa', 'family', 'family') RETURNING id"
            )
            
            # Create cousin relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'cousin')
            """, cousin1_id, cousin2_id)
            
            # Check reciprocal - should have exactly 2 relationships between these two people
            relationships = await conn.fetch("""
                SELECT relationship_type, notes
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
            """, cousin1_id, cousin2_id)
            
            assert len(relationships) == 2, f"Expected 2 relationships, found {len(relationships)}"
            assert all(r['relationship_type'] == 'cousin' for r in relationships)
            
            # Verify one is auto-created
            auto_created = [r for r in relationships if r['notes'] == 'Auto-created reciprocal relationship']
            assert len(auto_created) == 1, "Should have exactly one auto-created relationship"


class TestUpdateTrigger:
    """Test that updating a relationship updates its reciprocal"""
    
    @pytest.mark.asyncio
    async def test_update_relationship_type(self, db_pool):
        """Test changing relationship type updates reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            person1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Person 1', 'family', 'family') RETURNING id"
            )
            person2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Person 2', 'family', 'family') RETURNING id"
            )
            
            # Create parent relationship
            rel_id = await conn.fetchval("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'parent')
                RETURNING id
            """, person1_id, person2_id)
            
            # Verify initial state - should have exactly 2 relationships between these two people
            initial = await conn.fetch("""
                SELECT relationship_type
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
                ORDER BY relationship_type
            """, person1_id, person2_id)
            
            assert len(initial) == 2, f"Expected 2 initial relationships, found {len(initial)}"
            types = [r['relationship_type'] for r in initial]
            assert 'parent' in types and 'child' in types
            
            # Update to grandparent
            await conn.execute("""
                UPDATE person_relationships
                SET relationship_type = 'grandparent'
                WHERE id = $1
            """, rel_id)
            
            # Verify reciprocal updated - should still have exactly 2 relationships
            updated = await conn.fetch("""
                SELECT relationship_type
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
                ORDER BY relationship_type
            """, person1_id, person2_id)
            
            assert len(updated) == 2, f"Expected 2 updated relationships, found {len(updated)}"
            types = [r['relationship_type'] for r in updated]
            assert 'grandparent' in types and 'grandchild' in types


class TestDeleteTrigger:
    """Test that deleting a relationship deletes its reciprocal"""
    
    @pytest.mark.asyncio
    async def test_delete_removes_both_directions(self, db_pool):
        """Test deleting one direction deletes both"""
        async with db_pool.acquire() as conn:
            # Create two people
            person1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Delete Test 1', 'family', 'family') RETURNING id"
            )
            person2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Delete Test 2', 'family', 'family') RETURNING id"
            )
            
            # Create parent relationship
            rel_id = await conn.fetchval("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'parent')
                RETURNING id
            """, person1_id, person2_id)
            
            # Verify both exist - should have exactly 2 relationships
            initial_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
            """, person1_id, person2_id)
            
            assert initial_count == 2, f"Expected 2 initial relationships, found {initial_count}"
            
            # Delete the manual relationship
            await conn.execute("""
                DELETE FROM person_relationships WHERE id = $1
            """, rel_id)
            
            # Verify both are gone - should have 0 relationships
            final_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
            """, person1_id, person2_id)
            
            assert final_count == 0, f"Expected 0 final relationships, found {final_count}"
    
    @pytest.mark.asyncio
    async def test_no_infinite_loop_on_delete(self, db_pool):
        """Test that delete trigger doesn't cause infinite loop"""
        async with db_pool.acquire() as conn:
            # Create two people
            person1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Loop Test 1', 'family', 'family') RETURNING id"
            )
            person2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Loop Test 2', 'family', 'family') RETURNING id"
            )
            
            # Create sibling relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'sibling')
            """, person1_id, person2_id)
            
            # Delete should complete without hanging
            # (If there's an infinite loop, this will timeout)
            await conn.execute("""
                DELETE FROM person_relationships
                WHERE person_id = $1 AND related_person_id = $2
            """, person1_id, person2_id)
            
            # Verify all relationships are gone
            count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
            """, person1_id, person2_id)
            
            assert count == 0


class TestEdgeCases:
    """Test edge cases and constraints"""
    
    @pytest.mark.asyncio
    async def test_no_duplicate_relationships(self, db_pool):
        """Test that duplicate relationships are prevented"""
        async with db_pool.acquire() as conn:
            # Create two people
            person1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Dup Test 1', 'family', 'family') RETURNING id"
            )
            person2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Dup Test 2', 'family', 'family') RETURNING id"
            )
            
            # Create first relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'sibling')
            """, person1_id, person2_id)
            
            # Try to create duplicate - should fail
            with pytest.raises(Exception):  # Unique constraint violation
                await conn.execute("""
                    INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                    VALUES ($1, $2, 'sibling')
                """, person1_id, person2_id)
    
    @pytest.mark.asyncio
    async def test_no_self_relationships(self, db_pool):
        """Test that self-relationships are prevented"""
        async with db_pool.acquire() as conn:
            # Create person
            person_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Self Test', 'family', 'family') RETURNING id"
            )
            
            # Try to create self-relationship - should fail
            with pytest.raises(Exception):  # Check constraint violation
                await conn.execute("""
                    INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                    VALUES ($1, $1, 'sibling')
                """, person_id)
    
    @pytest.mark.asyncio
    async def test_other_relationship_type(self, db_pool):
        """Test 'other' relationship type creates reciprocal"""
        async with db_pool.acquire() as conn:
            # Create two people
            person1_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Other Test 1', 'family', 'family') RETURNING id"
            )
            person2_id = await conn.fetchval(
                "INSERT INTO people (canonical_name, relationship, category) "
                "VALUES ('Other Test 2', 'family', 'family') RETURNING id"
            )
            
            # Create 'other' relationship
            await conn.execute("""
                INSERT INTO person_relationships (person_id, related_person_id, relationship_type, notes)
                VALUES ($1, $2, 'other', 'Step-parent')
            """, person1_id, person2_id)
            
            # Check reciprocal was created (also as 'other')
            relationships = await conn.fetch("""
                SELECT relationship_type
                FROM person_relationships
                WHERE (person_id = $1 AND related_person_id = $2)
                   OR (person_id = $2 AND related_person_id = $1)
            """, person1_id, person2_id)
            
            assert len(relationships) == 2
            assert all(r['relationship_type'] == 'other' for r in relationships)


class TestCompleteEnumCoverage:
    """Test that all enum values have proper trigger support"""
    
    @pytest.mark.asyncio
    async def test_all_relationship_types_covered(self, db_pool):
        """Verify all family_relationship_type enum values work with triggers"""
        async with db_pool.acquire() as conn:
            # Get all enum values
            enum_values = await conn.fetch("""
                SELECT unnest(enum_range(NULL::family_relationship_type))::text as type
            """)
            
            enum_types = [e['type'] for e in enum_values]
            
            # Expected enum values
            expected = [
                'spouse', 'parent', 'child', 'sibling',
                'grandparent', 'grandchild', 'aunt_uncle',
                'niece_nephew', 'cousin', 'other'
            ]
            
            assert set(enum_types) == set(expected)
            
            # Test each type can create relationships
            for rel_type in enum_types:
                # Create two people for this test
                p1_id = await conn.fetchval(
                    f"INSERT INTO people (canonical_name, relationship, category) "
                    f"VALUES ('{rel_type}_person1', 'family', 'family') RETURNING id"
                )
                p2_id = await conn.fetchval(
                    f"INSERT INTO people (canonical_name, relationship, category) "
                    f"VALUES ('{rel_type}_person2', 'family', 'family') RETURNING id"
                )
                
                # Create relationship
                await conn.execute(f"""
                    INSERT INTO person_relationships (person_id, related_person_id, relationship_type)
                    VALUES ($1, $2, $3)
                """, p1_id, p2_id, rel_type)
                
                # Verify reciprocal exists
                count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM person_relationships
                    WHERE (person_id = $1 AND related_person_id = $2)
                       OR (person_id = $2 AND related_person_id = $1)
                """, p1_id, p2_id)
                
                assert count == 2, f"Failed to create reciprocal for {rel_type}"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
