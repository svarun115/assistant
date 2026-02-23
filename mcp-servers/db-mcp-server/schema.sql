-- ============================================================================
-- Personal Journal Database Schema - PostgreSQL (Event-Centric Architecture)
-- Optimized for LLM queries via MCP server
-- 
-- ARCHITECTURE: Events are the primary aggregate root
-- - Events own common attributes: WHO (participants), WHERE (location), WHEN (time)
-- - Workouts, Meals, etc. are specializations that reference events
-- - This eliminates duplication and creates a cleaner mental model
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

-- Person relationship types
CREATE TYPE person_relationship_enum AS ENUM (
    'friend',
    'family',
    'colleague',
    'partner',
    'acquaintance',
    'mentor',
    'mentee',
    'other'
);

-- Person category types
CREATE TYPE person_category_enum AS ENUM (
    'close_friend',
    'friend',
    'acquaintance',
    'family',
    'work',
    'not_met',
    'other'
);

-- Family relationship types (for person_relationships table)
CREATE TYPE family_relationship_type AS ENUM (
    'spouse',
    'parent',
    'child',
    'sibling',
    'grandparent',
    'grandchild',
    'aunt_uncle',
    'niece_nephew',
    'cousin',
    'other'
);

-- Person note types
CREATE TYPE person_note_type AS ENUM (
    'biographical',
    'health',
    'preference',
    'interest',
    'story',
    'personality',
    'achievement',
    'other'
);

-- Person note categories
CREATE TYPE person_note_category AS ENUM (
    'health',
    'personality',
    'hobbies',
    'family',
    'career',
    'preferences',
    'beliefs',
    'achievements',
    'stories',
    'other'
);

-- Event types (maps to specialized tables or generic events)
CREATE TYPE event_type_enum AS ENUM (
    'workout',        -- Has workouts table
    'meal',           -- Has meals table
    'sleep',          -- Sleep events (no specialized table, uses generic events)
    'commute',        -- Has commutes table
    'entertainment',  -- Has entertainment table
    'reflection',     -- Has reflections table
    'work',           -- Work sessions (generic events with work metadata)
    'generic'         -- No specialized table (social visits, communications, work sessions, misc events)
);

-- Event categories (semantic/contextual grouping)
CREATE TYPE event_category_enum AS ENUM (
    'health',      -- Health/fitness focused
    'social',      -- Social interactions
    'work',        -- Work/career related
    'travel',      -- Travel/transportation
    'personal',    -- Personal/solo activities
    'family',      -- Family activities
    'media',       -- Media consumption/entertainment
    'education',   -- Learning/development
    'maintenance', -- Life maintenance (chores, errands)
    'interaction', -- Specific interactions with people
    'entertainment', -- Entertainment/media consumption
    'other'        -- Uncategorized
);

-- Transport modes
CREATE TYPE transport_mode_enum AS ENUM (
    'driving',
    'public_transit',
    'walking',
    'cycling',
    'running',
    'flying',
    'rideshare',
    'taxi',
    'train',
    'bus',
    'subway',
    'ferry',
    'scooter',
    'other'
);

-- Meal title types (time of day)
CREATE TYPE meal_title_enum AS ENUM (
    'breakfast',
    'lunch',
    'dinner',
    'snack'
);

-- Meal type (preparation method)
CREATE TYPE meal_type_enum AS ENUM (
    'home_cooked',
    'restaurant',
    'takeout',
    'delivered',
    'meal_prep'
);

-- Exercise categories
CREATE TYPE exercise_category_enum AS ENUM (
    'strength',
    'cardio',
    'flexibility',
    'sports',
    'plyometric'
);

-- Workout subtypes (polymorphic workout behaviors)
CREATE TYPE workout_subtype_enum AS ENUM (
    'gym_strength',
    'gym_cardio',
    'run',
    'swim',
    'bike',
    'hike',
    'sport',
    'yoga',
    'pilates',
    'crossfit',
    'hiit',
    'circuit'
);

-- Health condition types
CREATE TYPE health_condition_type_enum AS ENUM (
    'illness',
    'injury'
);

-- Health condition severity levels
CREATE TYPE health_condition_severity_enum AS ENUM (
    'hospitalized',      -- Hospitalization required
    'clinic_visit',      -- Medical clinic/urgent care visit
    'doc_consultation',  -- Doctor consultation
    'home_remedy',       -- Home treatment
    'mild',              -- Mild symptoms
    'moderate',          -- Moderate symptoms
    'severe'             -- Severe symptoms (non-hospitalized)
);

-- ============================================================================
-- REFERENCE TABLES (Normalized - Catalog/Directory Data)
-- ============================================================================

-- People directory
CREATE TABLE people (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name VARCHAR(255) NOT NULL,
    aliases TEXT[],
    relationship person_relationship_enum,  -- Enum: friend, family, colleague, partner, etc.
    category person_category_enum,  -- Enum: close_friend, acquaintance, work, etc.
    kinship_to_owner VARCHAR(50), -- Direct relationship to owner (e.g. "Maternal Grandmother", "Honorary Uncle")
    
    -- Biographical information
    birthday VARCHAR(10),  -- ISO-8601 partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    death_date VARCHAR(10),  -- ISO-8601 partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    ethnicity VARCHAR(100),
    origin_location VARCHAR(255),  -- "from" field - where they're originally from
    known_since VARCHAR(10),  -- ISO-8601 partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    last_interaction_date VARCHAR(10),  -- ISO-8601 partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    
    -- Google People API integration (optional)
    google_people_id VARCHAR(255),  -- Google People resource ID (e.g., 'people/c1234567890')
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,  -- For data cleanup without losing historical records
    deleted_at TIMESTAMP,  -- When the person was marked as deleted
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_people_name ON people(canonical_name);
CREATE INDEX idx_people_name_trgm ON people USING gin(canonical_name gin_trgm_ops);  -- Fuzzy search
CREATE INDEX idx_people_aliases ON people USING gin(aliases);
CREATE INDEX idx_people_category ON people(category);
CREATE INDEX idx_people_kinship ON people(kinship_to_owner);
CREATE INDEX idx_people_birthday ON people(birthday);
CREATE INDEX idx_people_known_since ON people(known_since);
CREATE INDEX idx_people_last_interaction ON people(last_interaction_date DESC);
CREATE INDEX idx_people_google_people_id ON people(google_people_id) WHERE google_people_id IS NOT NULL;
CREATE INDEX idx_people_is_deleted ON people(is_deleted) WHERE is_deleted = TRUE;  -- For finding deleted records


-- ============================================================================
-- PERSON BIOGRAPHICAL TABLES
-- ============================================================================

-- Person relationships (family tree and connections)
CREATE TABLE person_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    related_person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    relationship_type family_relationship_type NOT NULL,  -- Enum: spouse, parent, sibling, child, etc.
    relationship_label VARCHAR(50), -- Nuanced label (e.g. "Twin", "Godfather")
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Prevent duplicate relationships
    UNIQUE(person_id, related_person_id, relationship_type),
    
    -- Prevent self-relationships
    CHECK (person_id != related_person_id)
);

CREATE INDEX idx_person_relationships_person ON person_relationships(person_id);
CREATE INDEX idx_person_relationships_related ON person_relationships(related_person_id);
CREATE INDEX idx_person_relationships_type ON person_relationships(relationship_type);


-- ============================================================================
-- TRIGGERS FOR AUTOMATIC RECIPROCAL RELATIONSHIPS
-- ============================================================================

