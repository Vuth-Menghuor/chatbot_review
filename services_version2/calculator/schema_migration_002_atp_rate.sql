-- ================================================================
-- SCHEMA MIGRATION 002: Add ATP Rate to Duty Rates
-- ================================================================
-- Purpose: Add atp_rate column to duty_rates for petroleum products
-- Date: 2026-05-25
--
-- ATP = Additional Tax on Petroleum product
-- Rate is in $/L (e.g., 0.02 = $0.02 per liter)
-- ================================================================

-- Add atp_rate column to duty_rates table
ALTER TABLE duty_rates
ADD COLUMN IF NOT EXISTS atp_rate DECIMAL(10,4) DEFAULT 0.00;

COMMENT ON COLUMN duty_rates.atp_rate IS 'Additional Tax on Petroleum (ATP) rate in USD per liter. Only applies to petroleum HS codes (2710.xx)';
