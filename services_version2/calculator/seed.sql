-- ================================================================
-- CUSTOMS AI DATABASE SEED DATA
-- ================================================================
-- Database: customs_ai
-- Purpose: Load initial data for tax calculation system
-- Last Updated: 2026-03-04
-- ================================================================

BEGIN;

-- ================================================================
-- 1. LOAD HS CODES
-- ================================================================
-- Source: data/processed/structured/hs_master.csv
-- Columns: "HS Code", "Description", "Unit" (with spaces in CSV)

-- Create temporary table to match CSV column names exactly
CREATE TEMP TABLE temp_hs_codes (
    "HS Code" VARCHAR(15),
    "Description" TEXT,
    "Unit" VARCHAR(50)
);

\COPY temp_hs_codes FROM :'hs_master_csv' WITH CSV HEADER DELIMITER ',';

-- Insert into actual table with normalized column names
INSERT INTO hs_codes(hs_code, description, unit)
SELECT "HS Code", "Description", "Unit"
FROM temp_hs_codes;

DROP TABLE temp_hs_codes;

-- Set all HS codes as active with effective date
UPDATE hs_codes 
SET 
    is_active = TRUE,
    effective_date = '2026-01-01'
WHERE effective_date = CURRENT_DATE;

-- ================================================================
-- 2. LOAD DUTY RATES
-- ================================================================
-- Source: data/processed/structured/duty_rates.csv
-- Columns: "HS Code", "Description", "Unit", "CD Rate", "ST Rate", "VAT Rate", "ET Rate" (with spaces)

-- Create temporary table to match CSV column names exactly
CREATE TEMP TABLE temp_duty_rates (
    "HS Code" VARCHAR(15),
    "Description" TEXT,
    "Unit" VARCHAR(50),
    "CD Rate" VARCHAR(20),
    "ST Rate" VARCHAR(20),
    "VAT Rate" VARCHAR(20),
    "ET Rate" VARCHAR(20)
);

\COPY temp_duty_rates FROM :'duty_rates_csv' WITH CSV HEADER DELIMITER ',';

-- Insert into actual table with normalized column names and cleaned numeric values
INSERT INTO duty_rates(hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate)
SELECT 
    "HS Code",
    "Description",
    "Unit",
    CASE 
        WHEN "CD Rate" ~ '^-?[0-9]+\.?[0-9]*$' THEN CAST("CD Rate" AS DECIMAL(5,2))
        ELSE 0.00
    END as cd_rate,
    CASE 
        WHEN "ST Rate" ~ '^-?[0-9]+\.?[0-9]*$' THEN CAST("ST Rate" AS DECIMAL(5,2))
        ELSE 0.00
    END as st_rate,
    CASE 
        WHEN "VAT Rate" ~ '^-?[0-9]+\.?[0-9]*$' THEN CAST("VAT Rate" AS DECIMAL(5,2))
        ELSE 10.00
    END as vat_rate,
    CASE 
        WHEN "ET Rate" ~ '^-?[0-9]+\.?[0-9]*$' THEN CAST("ET Rate" AS DECIMAL(5,2))
        ELSE 0.00
    END as et_rate
FROM temp_duty_rates;

DROP TABLE temp_duty_rates;

-- Normalize origin_country to 'XX' for general MFN rates
UPDATE duty_rates 
SET origin_country = 'XX' 
WHERE origin_country IS NULL OR origin_country = '';

-- ================================================================
-- 3. INSERT EXCHANGE RATES
-- ================================================================
-- Source: configs/exchange_rate/exchange_rates_selenium_20260219_094940.csv

-- Using COPY with transformation (if CSV structure matches)
-- Note: The CSV format needs transformation, so we'll insert manually