-- Function to get the reciprocal relationship type
CREATE OR REPLACE FUNCTION get_reciprocal_relationship_type(rel_type family_relationship_type)
RETURNS family_relationship_type AS $$
BEGIN
    RETURN CASE rel_type
        -- Symmetric relationships (same both ways)
        WHEN 'spouse' THEN 'spouse'
        WHEN 'sibling' THEN 'sibling'
        WHEN 'cousin' THEN 'cousin'
        
        -- Asymmetric relationships (different each way)
        WHEN 'parent' THEN 'child'
        WHEN 'child' THEN 'parent'
        WHEN 'grandparent' THEN 'grandchild'
        WHEN 'grandchild' THEN 'grandparent'
        WHEN 'aunt_uncle' THEN 'niece_nephew'
        WHEN 'niece_nephew' THEN 'aunt_uncle'
        
        -- Other - return same (handle manually if needed)
        WHEN 'other' THEN 'other'
        
        ELSE 'other'
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- Trigger function to automatically create reciprocal relationship on INSERT
CREATE OR REPLACE FUNCTION create_reciprocal_relationship()
RETURNS TRIGGER AS $$
DECLARE
    reciprocal_type family_relationship_type;
    is_reciprocal BOOLEAN;
BEGIN
    -- Check if this insert is itself a reciprocal (to prevent infinite loop)
    -- Use COALESCE to handle NULL notes properly
    is_reciprocal := (COALESCE(NEW.notes, '') = 'Auto-created reciprocal relationship');
    
    -- Only create reciprocal if this isn't already a reciprocal
    IF NOT is_reciprocal THEN
        -- Get the reciprocal relationship type
        reciprocal_type := get_reciprocal_relationship_type(NEW.relationship_type);
        
        -- Check if reciprocal relationship already exists
        IF NOT EXISTS (
            SELECT 1 FROM person_relationships
            WHERE person_id = NEW.related_person_id
            AND related_person_id = NEW.person_id
            AND relationship_type = reciprocal_type
        ) THEN
            -- Create the reciprocal relationship
            INSERT INTO person_relationships (
                person_id,
                related_person_id,
                relationship_type,
                notes,
                created_at,
                updated_at
            ) VALUES (
                NEW.related_person_id,
                NEW.person_id,
                reciprocal_type,
                'Auto-created reciprocal relationship',
                NOW(),
                NOW()
            );
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Trigger function to automatically update reciprocal relationship on UPDATE
CREATE OR REPLACE FUNCTION update_reciprocal_relationship()
RETURNS TRIGGER AS $$
DECLARE
    old_reciprocal_type family_relationship_type;
    new_reciprocal_type family_relationship_type;
BEGIN
    -- Get old and new reciprocal types
    old_reciprocal_type := get_reciprocal_relationship_type(OLD.relationship_type);
    new_reciprocal_type := get_reciprocal_relationship_type(NEW.relationship_type);
    
    -- Update the reciprocal relationship if relationship type changed
    IF OLD.relationship_type != NEW.relationship_type THEN
        UPDATE person_relationships
        SET relationship_type = new_reciprocal_type,
            updated_at = NOW()
        WHERE person_id = OLD.related_person_id
        AND related_person_id = OLD.person_id
        AND relationship_type = old_reciprocal_type;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Trigger function to automatically delete reciprocal relationship on DELETE
CREATE OR REPLACE FUNCTION delete_reciprocal_relationship()
RETURNS TRIGGER AS $$
DECLARE
    reciprocal_type family_relationship_type;
    is_reciprocal BOOLEAN;
BEGIN
    -- Prevent infinite recursion by checking trigger depth
    -- If we're already in a nested trigger call, don't proceed
    IF pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    
    -- Check if the deleted relationship was auto-created (to prevent infinite loop)
    -- Use COALESCE to handle NULL notes properly
    is_reciprocal := (COALESCE(OLD.notes, '') = 'Auto-created reciprocal relationship');
    
    -- Only delete reciprocal if this wasn't itself a reciprocal
    IF NOT is_reciprocal THEN
        -- Get the reciprocal relationship type
        reciprocal_type := get_reciprocal_relationship_type(OLD.relationship_type);
        
        -- Delete the reciprocal relationship if it exists
        DELETE FROM person_relationships
        WHERE person_id = OLD.related_person_id
        AND related_person_id = OLD.person_id
        AND relationship_type = reciprocal_type;
    END IF;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;


-- Attach triggers to person_relationships table
CREATE TRIGGER trigger_create_reciprocal_relationship
    AFTER INSERT ON person_relationships
    FOR EACH ROW
    EXECUTE FUNCTION create_reciprocal_relationship();

CREATE TRIGGER trigger_update_reciprocal_relationship
    AFTER UPDATE ON person_relationships
    FOR EACH ROW
    EXECUTE FUNCTION update_reciprocal_relationship();

CREATE TRIGGER trigger_delete_reciprocal_relationship
    BEFORE DELETE ON person_relationships
    FOR EACH ROW
    EXECUTE FUNCTION delete_reciprocal_relationship();


-- Person notes (structured biographical notes)
CREATE TABLE person_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    
    note_date VARCHAR(10),  -- ISO-8601 partial date string: YYYY, YYYY-MM, or YYYY-MM-DD
    note_type person_note_type,  -- Enum: biographical, health, preference, interest, story, etc.
    category person_note_category,  -- Enum: health, personality, hobbies, family, career, etc.
    text TEXT NOT NULL,
    source VARCHAR(100),  -- conversation, observation, social_media, told_by_others, etc.
    context TEXT,  -- Additional context about how info was obtained
    tags TEXT[],  -- Searchable keywords
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_person_notes_person ON person_notes(person_id);
CREATE INDEX idx_person_notes_date ON person_notes(note_date DESC);
CREATE INDEX idx_person_notes_type ON person_notes(note_type);
CREATE INDEX idx_person_notes_category ON person_notes(category);
CREATE INDEX idx_person_notes_tags ON person_notes USING gin(tags);
CREATE INDEX idx_person_notes_text_search ON person_notes USING gin(to_tsvector('english', text));


-- ============================================================================
-- LOCATIONS (Foundational reference table)
-- ============================================================================

-- Locations catalog
CREATE TABLE locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name VARCHAR(255) NOT NULL,
    place_id VARCHAR(255) UNIQUE,  -- Google Places ID (fetch details via API)
    location_type VARCHAR(50),  -- gym, park, home, restaurant, office, etc.
    
    notes TEXT,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_locations_name ON locations(canonical_name);
