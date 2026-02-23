#!/usr/bin/env python3
"""
Unified backup script for Personal Journal database.

Creates complete snapshots of:
- Events (workouts, meals, commutes, sleep, health, entertainment, etc.)
- People (with work, education, residence histories, notes, relationships)
- Locations
- Exercises catalog

Usage:
    python backup_json.py backup/snapshots/20251118_204039
    Custom DB: python backup_json.py backup/snapshots/20251118_204039 --db=my_database
"""

import json
import psycopg2
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import sys

# Default database connection
DEFAULT_DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST'),
    'port': int(os.getenv('POSTGRES_PORT')) if os.getenv('POSTGRES_PORT') else None,
    'database': os.getenv('POSTGRES_DB'),
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD')
}

def backup_database(output_dir: str, db_config: dict = None):
    """
    Create complete database backup (events + people).
    
    Args:
        output_dir: Output directory path
        db_config: Database connection config
    """
    
    if db_config is None:
        db_config = DEFAULT_DB_CONFIG
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    
    print(f"\n{'='*60}")
    print(f"[BACKUP] DATABASE - SNAPSHOT MODE")
    print(f"{'='*60}")
    print(f"Source DB: {db_config['database']}@{db_config['host']}")
    print(f"Output: {output_path}")
    print(f"{'='*60}\n")
    
    try:
        # 1. Export locations (always full export)
        print("  |- Exporting locations...")
        cur.execute("""
            SELECT id, canonical_name, place_id, location_type, notes, created_at
            FROM locations
            WHERE is_deleted = false
            ORDER BY canonical_name
        """)
        
        locations = []
        for row in cur.fetchall():
            locations.append({
                'id': str(row[0]),
                'canonical_name': row[1],
                'place_id': row[2],
                'location_type': row[3],
                'notes': row[4],
                'created_at': row[5].isoformat() if row[5] else None
            })
        
        with open(output_path / 'locations.json', 'w', encoding='utf-8') as f:
            json.dump(locations, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(locations)} locations")
        
        # 2. Export people (always full export)
        print("  |- Exporting people...")
        cur.execute("""
            SELECT 
                id, canonical_name, aliases, relationship, category, birthday, death_date,
                ethnicity, origin_location, known_since, last_interaction_date, 
                google_people_id, created_at, updated_at
            FROM people 
            WHERE is_deleted = false
            ORDER BY canonical_name
        """)
        
        people_full = []
        for row in cur.fetchall():
            person = {
                'id': str(row[0]),
                'canonical_name': row[1],
                'aliases': row[2] or [],
                'relationship': row[3],
                'category': row[4],
                'birthday': row[5],
                'death_date': row[6],
                'ethnicity': row[7],
                'origin_location': row[8],
                'known_since': row[9],
                'last_interaction_date': row[10],
                'google_people_id': row[11],
                'created_at': row[12].isoformat() if row[12] else None,
                'updated_at': row[13].isoformat() if row[13] else None
            }
            people_full.append(person)
        
        # Add full details for each person
        for person in people_full:
            person_id = person['id']
            
            # Work history
            cur.execute("""
                SELECT 
                    pw.id, pw.company, pw.role, pw.notes,
                    tl.start_date, tl.end_date, tl.is_current,
                    l.id as location_id, l.canonical_name as location_name, l.place_id
                FROM person_work pw
                JOIN temporal_locations tl ON pw.temporal_location_id = tl.id
                JOIN locations l ON tl.location_id = l.id
                WHERE pw.person_id = %s
                ORDER BY tl.start_date DESC NULLS LAST
            """, (person_id,))
            
            work_history = []
            for w in cur.fetchall():
                work_history.append({
                    'id': str(w[0]),
                    'company': w[1],
                    'role': w[2],
                    'notes': w[3],
                    'start_date': w[4],
                    'end_date': w[5],
                    'is_current': w[6],
                    'location': {'id': str(w[7]), 'name': w[8], 'place_id': w[9]}
                })
            person['work_history'] = work_history
            
            # Education history
            cur.execute("""
                SELECT 
                    pe.id, pe.institution, pe.degree, pe.field, pe.notes,
                    tl.start_date, tl.end_date, tl.is_current,
                    l.id as location_id, l.canonical_name as location_name, l.place_id
                FROM person_education pe
                JOIN temporal_locations tl ON pe.temporal_location_id = tl.id
                JOIN locations l ON tl.location_id = l.id
                WHERE pe.person_id = %s
                ORDER BY tl.start_date DESC NULLS LAST
            """, (person_id,))
            
            education_history = []
            for e in cur.fetchall():
                education_history.append({
                    'id': str(e[0]),
                    'institution': e[1],
                    'degree': e[2],
                    'field': e[3],
                    'notes': e[4],
                    'start_date': e[5],
                    'end_date': e[6],
                    'is_current': e[7],
                    'location': {'id': str(e[8]), 'name': e[9], 'place_id': e[10]}
                })
            person['education_history'] = education_history
            
            # Residence history (include is_deleted for full backup)
            cur.execute("""
                SELECT 
                    pr.id, pr.notes, pr.is_deleted, pr.deleted_at,
                    tl.start_date, tl.end_date, tl.is_current,
                    l.id as location_id, l.canonical_name as location_name, l.place_id
                FROM person_residences pr
                JOIN temporal_locations tl ON pr.temporal_location_id = tl.id
                JOIN locations l ON tl.location_id = l.id
                WHERE pr.person_id = %s
                ORDER BY tl.start_date DESC NULLS LAST
            """, (person_id,))
            
            residence_history = []
            for r in cur.fetchall():
                residence_history.append({
                    'id': str(r[0]),
                    'notes': r[1],
                    'is_deleted': r[2],
                    'deleted_at': r[3].isoformat() if r[3] else None,
                    'start_date': r[4],
                    'end_date': r[5],
                    'is_current': r[6],
                    'location': {'id': str(r[7]), 'name': r[8], 'place_id': r[9]}
                })
            person['residence_history'] = residence_history
            
            # Biographical notes
            cur.execute("""
                SELECT id, note_date, note_type, category, text, source, context, tags
                FROM person_notes
                WHERE person_id = %s
                ORDER BY created_at DESC
            """, (person_id,))
            
            notes = []
            for n in cur.fetchall():
                notes.append({
                    'id': str(n[0]),
                    'date': n[1],
                    'type': n[2],
                    'category': n[3],
                    'text': n[4],
                    'source': n[5],
                    'context': n[6],
                    'tags': n[7] or []
                })
            person['notes'] = notes
            
            # Relationships
            cur.execute("""
                SELECT 
                    pr.id, pr.relationship_type, pr.notes,
                    p2.id as related_person_id, p2.canonical_name as related_person_name
                FROM person_relationships pr
                JOIN people p2 ON pr.related_person_id = p2.id
                WHERE pr.person_id = %s
                ORDER BY pr.relationship_type, p2.canonical_name
            """, (person_id,))
            
            relationships = []
            for rel in cur.fetchall():
                relationships.append({
                    'id': str(rel[0]),
                    'relationship_type': rel[1],
                    'notes': rel[2],
                    'related_person': {'id': str(rel[3]), 'name': rel[4]}
                })
            person['relationships'] = relationships
        
        with open(output_path / 'people.json', 'w', encoding='utf-8') as f:
            json.dump(people_full, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(people_full)} people with full histories")
        
        # 3. Export relationships
        print("  |- Exporting relationships...")
        cur.execute("""
            SELECT 
                pr.id, 
                p1.id as person_id, p1.canonical_name as person_name,
                pr.relationship_type,
                p2.id as related_person_id, p2.canonical_name as related_person_name,
                pr.notes
            FROM person_relationships pr
            JOIN people p1 ON pr.person_id = p1.id
            JOIN people p2 ON pr.related_person_id = p2.id
            WHERE p1.is_deleted = false AND p2.is_deleted = false
            ORDER BY p1.canonical_name, pr.relationship_type
        """)
        
        relationships = []
        for rel in cur.fetchall():
            relationships.append({
                'id': str(rel[0]),
                'person': {'id': str(rel[1]), 'name': rel[2]},
                'relationship_type': rel[3],
                'related_person': {'id': str(rel[4]), 'name': rel[5]},
                'notes': rel[6]
            })
        
        with open(output_path / 'relationships.json', 'w', encoding='utf-8') as f:
            json.dump(relationships, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(relationships)} relationships")
        
        # 4. Export events
        print("  |- Exporting events...")
        cur.execute(f"""
            SELECT 
                e.id, e.event_type, e.title, e.description, e.start_time, e.end_time,
                e.category, e.significance, e.tags, e.notes,
                e.parent_event_id, e.source_event_id, e.source_person_id,
                e.information_source, e.source_confidence,
                e.external_event_id,
                l.id as location_id, l.canonical_name as location_name, l.place_id,
                e.created_at, e.updated_at
            FROM events e
            LEFT JOIN locations l ON e.location_id = l.id
            WHERE e.deleted_at IS NULL
            ORDER BY e.start_time
        """)
        
        events = []
        for row in cur.fetchall():
            event = {
                'id': str(row[0]),
                'event_type': row[1],
                'title': row[2],
                'description': row[3],
                'start_time': row[4].isoformat() if row[4] else None,
                'end_time': row[5].isoformat() if row[5] else None,
                'category': row[6],
                'significance': row[7],
                'tags': row[8] or [],
                'notes': row[9],
                'parent_event_id': str(row[10]) if row[10] else None,
                'source_event_id': str(row[11]) if row[11] else None,
                'source_person_id': str(row[12]) if row[12] else None,
                'information_source': row[13],
                'source_confidence': row[14],
                'external_event_id': row[15],
                'location': {
                    'id': str(row[16]),
                    'name': row[17],
                    'place_id': row[18]
                } if row[16] else None,
                'created_at': row[19].isoformat() if row[19] else None,
                'updated_at': row[20].isoformat() if row[20] else None
            }
            events.append(event)
        
        # Add participants to each event
        for event in events:
            cur.execute("""
                SELECT p.id, p.canonical_name
                FROM event_participants ep
                JOIN people p ON ep.person_id = p.id
                WHERE ep.event_id = %s
                ORDER BY p.canonical_name
            """, (event['id'],))
            
            event['participants'] = [
                {'id': str(p[0]), 'name': p[1]}
                for p in cur.fetchall()
            ]
        
        with open(output_path / 'events.json', 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(events)} events")
        
        # Get event IDs for specialized queries
        event_ids = [e['id'] for e in events]
        if not event_ids:
            event_ids = ['00000000-0000-0000-0000-000000000000']
        
        # 5. Export workouts
        print("  |- Exporting workouts...")
        placeholders = ','.join(['%s'] * len(event_ids))
        cur.execute(f"""
            SELECT 
                w.id, w.event_id, w.workout_name, w.category, w.workout_subtype, w.sport_type
            FROM workouts w
            WHERE w.event_id IN ({placeholders}) AND w.is_deleted = false
        """, event_ids)
        
        workouts = []
        for row in cur.fetchall():
            workout_id = row[0]
            workout = {
                'event_id': str(row[1]),
                'workout_name': row[2],
                'category': row[3],
                'workout_subtype': row[4],
                'sport_type': row[5],
                'exercises': []
            }
            
            # Get exercises
            cur.execute("""
                SELECT 
                    we.id, we.sequence_order, we.notes, we.rest_between_exercises_s,
                    ex.id, ex.canonical_name, ex.category, ex.primary_muscle_group
                FROM workout_exercises we
                JOIN exercises ex ON we.exercise_id = ex.id
                WHERE we.workout_id = %s
                ORDER BY we.sequence_order
            """, (workout_id,))
            
            for ex_row in cur.fetchall():
                workout_exercise_id = str(ex_row[0])
                exercise = {
                    'sequence_order': ex_row[1],
                    'notes': ex_row[2],
                    'rest_between_exercises_s': ex_row[3],
                    'exercise': {
                        'id': str(ex_row[4]),
                        'name': ex_row[5],
                        'category': ex_row[6],
                        'primary_muscle_group': ex_row[7]
                    },
                    'sets': []
                }
                
                # Get sets
                cur.execute("""
                    SELECT 
                        set_number, set_type, weight_kg, reps, duration_s, distance_km,
                        rest_time_s, pace, volume_kg, notes
                    FROM exercise_sets
                    WHERE workout_exercise_id = %s
                    ORDER BY set_number
                """, (workout_exercise_id,))
                
                for set_row in cur.fetchall():
                    exercise['sets'].append({
                        'set_number': set_row[0],
                        'set_type': set_row[1],
                        'weight_kg': float(set_row[2]) if set_row[2] else None,
                        'reps': set_row[3],
                        'duration_s': set_row[4],
                        'distance_km': float(set_row[5]) if set_row[5] else None,
                        'rest_time_s': set_row[6],
                        'pace': set_row[7],
                        'volume_kg': float(set_row[8]) if set_row[8] else None,
                        'notes': set_row[9]
                    })
                
                workout['exercises'].append(exercise)
            
            workouts.append(workout)
        
        with open(output_path / 'workouts.json', 'w', encoding='utf-8') as f:
            json.dump(workouts, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(workouts)} workouts")
        
        # 6. Export meals
        print("  |- Exporting meals...")
        cur.execute(f"""
            SELECT 
                m.id, m.event_id, m.meal_title, m.meal_type, m.portion_size
            FROM meals m
            WHERE m.event_id IN ({placeholders}) AND m.is_deleted = false
        """, event_ids)
        
        meals = []
        for row in cur.fetchall():
            meal_id = row[0]
            meal = {
                'event_id': str(row[1]),
                'meal_title': row[2],
                'meal_type': row[3],
                'portion_size': row[4],
                'items': []
            }
            
            cur.execute("""
                SELECT item_name, quantity
                FROM meal_items
                WHERE meal_id = %s
                ORDER BY created_at
            """, (meal_id,))
            
            for item in cur.fetchall():
                meal['items'].append({
                    'item_name': item[0],
                    'quantity': item[1]
                })
            
            meals.append(meal)
        
        with open(output_path / 'meals.json', 'w', encoding='utf-8') as f:
            json.dump(meals, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(meals)} meals")
        
        # 7. Export commutes
        print("  |- Exporting commutes...")
        cur.execute(f"""
            SELECT 
                c.event_id, c.transport_mode,
                l1.id, l1.canonical_name,
                l2.id, l2.canonical_name
            FROM commutes c
            LEFT JOIN locations l1 ON c.from_location_id = l1.id
            LEFT JOIN locations l2 ON c.to_location_id = l2.id
            WHERE c.event_id IN ({placeholders}) AND c.is_deleted = false
        """, event_ids)
        
        commutes = []
        for row in cur.fetchall():
            commutes.append({
                'event_id': str(row[0]),
                'transport_mode': row[1],
                'from_location': {'id': str(row[2]), 'name': row[3]} if row[2] else None,
                'to_location': {'id': str(row[4]), 'name': row[5]} if row[4] else None
            })
        
        with open(output_path / 'commutes.json', 'w', encoding='utf-8') as f:
            json.dump(commutes, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(commutes)} commutes")
        
        # 8. Export sleep
        print("  |- Exporting sleep...")
        cur.execute(f"""
            SELECT 
                s.event_id, s.sleep_date, s.sleep_time, s.wake_time, 
                s.duration_minutes, s.duration_hours, s.notes, s.tags
            FROM sleep_events s
            WHERE s.event_id IN ({placeholders})
        """, event_ids)
        
        sleep_entries = []
        for row in cur.fetchall():
            sleep_entries.append({
                'event_id': str(row[0]),
                'sleep_date': row[1].isoformat() if row[1] else None,
                'sleep_time': row[2].isoformat() if row[2] else None,
                'wake_time': row[3].isoformat() if row[3] else None,
                'duration_minutes': row[4],
                'duration_hours': float(row[5]) if row[5] else None,
                'notes': row[6],
                'tags': row[7] or []
            })
        
        with open(output_path / 'sleep.json', 'w', encoding='utf-8') as f:
            json.dump(sleep_entries, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(sleep_entries)} sleep entries")
        
        # 9. Export health data
        print("  |- Exporting health data...")
        
        cur.execute("""
            SELECT 
                id, event_id, condition_type, condition_name, severity, severity_score,
                start_date, end_date, is_sport_related, sport_type, notes
            FROM health_conditions
            WHERE is_deleted = false
        """)
        
        health_conditions = []
        for row in cur.fetchall():
            health_conditions.append({
                'id': str(row[0]),
                'event_id': str(row[1]) if row[1] else None,
                'condition_type': row[2],
                'condition_name': row[3],
                'severity': row[4],
                'severity_score': row[5],
                'start_date': row[6].isoformat() if row[6] else None,
                'end_date': row[7].isoformat() if row[7] else None,
                'is_sport_related': row[8],
                'sport_type': row[9],
                'notes': row[10]
            })
        
        cur.execute("""
            SELECT 
                id, medicine_name, dosage, dosage_unit, frequency,
                log_date, log_time, condition_id, event_id, notes
            FROM health_medicines
            WHERE is_deleted = false
        """)
        
        medicines = []
        for row in cur.fetchall():
            medicines.append({
                'id': str(row[0]),
                'medicine_name': row[1],
                'dosage': row[2],
                'dosage_unit': row[3],
                'frequency': row[4],
                'log_date': row[5].isoformat() if row[5] else None,
                'log_time': row[6].isoformat() if row[6] else None,
                'condition_id': str(row[7]) if row[7] else None,
                'event_id': str(row[8]) if row[8] else None,
                'notes': row[9]
            })
        
        cur.execute("""
            SELECT 
                id, supplement_name, amount, amount_unit, frequency,
                log_date, log_time, event_id, notes
            FROM health_supplements
            WHERE is_deleted = false
        """)
        
        supplements = []
        for row in cur.fetchall():
            supplements.append({
                'id': str(row[0]),
                'supplement_name': row[1],
                'amount': row[2],
                'amount_unit': row[3],
                'frequency': row[4],
                'log_date': row[5].isoformat() if row[5] else None,
                'log_time': row[6].isoformat() if row[6] else None,
                'event_id': str(row[7]) if row[7] else None,
                'notes': row[8]
            })
        
        health_data = {
            'conditions': health_conditions,
            'medicines': medicines,
            'supplements': supplements
        }
        
        with open(output_path / 'health.json', 'w', encoding='utf-8') as f:
            json.dump(health_data, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(health_conditions)} conditions, {len(medicines)} medicines, {len(supplements)} supplements")
        
        # 10. Export entertainment
        print("  |- Exporting entertainment...")
        cur.execute(f"""
            SELECT 
                e.event_id, e.entertainment_type, e.title, e.creator, e.genre,
                e.show_name, e.season_number, e.episode_number, e.episode_title,
                e.channel_name, e.video_url, e.director, e.release_year,
                e.performance_type, e.venue, e.performer_artist,
                e.game_platform, e.game_genre, e.platform, e.format,
                e.personal_rating, e.completion_status, e.rewatch, e.watched_with_others
            FROM entertainment e
            WHERE e.event_id IN ({placeholders}) AND e.is_deleted = false
        """, event_ids)
        
        entertainment = []
        for row in cur.fetchall():
            entertainment.append({
                'event_id': str(row[0]),
                'entertainment_type': row[1],
                'title': row[2],
                'creator': row[3],
                'genre': row[4],
                'show_name': row[5],
                'season_number': row[6],
                'episode_number': row[7],
                'episode_title': row[8],
                'channel_name': row[9],
                'video_url': row[10],
                'director': row[11],
                'release_year': row[12],
                'performance_type': row[13],
                'venue': row[14],
                'performer_artist': row[15],
                'game_platform': row[16],
                'game_genre': row[17],
                'platform': row[18],
                'format': row[19],
                'personal_rating': row[20],
                'completion_status': row[21],
                'rewatch': row[22],
                'watched_with_others': row[23]
            })
        
        with open(output_path / 'entertainment.json', 'w', encoding='utf-8') as f:
            json.dump(entertainment, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(entertainment)} entertainment entries")
        
        # 11. Export exercises catalog
        print("  |- Exporting exercises catalog...")
        cur.execute("""
            SELECT 
                id, canonical_name, category, primary_muscle_group, 
                secondary_muscle_groups, equipment, variants, notes
            FROM exercises
            WHERE is_deleted = false
            ORDER BY canonical_name
        """)
        
        exercises = []
        for row in cur.fetchall():
            exercises.append({
                'id': str(row[0]),
                'canonical_name': row[1],
                'category': row[2],
                'primary_muscle_group': row[3],
                'secondary_muscle_groups': row[4] or [],
                'equipment': row[5] or [],
                'variants': row[6] or [],
                'notes': row[7]
            })
        
        with open(output_path / 'exercises.json', 'w', encoding='utf-8') as f:
            json.dump(exercises, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(exercises)} exercises")
        
        # 12. Export journal days
        print("  |- Exporting journal days...")
        cur.execute("""
            SELECT 
                id, journal_date, day_title, day_rating, highlights,
                workout_count, meal_count, commute_count, entertainment_count,
                event_count, reflection_count, work_minutes, sleep_hours,
                total_commute_minutes, notes
            FROM journal_days
            ORDER BY journal_date
        """)
        
        journal_days = []
        for row in cur.fetchall():
            journal_days.append({
                'id': str(row[0]),
                'journal_date': row[1].isoformat() if row[1] else None,
                'day_title': row[2],
                'day_rating': row[3],
                'highlights': row[4] or [],
                'workout_count': row[5],
                'meal_count': row[6],
                'commute_count': row[7],
                'entertainment_count': row[8],
                'event_count': row[9],
                'reflection_count': row[10],
                'work_minutes': row[11],
                'sleep_hours': float(row[12]) if row[12] else None,
                'total_commute_minutes': row[13],
                'notes': row[14]
            })
        
        with open(output_path / 'journal_days.json', 'w', encoding='utf-8') as f:
            json.dump(journal_days, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Exported {len(journal_days)} journal days")
        
        # 13. Export metadata
        print("  |- Generating metadata...")
        
        # Get people counts
        cur.execute("SELECT COUNT(*) FROM person_work")
        work_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM person_education")
        education_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM person_residences")
        residence_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM person_notes")
        notes_count = cur.fetchone()[0]
        
        metadata = {
            'export_timestamp': datetime.now().isoformat(),
            'database': db_config['database'],
            'backup_mode': 'snapshot',
            'counts': {
                'events': len(events),
                'workouts': len(workouts),
                'meals': len(meals),
                'commutes': len(commutes),
                'sleep': len(sleep_entries),
                'health_conditions': len(health_conditions),
                'medicines': len(medicines),
                'supplements': len(supplements),
                'entertainment': len(entertainment),
                'exercises': len(exercises),
                'journal_days': len(journal_days),
                'people': len(people_full),
                'locations': len(locations),
                'relationships': len(relationships),
                'work_entries': work_count,
                'education_entries': education_count,
                'residence_entries': residence_count,
                'biographical_notes': notes_count
            },
            'schema_version': '1.0',
            'notes': 'Full snapshot of complete database (events + people)'
        }
        
        with open(output_path / 'metadata.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Generated metadata")
        
        print(f"\n{'='*60}")
        print(f"[OK] BACKUP COMPLETE")
        print(f"{'='*60}")
        print(f"Events: {len(events)}")
        print(f"People: {len(people_full)}")
        print(f"Locations: {len(locations)}")
        print(f"Output: {output_path}")
        print(f"{'='*60}\n")
        
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Unified backup for Personal Journal database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Snapshot backup
  python backup.py backup/snapshots/20251118_204039
  
  # Custom database
  python backup.py backup/snapshots/20251118_204039 --db=my_database
  
  # Full custom config
  python backup.py backup/snapshots/20251118_204039 --db=my_db --host=dbserver --port=5433
        """
    )
    
    parser.add_argument('output_dir', help='Output directory for backup')
    parser.add_argument('--db', '--database', dest='database', help='Database name')
    parser.add_argument('--host', default=os.getenv('POSTGRES_HOST'), help='Database host')
    parser.add_argument('--port', type=int, default=int(os.getenv('POSTGRES_PORT')) if os.getenv('POSTGRES_PORT') else None, help='Database port')
    parser.add_argument('--user', default=os.getenv('POSTGRES_USER'), help='Database user')
    parser.add_argument('--password', default=os.getenv('POSTGRES_PASSWORD'), help='Database password')
    
    args = parser.parse_args()
    
    # Build DB config
    db_config = {
        'host': args.host,
        'port': args.port,
        'database': args.database or DEFAULT_DB_CONFIG['database'],
        'user': args.user,
        'password': args.password
    }
    
    backup_database(args.output_dir, db_config)
