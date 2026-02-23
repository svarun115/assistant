-- Migration: Add daily_plans and planned_items tables for plan tracking
-- Date: 2026-02-19

BEGIN;

-- ============================================================
-- Table: daily_plans
-- Stores the high-level plan for a given day, versioned.
-- Written by daily-tracker skill at plan approval.
-- ============================================================
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

CREATE INDEX IF NOT EXISTS idx_daily_plans_date
    ON daily_plans(plan_date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_plans_date_version
    ON daily_plans(plan_date, version)
    WHERE is_deleted = FALSE;


-- ============================================================
-- Table: planned_items
-- Stores individual timeline items within a daily plan.
-- Status updated at check-in and wrap-up.
-- ============================================================
CREATE TABLE IF NOT EXISTS planned_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_id UUID NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_minutes INTEGER,
    category VARCHAR(50),    -- work, personal, health, break, social, family, finance
    item_type VARCHAR(50),   -- focused_work, meeting, meal, workout, errand, commute, entertainment, other
    priority VARCHAR(20) DEFAULT 'medium',  -- high, medium, low
    actual_event_id UUID REFERENCES events(id),  -- linked journal event (set at check-in/wrap-up)
    status VARCHAR(20) DEFAULT 'planned',   -- planned, in-progress, completed, skipped, modified, replaced
    status_notes TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planned_items_plan
    ON planned_items(plan_id);

CREATE INDEX IF NOT EXISTS idx_planned_items_actual
    ON planned_items(actual_event_id)
    WHERE actual_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_planned_items_status
    ON planned_items(status);


-- ============================================================
-- View: plan_vs_actual
-- Joins planned items with actual journal events for comparison.
-- Used by get_plan_vs_actual tool and wrap-up flow.
-- ============================================================
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

COMMIT;