INSERT INTO exchange_rates (currency_code, currency_name, usd_rate, khr_rate, effective_date, source) VALUES
('USD', 'US Dollar', 1.0000, 4022.0000, '2026-02-19', 'NBC'),
('AUD', 'Australia', 1.4068, 2859.0000, '2026-02-19', 'NBC'),
('CAD', 'Canada', 1.3595, 2958.5000, '2026-02-19', 'NBC'),
('CNY', 'China', 6.8693, 585.5000, '2026-02-19', 'NBC'),
('CNH', 'China in Hong Kong', 6.8518, 587.0000, '2026-02-19', 'NBC'),
('GBP', 'England', 0.7337, 5482.0000, '2026-02-19', 'NBC'),
('EUR', 'Euro', 0.8407, 4784.0000, '2026-02-19', 'NBC'),
('HKD', 'Hong Kong', 7.7720, 517.5000, '2026-02-19', 'NBC'),
('INR', 'India', 90.2097, 44.5850, '2026-02-19', 'NBC'),
('IDR', 'Indonesia', 16793.3194, 0.2395, '2026-02-19', 'NBC'),
('JPY', 'Japan', 152.8987, 26.3050, '2026-02-19', 'NBC'),
('LAK', 'Lao PDR', 21168.4211, 0.1900, '2026-02-19', 'NBC'),
('MMK', 'Myanmar', 2083.9378, 1.9300, '2026-02-19', 'NBC'),
('MYR', 'Malaysia', 3.8785, 1037.0000, '2026-02-19', 'NBC'),
('NZD', 'New Zealand', 1.6579, 2426.0000, '2026-02-19', 'NBC'),
('PHP', 'Philippines', 57.5682, 69.8650, '2026-02-19', 'NBC'),
('SGD', 'Singapore', 1.2577, 3198.0000, '2026-02-19', 'NBC'),
('KRW', 'South Korea', 1436.4286, 2.8000, '2026-02-19', 'NBC'),
('SDR', 'Special Drawing Right', 0.7223, 5568.0000, '2026-02-19', 'NBC'),
('SEK', 'Sweden', 8.9279, 450.5000, '2026-02-19', 'NBC'),
('CHF', 'Switzerland', 0.7676, 5240.0000, '2026-02-19', 'NBC'),
('TWD', 'Taiwan', 31.2996, 128.5000, '2026-02-19', 'NBC'),
('THB', 'Thailand', 31.0579, 129.5000, '2026-02-19', 'NBC'),
('VND', 'Vietnam', 25864.9518, 0.1555, '2026-02-19', 'NBC'),
('AED', 'United Arab Emirates Dirham', 3.6547, 1100.5000, '2026-02-19', 'NBC'),
('ZAR', 'South Africa Rand', 15.8972, 253.0000, '2026-02-19', 'NBC'),
('NGN', 'Nigeria Naira', 1325.2059, 3.0350, '2026-02-19', 'NBC'),
('DKK', 'Danish Krone', 6.2795, 640.5000, '2026-02-19', 'NBC'),
('SAR', 'Saudi Riyal', 3.7327, 1077.5000, '2026-02-19', 'NBC'),
('KHR', 'Cambodian Riel', 4022.0000, 1.0000, '2026-02-19', 'NBC')
ON CONFLICT (currency_code, effective_date) DO NOTHING;

-- ================================================================
-- 4. INSERT FEES
-- ================================================================
INSERT INTO fees (fee_code, fee_name, basis, amount, currency, notes, effective_date) VALUES
('SCANNER_20', 'Container Scanner Fee (20ft)', 'per container', 45000, 'KHR', 'Mandatory scanning fee for 20-foot containers', '2025-01-01'),
('SCANNER_40', 'Container Scanner Fee (40ft)', 'per container', 90000, 'KHR', 'Mandatory scanning fee for 40-foot containers', '2025-01-01'),
('STORAGE_DAY', 'Container Storage Fee', 'per day', 15000, 'KHR', 'Daily storage fee after free period expires', '2025-01-01'),
('OVERTIME', 'Overtime Processing Fee', 'per declaration', 50000, 'KHR', 'Customs processing outside normal hours', '2025-01-01'),
('INSPECTION', 'Physical Inspection Fee', 'per container', 100000, 'KHR', 'Random or targeted physical inspection', '2025-01-01')
ON CONFLICT (fee_code) DO NOTHING;