CREATE INDEX idx_locations_name_trgm ON locations USING gin(canonical_name gin_trgm_ops);
CREATE INDEX idx_locations_place_id ON locations(place_id) WHERE place_id IS NOT NULL;
CREATE INDEX idx_locations_type ON locations(location_type);
CREATE INDEX idx_locations_is_deleted ON locations(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- TEMPORAL LOCATIONS (Person-agnostic base table for time-place periods)
-- Architecture: Multiple people can share the same temporal_location entry
-- Example: Two people who attended Stanford 2018-2022 reference one entry
-- Design #31: Strict enforcement - location_id required, place_text removed
-- ============================================================================

CREATE TABLE temporal_locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Location reference (required - no free-form fallback)
    location_id UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    
    -- Date (partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD)
    start_date VARCHAR(10),  -- Start date (NULL if unknown)
    end_date VARCHAR(10),  -- End date (NULL if ongoing/unknown)
    is_current BOOLEAN DEFAULT FALSE,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_temporal_locations_location ON temporal_locations(location_id);
CREATE INDEX idx_temporal_locations_dates ON temporal_locations(start_date, end_date);
CREATE INDEX idx_temporal_locations_current ON temporal_locations(is_current) WHERE is_current = TRUE;


-- ============================================================================
-- PERSON BIOGRAPHICAL TABLES (Specialized tables linking people to temporal locations)
-- ============================================================================

-- Person residences (where someone lived)
CREATE TABLE person_residences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    temporal_location_id UUID NOT NULL REFERENCES temporal_locations(id) ON DELETE CASCADE,
    
    notes TEXT,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_person_residences_person ON person_residences(person_id);
CREATE INDEX idx_person_residences_temporal_location ON person_residences(temporal_location_id);
CREATE INDEX idx_person_residences_composite ON person_residences(person_id, temporal_location_id);
CREATE INDEX idx_person_residences_is_deleted ON person_residences(is_deleted) WHERE is_deleted = TRUE;


-- Person work history (employment timeline)
CREATE TABLE person_work (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    temporal_location_id UUID NOT NULL REFERENCES temporal_locations(id) ON DELETE CASCADE,
    
    company VARCHAR(255) NOT NULL,
    role VARCHAR(255) NOT NULL,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_person_work_person ON person_work(person_id);
CREATE INDEX idx_person_work_temporal_location ON person_work(temporal_location_id);
CREATE INDEX idx_person_work_composite ON person_work(person_id, temporal_location_id);
CREATE INDEX idx_person_work_company ON person_work(company);


-- Person education history
CREATE TABLE person_education (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    temporal_location_id UUID NOT NULL REFERENCES temporal_locations(id) ON DELETE CASCADE,
    
    institution VARCHAR(255) NOT NULL,
    degree VARCHAR(100) NOT NULL,
    field VARCHAR(255),  -- Field of study
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_person_education_person ON person_education(person_id);
CREATE INDEX idx_person_education_temporal_location ON person_education(temporal_location_id);
CREATE INDEX idx_person_education_composite ON person_education(person_id, temporal_location_id);
CREATE INDEX idx_person_education_institution ON person_education(institution);


-- ============================================================================
-- EXERCISES (Reference data for workouts)
-- ============================================================================

-- Exercise catalog
CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name VARCHAR(255) NOT NULL UNIQUE,
    category exercise_category_enum NOT NULL,
    
    -- Muscle targeting (for analytics)
    primary_muscle_group VARCHAR(50),
    secondary_muscle_groups TEXT[] DEFAULT '{}',
    
    equipment TEXT[],
    variants TEXT[],
    
    notes TEXT,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_exercises_name ON exercises(canonical_name);
CREATE INDEX idx_exercises_name_trgm ON exercises USING gin(canonical_name gin_trgm_ops);
CREATE INDEX idx_exercises_category ON exercises(category);
CREATE INDEX idx_exercises_primary_muscle ON exercises(primary_muscle_group);
CREATE INDEX idx_exercises_is_deleted ON exercises(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- EVENTS (Primary Aggregate Root)
-- Events own WHO, WHERE, WHEN - the common attributes of all activities
-- ============================================================================

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Event classification
    event_type event_type_enum NOT NULL,  -- Type determines which specialized table (if any)
    title VARCHAR(500),
    description TEXT,
    
    -- Hierarchical structure (NEW - for nested events)
    parent_event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    event_scope VARCHAR(50) DEFAULT 'single_day',  -- 'single_day', 'multi_day', 'trip', 'vacation', 'project'
    hierarchy_level INTEGER DEFAULT 0,  -- 0=root, 1=child, 2=grandchild, etc.
    hierarchy_path TEXT,  -- Materialized path: 'parent_id/child_id/grandchild_id'
    
    -- Information provenance (NEW - track how you learned about events)
    information_source VARCHAR(50) DEFAULT 'direct',  -- 'direct', 'told_by_person', 'read', 'social_media', 'inferred'
    source_event_id UUID REFERENCES events(id) ON DELETE SET NULL,  -- Event where you learned about this (e.g., conversation)
    source_person_id UUID REFERENCES people(id) ON DELETE SET NULL,  -- Person who told you about this event
    source_confidence VARCHAR(20) DEFAULT 'certain',  -- 'certain', 'probable', 'uncertain' - reliability of second-hand info
    
    -- Recurrence (for repeating events)
    recurrence VARCHAR(50) DEFAULT 'none',  -- 'none', 'daily', 'weekly', 'monthly', 'yearly'
    recurrence_end_date DATE,
    
    -- Temporal data (CRITICAL for time-series queries)
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_minutes INTEGER GENERATED ALWAYS AS 
        (CAST(EXTRACT(EPOCH FROM (end_time - start_time)) / 60 AS INTEGER)) STORED,
    
    -- Location (WHERE)
    location_id UUID REFERENCES locations(id),
    -- location_text removed: use locations catalog via location_id
    
    -- External system references
    external_event_id VARCHAR(255),  -- Reference to event ID in external/legacy systems (e.g., "20007876401")
    external_event_source VARCHAR(100),  -- Source system for external_event_id (e.g., 'garmin', 'apple_health', 'fitbit', 'strava')
    
    -- Categorization
    category event_category_enum,  -- Semantic/contextual grouping (health, social, work, etc.)
    significance VARCHAR(50) DEFAULT 'routine',  -- routine, notable, major, milestone, major_milestone
    
    -- Metadata
    notes TEXT,
    tags TEXT[],
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT check_no_self_reference CHECK (id != parent_event_id)
    -- Note: check_child_within_parent_time constraint removed - can't use subqueries in CHECK constraints
    -- This validation should be done at application level or via triggers
);

-- CRITICAL INDEXES for LLM queries
CREATE INDEX idx_events_date ON events(DATE(start_time) DESC);
CREATE INDEX idx_events_start_time ON events(start_time DESC);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_location ON events(location_id);
CREATE INDEX idx_events_date_type ON events(DATE(start_time), event_type);
CREATE INDEX idx_events_category ON events(category);
CREATE INDEX idx_events_tags ON events USING gin(tags);

-- NEW: Hierarchical event indexes
CREATE INDEX idx_events_parent ON events(parent_event_id) WHERE parent_event_id IS NOT NULL;
CREATE INDEX idx_events_scope ON events(event_scope);
CREATE INDEX idx_events_hierarchy_level ON events(hierarchy_level);
CREATE INDEX idx_events_hierarchy_path ON events(hierarchy_path);
CREATE INDEX idx_events_recurrence ON events(recurrence) WHERE recurrence != 'none';

-- NEW: Information provenance indexes
CREATE INDEX idx_events_information_source ON events(information_source);
CREATE INDEX idx_events_source_event ON events(source_event_id) WHERE source_event_id IS NOT NULL;
CREATE INDEX idx_events_source_person ON events(source_person_id) WHERE source_person_id IS NOT NULL;
CREATE INDEX idx_events_source_confidence ON events(source_confidence) WHERE source_confidence != 'certain';
CREATE INDEX idx_events_external_id ON events(external_event_id) WHERE external_event_id IS NOT NULL;
CREATE INDEX idx_events_external_source ON events(external_event_source) WHERE external_event_source IS NOT NULL;
CREATE INDEX idx_events_is_deleted ON events(is_deleted) WHERE is_deleted = TRUE;


-- Event participants (WHO) - shared across all event types
CREATE TABLE event_participants (
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    role VARCHAR(50),  -- trainer, partner, friend, coach, etc.
    interaction_mode VARCHAR(50) CHECK (interaction_mode IN ('in_person', 'virtual_video', 'virtual_audio', 'text_async', 'other')),
    PRIMARY KEY (event_id, person_id)
);

CREATE INDEX idx_event_participants_person ON event_participants(person_id);
CREATE INDEX idx_event_participants_event ON event_participants(event_id);


-- ============================================================================
-- EVENT SPECIALIZATION TABLES
-- These tables extend events with type-specific data
-- Organized from simplest (thin wrappers) to most complex (with child tables)
-- ============================================================================

-- ============================================================================
-- MEALS (Event Specialization - WHAT meal-specific data)
-- ============================================================================

CREATE TABLE meals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    
    -- Meal-specific fields
    meal_title meal_title_enum NOT NULL,  -- breakfast, lunch, dinner, snack
    meal_type meal_type_enum,  -- home_cooked, restaurant, takeout, delivered, meal_prep
    portion_size VARCHAR(20),  -- light, regular, heavy
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_meals_event ON meals(event_id);
CREATE INDEX idx_meals_title ON meals(meal_title);
CREATE INDEX idx_meals_type ON meals(meal_type) WHERE meal_type IS NOT NULL;
CREATE INDEX idx_meals_is_deleted ON meals(is_deleted) WHERE is_deleted = TRUE;


-- Meal items (food items in a meal)
CREATE TABLE meal_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meal_id UUID NOT NULL REFERENCES meals(id) ON DELETE CASCADE,

    -- Food item details
    item_name VARCHAR(255) NOT NULL,
    quantity VARCHAR(100),  -- e.g., "200g", "1 cup", "2 pieces"

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);CREATE INDEX idx_meal_items_meal ON meal_items(meal_id);
CREATE INDEX idx_meal_items_name ON meal_items(item_name);


-- ============================================================================
-- COMMUTES/TRAVEL (Event Specialization - WHAT travel-specific data)
-- ============================================================================

CREATE TABLE commutes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    
    -- Travel route
    from_location_id UUID REFERENCES locations(id),
    to_location_id UUID REFERENCES locations(id),
    
    -- Transport method
    transport_mode transport_mode_enum NOT NULL,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_commutes_event ON commutes(event_id);
CREATE INDEX idx_commutes_from_location ON commutes(from_location_id);
CREATE INDEX idx_commutes_to_location ON commutes(to_location_id);
CREATE INDEX idx_commutes_transport_mode ON commutes(transport_mode);
CREATE INDEX idx_commutes_is_deleted ON commutes(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- ENTERTAINMENT (Event Specialization - WHAT entertainment-specific data)
-- Replaces old media table with richer functionality
-- ============================================================================

CREATE TABLE entertainment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    
    -- Classification
    entertainment_type VARCHAR(50) NOT NULL,  -- movie, tv_show, video, podcast, live_performance, gaming, reading, streaming, concert, theater, sports_event, other
    title VARCHAR(500) NOT NULL,  -- Title of the content
    
    -- Creators/Attribution
    creator VARCHAR(255),  -- Author, director, creator
    genre VARCHAR(100),  -- Genre classification
    
    -- TV Show specifics
    show_name VARCHAR(255),  -- Show name (for TV shows)
    season_number INTEGER CHECK (season_number >= 1),
    episode_number INTEGER CHECK (episode_number >= 1),
    episode_title VARCHAR(255),
    
    -- YouTube/Podcast specifics
    channel_name VARCHAR(255),  -- Channel or podcast name
    video_url TEXT,  -- URL to content
    
    -- Movie specifics
    director VARCHAR(255),
    release_year INTEGER CHECK (release_year >= 1800 AND release_year <= 2100),
    
    -- Live Performance specifics
    performance_type VARCHAR(50),  -- concert, theater, comedy, dance, opera, sports, other
    venue VARCHAR(255),  -- Venue name
    performer_artist VARCHAR(255),  -- Performer/artist name
    
    -- Gaming specifics
    game_platform VARCHAR(100),  -- PC, PS5, Xbox, Switch, etc.
    game_genre VARCHAR(100),  -- RPG, FPS, strategy, etc.
    
    -- Platform and format
    platform VARCHAR(100),  -- Netflix, Spotify, HBO, YouTube, etc.
    format VARCHAR(50),  -- digital, physical, streaming, etc.
    
    -- User feedback
    personal_rating INTEGER CHECK (personal_rating >= 1 AND personal_rating <= 10),
    completion_status VARCHAR(20) DEFAULT 'completed',  -- completed, in_progress, abandoned, planned
    rewatch BOOLEAN DEFAULT FALSE,
    
    -- Social context
    watched_with_others BOOLEAN DEFAULT FALSE,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_entertainment_event ON entertainment(event_id);
CREATE INDEX idx_entertainment_type ON entertainment(entertainment_type);
CREATE INDEX idx_entertainment_rating ON entertainment(personal_rating) WHERE personal_rating IS NOT NULL;
CREATE INDEX idx_entertainment_completion ON entertainment(completion_status);
CREATE INDEX idx_entertainment_is_deleted ON entertainment(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- HEALTH TRACKING (Three separate tables for modularity)
-- - health_conditions: Illnesses and injuries (event-based)
-- - health_medicines: Medications taken (optional event link)
-- - health_supplements: Dietary supplements (daily wellness logging)
-- ============================================================================

-- Health conditions (illnesses and injuries) - event-based
CREATE TABLE health_conditions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,  -- Direct person reference for easy querying

    -- Condition type and severity
    condition_type health_condition_type_enum NOT NULL,  -- 'illness' or 'injury'
    condition_name VARCHAR(255) NOT NULL,                 -- 'flu', 'headache', 'broken_arm', etc.
    severity health_condition_severity_enum,              -- 'hospitalized', 'clinic_visit', 'doc_consultation', 'home_remedy', 'mild', 'moderate', 'severe'
    severity_score INTEGER CHECK (severity_score >= 1 AND severity_score <= 10),  -- 1-10 pain/severity scale

    -- Injury-specific fields
    is_sport_related BOOLEAN DEFAULT FALSE,
    sport_type VARCHAR(100),  -- 'soccer', 'running', 'cycling', etc. if injury_sport_related

    -- Duration tracking (for illnesses that span multiple days)
    start_date DATE NOT NULL,
    end_date DATE,  -- NULL if ongoing

    -- Additional context
    notes TEXT,

    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_health_conditions_event ON health_conditions(event_id);
CREATE INDEX idx_health_conditions_person ON health_conditions(person_id);
CREATE INDEX idx_health_conditions_type ON health_conditions(condition_type);
CREATE INDEX idx_health_conditions_start_date ON health_conditions(start_date);
CREATE INDEX idx_health_conditions_sport_related ON health_conditions(is_sport_related) WHERE is_sport_related = TRUE;
CREATE INDEX idx_health_conditions_is_deleted ON health_conditions(is_deleted) WHERE is_deleted = TRUE;


-- Health medicines (medications taken)
CREATE TABLE health_medicines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,  -- Optional event link
    condition_id UUID REFERENCES health_conditions(id) ON DELETE SET NULL,  -- Optional link to condition
    
    -- Medicine information
    medicine_name VARCHAR(255) NOT NULL,  -- 'ibuprofen', 'aspirin', 'amoxicillin', etc.
    dosage VARCHAR(100),                  -- '500mg', '1 tablet', '10ml'
    dosage_unit VARCHAR(50),              -- 'mg', 'tablet', 'capsule', 'ml', etc.
    frequency VARCHAR(100),               -- 'once daily', 'every 6 hours', 'as needed'
    
    -- Logging information
    log_date DATE NOT NULL,
    log_time TIME,
    
    notes TEXT,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_health_medicines_event ON health_medicines(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX idx_health_medicines_condition ON health_medicines(condition_id) WHERE condition_id IS NOT NULL;
CREATE INDEX idx_health_medicines_log_date ON health_medicines(log_date);
CREATE INDEX idx_health_medicines_medicine_name ON health_medicines(medicine_name);
CREATE INDEX idx_health_medicines_is_deleted ON health_medicines(is_deleted) WHERE is_deleted = TRUE;


-- Health supplements (dietary supplements - routine wellness)
CREATE TABLE health_supplements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,  -- Optional event link
    
    -- Supplement information
    supplement_name VARCHAR(255) NOT NULL,  -- 'multivitamin', 'vitamin_d', 'protein', 'creatine', 'zinc', 'magnesium', etc.
    amount VARCHAR(100),                    -- '1000mg', '2 scoops', '2 capsules'
    amount_unit VARCHAR(50),                -- 'mg', 'iu', 'grams', 'scoops', 'capsules', 'tablets'
    frequency VARCHAR(100),                 -- 'daily', 'every other day', 'twice daily'
    
    -- Logging information
    log_date DATE NOT NULL,
    log_time TIME,
    
    notes TEXT,
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_health_supplements_event ON health_supplements(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX idx_health_supplements_log_date ON health_supplements(log_date);
CREATE INDEX idx_health_supplements_supplement_name ON health_supplements(supplement_name);
CREATE INDEX idx_health_supplements_is_deleted ON health_supplements(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- HEALTH CONDITION LOGS (Progression tracking for health conditions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS health_condition_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    condition_id UUID NOT NULL REFERENCES health_conditions(id) ON DELETE CASCADE,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,  -- Inherited from parent condition for easy querying
    log_date DATE NOT NULL,
    severity health_condition_severity_enum,
    severity_score INTEGER CHECK (severity_score >= 1 AND severity_score <= 10),
    notes TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(condition_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_hcl_condition ON health_condition_logs(condition_id);
CREATE INDEX IF NOT EXISTS idx_hcl_person ON health_condition_logs(person_id);
CREATE INDEX IF NOT EXISTS idx_hcl_log_date ON health_condition_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_hcl_is_deleted ON health_condition_logs(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- REFLECTIONS (Event Specialization - Personal reflections and introspection)
-- ============================================================================

CREATE TABLE reflections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    
    -- Reflection-specific fields
    reflection_type VARCHAR(50),  -- 'daily', 'weekly', 'monthly', 'gratitude', 'learning', 'goal_review', 'decision', 'other'
    mood VARCHAR(50),  -- 'positive', 'negative', 'neutral', 'mixed', 'anxious', 'excited', 'sad', 'grateful', etc.
    mood_score INTEGER CHECK (mood_score BETWEEN 1 AND 10),  -- 1-10 emotional state
    
    -- Structured reflection prompts (optional)
    prompt_question TEXT,  -- What question/prompt triggered this reflection?
    key_insights TEXT[],   -- Array of key insights or takeaways
    action_items TEXT[],   -- Array of action items from the reflection
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_reflections_event ON reflections(event_id);
CREATE INDEX idx_reflections_type ON reflections(reflection_type);
CREATE INDEX idx_reflections_mood ON reflections(mood);
CREATE INDEX idx_reflections_mood_score ON reflections(mood_score);
CREATE INDEX idx_reflections_is_deleted ON reflections(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================================
-- WORKOUTS (Event Specialization - WHAT workout-specific data)
-- More complex than other event types due to child tables for exercises/sets
-- ============================================================================

CREATE TABLE workouts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    
    -- Workout-specific fields
    workout_name VARCHAR(255),
    category VARCHAR(50) NOT NULL,  -- STRENGTH, CARDIO, MIXED, SPORTS, etc.
    
    -- Workout subtype for polymorphic behavior
    workout_subtype workout_subtype_enum,  -- gym_strength, gym_cardio, run, swim, bike, hike, sport, yoga, etc.
    
    -- Sport-specific fields (SPORT subtype)
    sport_type VARCHAR(100),  -- 'basketball', 'tennis', 'soccer', 'volleyball'
    
    -- Soft delete support
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- INDEXES for workout queries
CREATE INDEX idx_workouts_event ON workouts(event_id);
CREATE INDEX idx_workouts_category ON workouts(category);
CREATE INDEX idx_workouts_subtype ON workouts(workout_subtype);
CREATE INDEX idx_workouts_sport_type ON workouts(sport_type) WHERE sport_type IS NOT NULL;
CREATE INDEX idx_workouts_is_deleted ON workouts(is_deleted) WHERE is_deleted = TRUE;


-- Workout exercises (one-to-many)
CREATE TABLE workout_exercises (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workout_id UUID NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_id UUID NOT NULL REFERENCES exercises(id),
    
    sequence_order INTEGER NOT NULL,
    notes TEXT,
    rest_between_exercises_s INTEGER,
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(workout_id, sequence_order)
);

CREATE INDEX idx_workout_exercises_workout ON workout_exercises(workout_id);
CREATE INDEX idx_workout_exercises_exercise ON workout_exercises(exercise_id);
CREATE INDEX idx_workout_exercises_composite ON workout_exercises(exercise_id, workout_id);


-- Exercise sets (one-to-many from workout_exercises)
CREATE TABLE exercise_sets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workout_exercise_id UUID NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
    
    set_number INTEGER NOT NULL,
    set_type VARCHAR(20) DEFAULT 'WORKING',  -- WORKING, WARMUP, DROP, FAILURE
    
    -- Set data (different exercises use different fields)
    weight_kg DECIMAL(10, 2),
    reps INTEGER,  -- NULL for interval-based sets
    duration_s INTEGER,
    distance_km DECIMAL(10, 3),
    rest_time_s INTEGER,
    pace VARCHAR(50),
    
    -- Interval training fields (for Tabata, HIIT, etc.)
    interval_description TEXT,  -- Free-text description (e.g., "20s work, 10s rest")
    work_duration_s INTEGER,    -- Work duration in seconds
    rest_duration_s INTEGER,    -- Rest duration in seconds
    
    -- Computed field for volume
    volume_kg DECIMAL(10, 2) GENERATED ALWAYS AS 
        (COALESCE(weight_kg, 0) * COALESCE(reps, 0)) STORED,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(workout_exercise_id, set_number),
    CONSTRAINT check_reps_or_interval CHECK (reps IS NOT NULL OR interval_description IS NOT NULL)
);

CREATE INDEX idx_sets_workout_exercise ON exercise_sets(workout_exercise_id);
CREATE INDEX idx_sets_weight ON exercise_sets(weight_kg) WHERE weight_kg IS NOT NULL;
CREATE INDEX idx_sets_volume ON exercise_sets(volume_kg) WHERE volume_kg > 0;


-- ============================================================================
-- EVENT VALIDATION TRIGGERS
-- Ensure events with specialized types have corresponding specialized table entries
-- ============================================================================

-- Function to validate event has required specialized table entry
CREATE OR REPLACE FUNCTION validate_event_specialized_table()
RETURNS TRIGGER AS $$
DECLARE
    v_has_specialized_entry BOOLEAN;
BEGIN
    -- Only validate for UPDATE or after specialized tables are created
    -- For INSERT, the specialized table entry is created AFTER the event
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    
    -- Check if event_type requires a specialized table
    CASE NEW.event_type
        WHEN 'workout' THEN
            SELECT EXISTS(SELECT 1 FROM workouts WHERE event_id = NEW.id) INTO v_has_specialized_entry;
            IF NOT v_has_specialized_entry THEN
                RAISE EXCEPTION 'Event type "workout" requires an entry in workouts table';
            END IF;
            
        WHEN 'meal' THEN
            SELECT EXISTS(SELECT 1 FROM meals WHERE event_id = NEW.id) INTO v_has_specialized_entry;
            IF NOT v_has_specialized_entry THEN
                RAISE EXCEPTION 'Event type "meal" requires an entry in meals table';
            END IF;
            
        WHEN 'commute' THEN
            SELECT EXISTS(SELECT 1 FROM commutes WHERE event_id = NEW.id) INTO v_has_specialized_entry;
            IF NOT v_has_specialized_entry THEN
                RAISE EXCEPTION 'Event type "commute" requires an entry in commutes table';
            END IF;
            
        WHEN 'entertainment' THEN
            SELECT EXISTS(SELECT 1 FROM entertainment WHERE event_id = NEW.id) INTO v_has_specialized_entry;
            IF NOT v_has_specialized_entry THEN
                RAISE EXCEPTION 'Event type "entertainment" requires an entry in entertainment table';
            END IF;
            
        WHEN 'generic' THEN
            -- Generic events don't require a specialized table
            NULL;
            
        ELSE
            RAISE EXCEPTION 'Unknown event_type: %', NEW.event_type;
    END CASE;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to validate specialized table entries (runs AFTER UPDATE)
-- Note: We use AFTER UPDATE instead of AFTER INSERT because the specialized
-- table entry is typically created after the event is created
CREATE TRIGGER trigger_validate_event_specialized_table
    AFTER UPDATE ON events
    FOR EACH ROW
    WHEN (OLD.event_type IS DISTINCT FROM NEW.event_type)
    EXECUTE FUNCTION validate_event_specialized_table();


-- ============================================================================
-- RAW JOURNAL ENTRIES (Preserve original user input)
-- ============================================================================



-- ============================================================================
-- JOURNAL DAYS (Top-level aggregator for a complete day)
-- ============================================================================

CREATE TABLE journal_days (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    journal_date DATE NOT NULL UNIQUE,
    
    -- Summary/metadata
    day_title VARCHAR(255),
    day_rating INTEGER CHECK (day_rating BETWEEN 1 AND 10),
    highlights TEXT[],
    
    -- Quick stats (denormalized for fast queries)
    workout_count INTEGER DEFAULT 0,
    meal_count INTEGER DEFAULT 0,
    commute_count INTEGER DEFAULT 0,
    entertainment_count INTEGER DEFAULT 0,
    event_count INTEGER DEFAULT 0,
    reflection_count INTEGER DEFAULT 0,
    work_minutes INTEGER DEFAULT 0,
    sleep_hours DECIMAL(4, 2),
    total_commute_minutes INTEGER DEFAULT 0,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_journal_days_date ON journal_days(journal_date DESC);
CREATE INDEX idx_journal_days_rating ON journal_days(day_rating);


-- ============================================================================
-- TRIGGERS (Auto-update computed fields)
-- ============================================================================

-- Update journal day stats
CREATE OR REPLACE FUNCTION update_journal_day_stats()
RETURNS TRIGGER AS $$
DECLARE
    v_date DATE;
BEGIN
    -- Determine which date to update (use DATE(start_time) instead of event_date)
    v_date = COALESCE(DATE(NEW.start_time), DATE(OLD.start_time));
    
    -- Upsert journal day and update stats
    INSERT INTO journal_days (journal_date)
    VALUES (v_date)
    ON CONFLICT (journal_date) DO NOTHING;
    
    UPDATE journal_days jd
    SET 
        workout_count = (
            SELECT COUNT(*) 
            FROM events e 
            JOIN workouts w ON e.id = w.event_id 
            WHERE DATE(e.start_time) = v_date
        ),
        meal_count = (
            SELECT COUNT(*) 
            FROM events e 
            JOIN meals m ON e.id = m.event_id 
            WHERE DATE(e.start_time) = v_date
        ),
        commute_count = (
            SELECT COUNT(*) 
            FROM events e 
            JOIN commutes c ON e.id = c.event_id 
            WHERE DATE(e.start_time) = v_date
        ),
        entertainment_count = (
            SELECT COUNT(*) 
            FROM events e 
            JOIN entertainment ent ON e.id = ent.event_id 
            WHERE DATE(e.start_time) = v_date
        ),
        total_commute_minutes = (
            SELECT COALESCE(SUM(e.duration_minutes), 0)
            FROM events e 
            JOIN commutes c ON e.id = c.event_id 
            WHERE DATE(e.start_time) = v_date
        ),
        event_count = (SELECT COUNT(*) FROM events WHERE DATE(start_time) = v_date),
        reflection_count = (
            SELECT COUNT(*) 
            FROM events e 
            WHERE DATE(e.start_time) = v_date
              AND e.event_type = 'generic'
              AND (e.tags @> ARRAY['reflection'] OR e.title ILIKE '%reflection%')
        ),
        work_minutes = (
            SELECT COALESCE(SUM(e.duration_minutes), 0)
            FROM events e
            WHERE DATE(e.start_time) = v_date
              AND e.category = 'work'
        ),
        sleep_hours = (
            SELECT e.duration_minutes / 60.0
            FROM events e 
            WHERE DATE(e.start_time) = v_date
              AND e.event_type = 'generic'
              AND (e.tags @> ARRAY['sleep'] OR e.title ILIKE '%sleep%')
            LIMIT 1
        ),
        updated_at = NOW()
    WHERE jd.journal_date = v_date;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_journal_event_stats
AFTER INSERT OR UPDATE OR DELETE ON events
FOR EACH ROW
EXECUTE FUNCTION update_journal_day_stats();


-- ============================================================================
-- CONVENIENCE VIEWS (Simplify common queries)
-- ============================================================================

-- Workout events with all common fields
CREATE VIEW workout_events AS
SELECT 
    e.id AS event_id,
    e.start_time,
    e.end_time,
    e.duration_minutes,
    e.title AS event_title,
    e.notes AS event_notes,
    e.tags,
    e.location_id,
    l.canonical_name AS location_name,
    l.location_type,
    w.id AS workout_id,
    w.workout_name,
    w.category AS workout_category
FROM events e
JOIN workouts w ON e.id = w.event_id
LEFT JOIN locations l ON e.location_id = l.id;


-- Meal events with all common fields
CREATE VIEW meal_events AS
SELECT 
    e.id AS event_id,
    e.start_time AS meal_time,
    e.duration_minutes,
    e.title AS event_title,
    e.notes AS event_notes,
    e.tags,
    e.location_id,
    l.canonical_name AS location_name,
    l.location_type,
    m.id AS meal_id,
    m.meal_title,
    m.meal_type,
    m.portion_size
FROM events e
JOIN meals m ON e.id = m.event_id
LEFT JOIN locations l ON e.location_id = l.id;


-- Commute events with all common fields
CREATE VIEW commute_events AS
SELECT 
    e.id AS event_id,
    e.start_time,
    e.end_time,
    e.duration_minutes,
    e.title AS event_title,
    e.notes AS event_notes,
    e.tags,
    c.id AS commute_id,
    c.from_location_id,
    fl.canonical_name AS from_location_name,
    c.to_location_id,
    tl.canonical_name AS to_location_name,
    c.transport_mode
FROM events e
JOIN commutes c ON e.id = c.event_id
LEFT JOIN locations fl ON c.from_location_id = fl.id
LEFT JOIN locations tl ON c.to_location_id = tl.id;


-- Entertainment events with all common fields
CREATE VIEW entertainment_events AS
SELECT 
    e.id AS event_id,
    e.start_time,
    e.end_time,
    e.duration_minutes,
    e.title AS event_title,
    e.notes AS event_notes,
    e.tags,
    e.location_id,
    l.canonical_name AS location_name,
    ent.id AS entertainment_id,
    ent.entertainment_type,
    ent.title AS entertainment_title,
    ent.creator,
    ent.genre,
    ent.show_name,
    ent.season_number,
    ent.episode_number,
    ent.episode_title,
    ent.channel_name,
    ent.video_url,
    ent.director,
    ent.release_year,
    ent.performance_type,
    ent.venue,
    ent.performer_artist,
    ent.game_platform,
    ent.game_genre,
    ent.platform,
    ent.format,
    ent.personal_rating,
    ent.completion_status,
    ent.rewatch,
    ent.watched_with_others
FROM events e
JOIN entertainment ent ON e.id = ent.event_id
LEFT JOIN locations l ON e.location_id = l.id;


-- Sleep events (no specialized table needed - just use events with event_type='sleep')
CREATE VIEW sleep_events AS
SELECT 
    e.id AS event_id,
    DATE(e.start_time) AS sleep_date,
    e.start_time AS sleep_time,
    e.end_time AS wake_time,
    e.duration_minutes,
    ROUND((e.duration_minutes / 60.0)::NUMERIC, 2) AS duration_hours,
    e.notes,
    e.tags,
    e.location_id,
    l.canonical_name AS location_name
FROM events e
LEFT JOIN locations l ON e.location_id = l.id
WHERE e.event_type = 'sleep';


-- All events with participants
CREATE VIEW events_with_participants AS
SELECT 
    e.id AS event_id,
    e.event_type,
    e.start_time,
    e.end_time,
    e.title,
    e.location_id,
    l.canonical_name AS location_name,
    ARRAY_AGG(DISTINCT p.canonical_name) FILTER (WHERE p.canonical_name IS NOT NULL) AS participants,
    ARRAY_AGG(DISTINCT ep.role) FILTER (WHERE ep.role IS NOT NULL) AS participant_roles
FROM events e
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN event_participants ep ON e.id = ep.event_id
LEFT JOIN people p ON ep.person_id = p.id
GROUP BY e.id, e.event_type, e.start_time, e.end_time, e.title, e.location_id, l.canonical_name;


-- ============================================================================
-- MATERIALIZED VIEWS (For fast analytics)
-- ============================================================================

-- Exercise progression view
CREATE MATERIALIZED VIEW exercise_progression AS
SELECT 
    ex.id AS exercise_id,
    ex.canonical_name AS exercise_name,
    ex.category,
    ex.primary_muscle_group,
    DATE(ev.start_time) AS workout_date,
    w.id AS workout_id,
    ev.id AS event_id,
    es.set_number,
    es.weight_kg,
    es.reps,
    es.volume_kg,
    es.duration_s,
    es.distance_km,
    -- Calculate estimated 1RM (Brzycki formula)
    CASE 
        WHEN es.weight_kg > 0 AND es.reps > 0 AND es.reps < 37
        THEN ROUND((es.weight_kg * 36.0 / (37.0 - es.reps))::NUMERIC, 2)
        ELSE NULL
    END AS estimated_1rm
FROM exercises ex
JOIN workout_exercises we ON ex.id = we.exercise_id
JOIN workouts w ON we.workout_id = w.id
JOIN events ev ON w.event_id = ev.id
JOIN exercise_sets es ON we.id = es.workout_exercise_id
ORDER BY ex.canonical_name, DATE(ev.start_time) DESC, es.set_number;

CREATE INDEX idx_exercise_progression_exercise ON exercise_progression(exercise_id, workout_date DESC);
CREATE INDEX idx_exercise_progression_name ON exercise_progression(exercise_name, workout_date DESC);
CREATE INDEX idx_exercise_progression_muscle ON exercise_progression(primary_muscle_group, workout_date DESC);


-- Muscle group frequency (last 90 days)
CREATE MATERIALIZED VIEW muscle_group_analysis AS
SELECT 
    ex.primary_muscle_group,
    DATE_TRUNC('week', DATE(ev.start_time))::DATE AS week_start,
    DATE_TRUNC('month', DATE(ev.start_time))::DATE AS month_start,
    COUNT(DISTINCT w.id) AS workout_count,
    COUNT(DISTINCT we.id) AS exercise_count,
    COUNT(es.id) AS total_sets,
    COALESCE(SUM(es.volume_kg), 0) AS total_volume_kg,
    MAX(DATE(ev.start_time)) AS last_workout_date
FROM exercises ex
JOIN workout_exercises we ON ex.id = we.exercise_id
JOIN workouts w ON we.workout_id = w.id
JOIN events ev ON w.event_id = ev.id
LEFT JOIN exercise_sets es ON we.id = es.workout_exercise_id
WHERE DATE(ev.start_time) >= CURRENT_DATE - INTERVAL '90 days'
  AND ex.primary_muscle_group IS NOT NULL
GROUP BY ex.primary_muscle_group, week_start, month_start;

CREATE INDEX idx_muscle_group_analysis_group ON muscle_group_analysis(primary_muscle_group, month_start DESC);


-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Refresh all materialized views
CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY exercise_progression;
    REFRESH MATERIALIZED VIEW CONCURRENTLY muscle_group_analysis;
END;
$$ LANGUAGE plpgsql;


-- NEW: Auto-update hierarchy fields when event is created/updated
CREATE OR REPLACE FUNCTION update_event_hierarchy()
RETURNS TRIGGER AS $$
DECLARE
    v_parent_level INTEGER;
    v_parent_path TEXT;
BEGIN
    IF NEW.parent_event_id IS NOT NULL THEN
        -- Get parent's hierarchy info
        SELECT hierarchy_level, hierarchy_path
        INTO v_parent_level, v_parent_path
        FROM events
        WHERE id = NEW.parent_event_id;
        
        -- Set child's hierarchy level and path
        NEW.hierarchy_level := COALESCE(v_parent_level, 0) + 1;
        NEW.hierarchy_path := COALESCE(v_parent_path || '/', '') || NEW.parent_event_id::TEXT;
    ELSE
        -- Root event
        NEW.hierarchy_level := 0;
        NEW.hierarchy_path := NULL;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_event_hierarchy
BEFORE INSERT OR UPDATE OF parent_event_id ON events
FOR EACH ROW
EXECUTE FUNCTION update_event_hierarchy();


-- NEW: Get all child events recursively
CREATE OR REPLACE FUNCTION get_event_children(p_event_id UUID, p_max_depth INTEGER DEFAULT 10)
RETURNS TABLE (
    id UUID,
    event_type VARCHAR,
    title VARCHAR,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    hierarchy_level INTEGER,
    depth INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE event_tree AS (
        -- Base case: the parent event
        SELECT 
            e.id,
            e.event_type,
            e.title,
            e.start_time,
            e.end_time,
            e.hierarchy_level,
            0 AS depth
        FROM events e
        WHERE e.id = p_event_id
        
        UNION ALL
        
        -- Recursive case: children
        SELECT 
            e.id,
            e.event_type,
            e.title,
            e.start_time,
            e.end_time,
            e.hierarchy_level,
            et.depth + 1
        FROM events e
        JOIN event_tree et ON e.parent_event_id = et.id
        WHERE et.depth < p_max_depth
    )
    SELECT * FROM event_tree WHERE depth > 0 ORDER BY start_time;
END;
$$ LANGUAGE plpgsql;


-- NEW: Get event breadcrumb path (from root to event)
CREATE OR REPLACE FUNCTION get_event_breadcrumb(p_event_id UUID)
RETURNS TABLE (
    id UUID,
    title VARCHAR,
    event_type VARCHAR,
    hierarchy_level INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE breadcrumb AS (
        -- Start with the target event
        SELECT 
            e.id,
            e.title,
            e.event_type,
            e.hierarchy_level,
            e.parent_event_id
        FROM events e
        WHERE e.id = p_event_id
        
        UNION ALL
        
        -- Walk up to parents
        SELECT 
            e.id,
            e.title,
            e.event_type,
            e.hierarchy_level,
            e.parent_event_id
        FROM events e
        JOIN breadcrumb b ON e.id = b.parent_event_id
    )
    SELECT id, title, event_type, hierarchy_level 
    FROM breadcrumb 
    ORDER BY hierarchy_level;
END;
$$ LANGUAGE plpgsql;


-- Get or create person by name
CREATE OR REPLACE FUNCTION get_or_create_person(p_name TEXT)
RETURNS UUID AS $$
DECLARE
    v_person_id UUID;
BEGIN
    SELECT id INTO v_person_id
    FROM people
    WHERE canonical_name ILIKE p_name
    LIMIT 1;
    
    IF v_person_id IS NULL THEN
        INSERT INTO people (canonical_name)
        VALUES (p_name)
        RETURNING id INTO v_person_id;
    END IF;
    
    RETURN v_person_id;
END;
$$ LANGUAGE plpgsql;


-- Get or create location by name
CREATE OR REPLACE FUNCTION get_or_create_location(l_name TEXT, l_type TEXT DEFAULT NULL)
RETURNS UUID AS $$
DECLARE
    v_location_id UUID;
BEGIN
    SELECT id INTO v_location_id
    FROM locations
    WHERE canonical_name ILIKE l_name
    LIMIT 1;
    
    IF v_location_id IS NULL THEN
        INSERT INTO locations (canonical_name, location_type)
        VALUES (l_name, l_type)
        RETURNING id INTO v_location_id;
    END IF;
    
    RETURN v_location_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE events IS 'Primary aggregate root - owns WHO (participants), WHERE (location), WHEN (time) for all activities';
COMMENT ON TABLE workouts IS 'Workout-specific data - references events for common attributes';
COMMENT ON TABLE meals IS 'Meal-specific data with nutritional information - references events';
COMMENT ON TABLE commutes IS 'Commute/travel-specific data - references events for timing and participants';
COMMENT ON TABLE entertainment IS 'Entertainment-specific data (movies, TV, videos, podcasts, live performances, gaming, reading) - references events';
COMMENT ON TABLE exercises IS 'Exercise catalog - reference data';
COMMENT ON TABLE people IS 'People directory - reference data';
COMMENT ON TABLE locations IS 'Location catalog - reference data';
COMMENT ON TABLE journal_days IS 'Top-level daily summary aggregating all activities';
COMMENT ON TABLE event_participants IS 'Shared participant table for all event types';

COMMENT ON COLUMN exercise_sets.volume_kg IS 'Computed as weight_kg * reps';
COMMENT ON COLUMN exercise_sets.interval_description IS 'Free-text interval description (e.g., "20s work, 10s rest" for Tabata)';
COMMENT ON COLUMN exercise_sets.work_duration_s IS 'Work duration in seconds for interval training';
COMMENT ON COLUMN exercise_sets.rest_duration_s IS 'Rest duration in seconds for interval training';
COMMENT ON COLUMN events.external_event_id IS 'Reference to event ID in external/legacy systems (e.g., "event_168")';
COMMENT ON MATERIALIZED VIEW exercise_progression IS 'Historical exercise data for progression tracking';
COMMENT ON MATERIALIZED VIEW muscle_group_analysis IS 'Muscle group frequency analysis (90 days)';


-- End of schema.sql

-- ============================================================================
-- MEMORY SYSTEM (Stage 2)
-- ============================================================================

CREATE TABLE IF NOT EXISTS journal_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_text TEXT NOT NULL,
    entry_date DATE NOT NULL,
    entry_type VARCHAR(50) DEFAULT 'journal', -- 'journal', 'reflection', 'log'
    tags TEXT[],
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_date ON journal_entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_journal_entries_type ON journal_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_journal_entries_is_deleted ON journal_entries(is_deleted) WHERE is_deleted = TRUE;


-- ============================================================
-- DAILY PLANNING TABLES (added 2026-02-19)
-- ============================================================

-- daily_plans: High-level plan for a day, versioned.
-- Written by daily-tracker skill at plan approval.
CREATE TABLE IF NOT EXISTS daily_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_date DATE NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    source VARCHAR(50) DEFAULT 'daily_tracker',  -- daily_tracker, manual, weekly_plan
    time_budget JSONB,  -- {"work": 360, "personal": 120, "health": 90} (minutes)
    notes TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_plans_date ON daily_plans(plan_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_plans_date_version
    ON daily_plans(plan_date, version) WHERE is_deleted = FALSE;

-- planned_items: Individual timeline items within a daily plan.
-- Status updated at check-in and wrap-up.
CREATE TABLE IF NOT EXISTS planned_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_id UUID NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_minutes INTEGER,
    category VARCHAR(50),   -- work, personal, health, break, social, family, finance
    item_type VARCHAR(50),  -- focused_work, meeting, meal, workout, errand, commute, entertainment, other
    priority VARCHAR(20) DEFAULT 'medium',  -- high, medium, low
    actual_event_id UUID REFERENCES events(id),  -- linked journal event
    status VARCHAR(20) DEFAULT 'planned',   -- planned, in-progress, completed, skipped, modified, replaced
    status_notes TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planned_items_plan ON planned_items(plan_id);
CREATE INDEX IF NOT EXISTS idx_planned_items_actual
    ON planned_items(actual_event_id) WHERE actual_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_planned_items_status ON planned_items(status);

-- plan_vs_actual view: Joins planned items with actual journal events.
CREATE OR REPLACE VIEW plan_vs_actual AS
SELECT
    dp.plan_date,
    dp.version AS plan_version,
    dp.id AS plan_id,
    pi.id AS item_id,
    pi.title AS planned_title,
    pi.start_time AS planned_start,
    pi.end_time AS planned_end,
    pi.duration_minutes AS planned_duration,
    pi.category AS planned_category,
    pi.item_type AS planned_item_type,
    pi.priority,
    pi.status,
    pi.status_notes,
    e.title AS actual_title,
    e.start_time AS actual_start,
    e.end_time AS actual_end,
    e.duration_minutes AS actual_duration,
    CASE
        WHEN pi.actual_event_id IS NOT NULL THEN 'linked'
        WHEN pi.status = 'completed' THEN 'completed_unlinked'
        WHEN pi.status = 'skipped' THEN 'skipped'
        WHEN pi.status = 'in-progress' THEN 'in_progress'
        WHEN pi.status = 'planned' THEN 'pending'
        ELSE pi.status
    END AS resolution,
    CASE
        WHEN pi.actual_event_id IS NOT NULL
            AND pi.end_time IS NOT NULL
            AND e.end_time IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM (e.end_time - pi.end_time)) / 60)
        ELSE NULL
    END AS end_time_delta_minutes
FROM daily_plans dp
JOIN planned_items pi ON pi.plan_id = dp.id
LEFT JOIN events e ON e.id = pi.actual_event_id AND e.is_deleted = FALSE
WHERE dp.is_deleted = FALSE
ORDER BY dp.plan_date, dp.version, pi.start_time NULLS LAST;
