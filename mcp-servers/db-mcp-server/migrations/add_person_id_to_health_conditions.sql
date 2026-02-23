-- Migration: Add person_id to health_conditions and health_condition_logs
-- Issue: #121 - Add person_id to health_conditions for non-owner tracking
-- Date: 2026-02-15
-- Author: Claude Code

BEGIN;

-- 1. Add person_id columns (nullable initially for migration)
ALTER TABLE health_conditions
ADD COLUMN IF NOT EXISTS person_id UUID;

ALTER TABLE health_condition_logs
ADD COLUMN IF NOT EXISTS person_id UUID;

-- 2. Backfill existing data from event_participants
-- Get person_id from the event's first participant
UPDATE health_conditions hc
SET person_id = (
    SELECT ep.person_id
    FROM event_participants ep
    WHERE ep.event_id = hc.event_id
    LIMIT 1
)
WHERE person_id IS NULL;

-- Backfill health_condition_logs from parent condition
UPDATE health_condition_logs hcl
SET person_id = (
    SELECT person_id
    FROM health_conditions
    WHERE id = hcl.condition_id
)
WHERE person_id IS NULL;

-- 3. Add foreign key constraints
ALTER TABLE health_conditions
ADD CONSTRAINT fk_health_conditions_person
FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE;

ALTER TABLE health_condition_logs
ADD CONSTRAINT fk_health_condition_logs_person
FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE;

-- 4. Create indexes
CREATE INDEX IF NOT EXISTS idx_health_conditions_person
ON health_conditions(person_id);

CREATE INDEX IF NOT EXISTS idx_hcl_person
ON health_condition_logs(person_id);

-- 5. Validate migration
DO $$
DECLARE
    total_conditions INTEGER;
    migrated_conditions INTEGER;
    orphaned_conditions INTEGER;
    total_logs INTEGER;
    migrated_logs INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_conditions FROM health_conditions WHERE is_deleted = FALSE;
    SELECT COUNT(*) INTO migrated_conditions FROM health_conditions WHERE person_id IS NOT NULL AND is_deleted = FALSE;
    SELECT COUNT(*) INTO orphaned_conditions FROM health_conditions WHERE person_id IS NULL AND is_deleted = FALSE;

    SELECT COUNT(*) INTO total_logs FROM health_condition_logs WHERE is_deleted = FALSE;
    SELECT COUNT(*) INTO migrated_logs FROM health_condition_logs WHERE person_id IS NOT NULL AND is_deleted = FALSE;

    RAISE NOTICE '====================================';
    RAISE NOTICE 'Migration Summary:';
    RAISE NOTICE '  Health Conditions:';
    RAISE NOTICE '    Total: %', total_conditions;
    RAISE NOTICE '    Migrated: %', migrated_conditions;
    RAISE NOTICE '    Without person_id: %', orphaned_conditions;
    RAISE NOTICE '  Health Condition Logs:';
    RAISE NOTICE '    Total: %', total_logs;
    RAISE NOTICE '    Migrated: %', migrated_logs;
    RAISE NOTICE '====================================';

    IF orphaned_conditions > 0 THEN
        RAISE WARNING 'Found % health_conditions without person_id - manual review needed', orphaned_conditions;
    END IF;
END $$;

COMMIT;