-- ================================================================
-- 5. INSERT EXEMPTIONS
-- ================================================================
INSERT INTO exemptions (
    exemption_code, regime_name, exemption_type,
    cd_exempt, st_exempt, vat_exempt, et_exempt,
    cd_reduction_pct, vat_reduction_pct,
    conditions, effective_date
) VALUES
('DIP', 'Duty Incentive Program', 'full', TRUE, TRUE, TRUE, FALSE, 0, 0, 
 'Approved manufacturing for export. Certificate of Eligibility required.', '2025-01-01'),
 
('QIP', 'Qualified Investment Project', 'full', TRUE, TRUE, TRUE, FALSE, 0, 0,
 'CDC-approved investment project. QIP certificate required.', '2025-01-01'),
 
('EXP', 'Export Goods', 'full', TRUE, TRUE, TRUE, TRUE, 0, 0,
 'Goods for direct export. Export declaration required.', '2025-01-01'),
 
('TMP', 'Temporary Import', 'full', TRUE, FALSE, TRUE, FALSE, 0, 0,
 'Temporary admission. Re-export within 6 months required.', '2025-01-01'),
 
('NGO', 'NGO Humanitarian', 'full', TRUE, TRUE, TRUE, FALSE, 0, 0,
 'Registered NGO humanitarian imports. MoFA approval required.', '2025-01-01'),
 
('ATIGA', 'ASEAN Trade in Goods Agreement', 'partial_cd', FALSE, FALSE, FALSE, FALSE, 100, 0,
 'ASEAN origin goods with Form D. 0% duty under ATIGA.', '2025-01-01'),
 
('ACFTA', 'ASEAN-China FTA', 'partial_cd', FALSE, FALSE, FALSE, FALSE, 100, 0,
 'China origin goods with Form E. Preferential rates apply.', '2025-01-01'),
 
('AKFTA', 'ASEAN-Korea FTA', 'partial_cd', FALSE, FALSE, FALSE, FALSE, 100, 0,
 'Korea origin goods with Form AK. Preferential rates apply.', '2025-01-01'),
 
('DIPLOMATIC', 'Diplomatic Immunity', 'full', TRUE, TRUE, TRUE, FALSE, 0, 0,
 'Embassy/consulate imports. Diplomatic ID required.', '2025-01-01'),
 
('PERSONAL', 'Personal Effects Exemption', 'partial_cd', FALSE, FALSE, TRUE, FALSE, 100, 0,
 'Personal belongings under USD 400 value. First-time import.', '2025-01-01'),
 
('SAMPLES', 'Commercial Samples', 'full', TRUE, FALSE, TRUE, FALSE, 0, 0,
 'No commercial value samples. Value < USD 100.', '2025-01-01'),
 
('REPAIR', 'Re-import After Repair', 'partial_cd', FALSE, FALSE, TRUE, FALSE, 100, 0,
 'Goods sent abroad for repair. Only repair cost taxable.', '2025-01-01'),
 
('EDUCATION', 'Educational Institution', 'partial_cd', FALSE, TRUE, TRUE, FALSE, 100, 0,
 'Books, equipment for schools/universities. MoEYS approval.', '2025-01-01')
ON CONFLICT (exemption_code) DO NOTHING;

-- ================================================================
-- 6. INSERT FORMULAS
-- ================================================================
INSERT INTO formulas (formula_id, formula_name, formula_type, expression, description, variables, effective_date) VALUES
('CIF_01', 'CIF Calculation', 'cif',
 'invoice_value + freight + insurance',
 'Calculate CIF (Cost, Insurance, Freight) value from FOB components',
 '["invoice_value", "freight", "insurance"]'::jsonb,
 '2025-01-01'),

('CD_01', 'Customs Duty Calculation', 'duty',
 'cif_value * (cd_rate / 100)',
 'Calculate Customs Duty as percentage of CIF value',
 '["cif_value", "cd_rate"]'::jsonb,
 '2025-01-01'),

