-- ================================================================
-- SCHEMA MIGRATION 001: Dynamic Rules Engine
-- ================================================================
-- Purpose: Add tables for dynamic, database-driven rules management
-- Depends on: schema.sql (base tables already exist)
-- Date: 2026-05-04
--
-- Tables added:
--   rounding_rules  — deterministic rounding rules (previously JSON only)
--   rules_audit_log — audit trail for admin changes to rules
--
-- Existing tables used as-is:
--   formulas, policies, exemptions
-- ================================================================

-- ================================================================
-- 1. ROUNDING RULES TABLE
-- ================================================================
-- Previously only in configs/rounding_rules.json — now DB-driven
CREATE TABLE IF NOT EXISTS rounding_rules (
    rule_id VARCHAR(50) PRIMARY KEY,
    rule_name VARCHAR(200) NOT NULL,
    applies_to TEXT[] NOT NULL,              -- e.g. {'cop_amount','sop_amount','vop_amount'}
    rounding_method VARCHAR(30) NOT NULL,    -- 'CEILING_100', 'ROUND_WHOLE', 'NONE'
    precision INTEGER DEFAULT 100,           -- rounding precision (100 = nearest 100)
    priority VARCHAR(20) DEFAULT 'HIGH',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rounding_active ON rounding_rules(is_active, effective_date);

COMMENT ON TABLE rounding_rules IS 'Deterministic rounding rules for customs duty calculations';
COMMENT ON COLUMN rounding_rules.rounding_method IS 'CEILING_100 = ceil to nearest 100, ROUND_WHOLE = round to nearest 1, NONE = no rounding';
COMMENT ON COLUMN rounding_rules.applies_to IS 'Array of field names this rule applies to (e.g. cop_amount, vop_amount, total_payable)';

-- Apply updated_at trigger
CREATE TRIGGER update_rounding_rules_updated_at BEFORE UPDATE ON rounding_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ================================================================
-- 2. RULES AUDIT LOG TABLE
-- ================================================================
-- Tracks who changed what rule, when, and what the old/new values were
CREATE TABLE IF NOT EXISTS rules_audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,         -- 'formulas', 'policies', 'rounding_rules', etc.
    record_id VARCHAR(100) NOT NULL,         -- PK of the changed record
    action VARCHAR(20) NOT NULL,             -- 'CREATE', 'UPDATE', 'DEACTIVATE'
    old_value JSONB,                         -- previous state (NULL for CREATE)
    new_value JSONB NOT NULL,                -- new state
    changed_by VARCHAR(100) DEFAULT 'admin', -- who made the change
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT                              -- optional reason for the change
);

CREATE INDEX IF NOT EXISTS idx_audit_table ON rules_audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_date ON rules_audit_log(changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_record ON rules_audit_log(table_name, record_id);

COMMENT ON TABLE rules_audit_log IS 'Audit trail for all admin changes to rules, formulas, and policies';


-- ================================================================
-- 3. VIEW: Active formulas with version info
-- ================================================================
CREATE OR REPLACE VIEW active_formulas AS
SELECT
    formula_id,
    formula_name,
    formula_type,
    expression,
    description,
    variables,
    version,
    effective_date,
    end_date
FROM formulas
WHERE is_active = TRUE
  AND (end_date IS NULL OR end_date > CURRENT_DATE);


-- ================================================================
-- 4. VIEW: Active rounding rules
-- ================================================================
CREATE OR REPLACE VIEW active_rounding_rules AS
SELECT
    rule_id,
    rule_name,
    applies_to,
    rounding_method,
    precision,
    priority,
    description
FROM rounding_rules
WHERE is_active = TRUE
  AND (end_date IS NULL OR end_date > CURRENT_DATE);


-- ================================================================
-- 5. VIEW: Active policies ordered by priority
-- ================================================================
CREATE OR REPLACE VIEW active_policies AS
SELECT
    policy_id,
    policy_name,
    policy_type,
    conditions,
    actions,
    priority,
    description
FROM policies
WHERE is_active = TRUE
  AND (end_date IS NULL OR end_date > CURRENT_DATE)
ORDER BY priority ASC;


-- ================================================================
-- END OF MIGRATION
-- ================================================================