('ST_01', 'Special Tax Calculation', 'duty',
 'cif_value * (st_rate / 100)',
 'Calculate Special Tax (Excise) as percentage of CIF value',
 '["cif_value", "st_rate"]'::jsonb,
 '2025-01-01'),

('VAT_01', 'VAT Calculation', 'vat',
 '(cif_value + customs_duty + special_tax) * (vat_rate / 100)',
 'Calculate VAT on sum of CIF, CD, and ST',
 '["cif_value", "customs_duty", "special_tax", "vat_rate"]'::jsonb,
 '2025-01-01'),

('TOTAL_01', 'Total Tax Calculation', 'total',
 'customs_duty + special_tax + vat',
 'Calculate total tax liability',
 '["customs_duty", "special_tax", "vat"]'::jsonb,
 '2025-01-01'),

('FX_01', 'Currency Conversion to KHR', 'conversion',
 'amount * exchange_rate',
 'Convert foreign currency amount to KHR using exchange rate',
 '["amount", "exchange_rate"]'::jsonb,
 '2025-01-01'),

('EXEMPT_CD_01', 'Exemption Adjustment - CD', 'adjustment',
 'customs_duty * (1 - cd_reduction_pct / 100)',
 'Apply exemption reduction to Customs Duty',
 '["customs_duty", "cd_reduction_pct"]'::jsonb,
 '2025-01-01'),

('EXEMPT_VAT_01', 'Exemption Adjustment - VAT', 'adjustment',
 'vat * (1 - vat_reduction_pct / 100)',
 'Apply exemption reduction to VAT',
 '["vat", "vat_reduction_pct"]'::jsonb,
 '2025-01-01')
ON CONFLICT (formula_id) DO NOTHING;

-- ================================================================
-- 7. INSERT POLICIES
-- ================================================================
INSERT INTO policies (policy_id, policy_name, policy_type, conditions, actions, priority, description, effective_date) VALUES
('POL_CD_01', 'Apply Standard Customs Duty', 'duty',
 '{"exemption": null, "fta_eligible": false}'::jsonb,
 '{"calculate": "CD_01", "apply_rate": "cd_rate"}'::jsonb,
 100,
 'Standard customs duty calculation using MFN rates',
 '2025-01-01'),

('POL_VAT_01', 'Apply Standard VAT', 'vat',
 '{"exemption": null, "vat_exempt": false}'::jsonb,
 '{"calculate": "VAT_01", "apply_rate": "vat_rate"}'::jsonb,
 100,
 'Standard VAT calculation at 10% on CIF + CD + ST',
 '2025-01-01'),

('POL_EXEMPT_01', 'Process Exemption Claims', 'exemption',
 '{"exemption_code": {"$ne": null}}'::jsonb,
 '{"validate_certificate": true, "apply_reductions": true}'::jsonb,
 50,
 'Validate and apply exemption benefits when exemption code provided',
 '2025-01-01')
ON CONFLICT (policy_id) DO NOTHING;

COMMIT;

-- ================================================================
-- VERIFICATION QUERIES
-- ================================================================
-- Run these after seed completes to verify data loaded correctly

-- SELECT 'hs_codes' as table_name, COUNT(*) as row_count FROM hs_codes
-- UNION ALL
-- SELECT 'duty_rates', COUNT(*) FROM duty_rates
-- UNION ALL
-- SELECT 'exchange_rates', COUNT(*) FROM exchange_rates
-- UNION ALL
-- SELECT 'fees', COUNT(*) FROM fees
-- UNION ALL
-- SELECT 'exemptions', COUNT(*) FROM exemptions
-- UNION ALL
-- SELECT 'formulas', COUNT(*) FROM formulas
-- UNION ALL
-- SELECT 'policies', COUNT(*) FROM policies
-- UNION ALL
-- SELECT 'formulas', COUNT(*) FROM formulas;

-- ================================================================
-- END OF SEED
-- ================================================================
