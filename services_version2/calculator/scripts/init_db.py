#!/usr/bin/env python3
"""
Calculator Service - Database Initialization Script (Standalone)
=================================================================
Creates the calculator's primary PostgreSQL database and all required tables.
Qdrant verification is OPTIONAL — the calculator is fully standalone.

Exit codes:
    0 — Calculator DB initialized successfully
    1 — Initialization failed
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from the calculator service .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- HS Codes master table
CREATE TABLE IF NOT EXISTS hs_codes (
    hs_code TEXT PRIMARY KEY,
    description TEXT,
    unit TEXT DEFAULT 'u',
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Duty rates table
CREATE TABLE IF NOT EXISTS duty_rates (
    id SERIAL PRIMARY KEY,
    hs_code TEXT NOT NULL,
    description TEXT,
    unit TEXT DEFAULT 'u',
    cd_rate NUMERIC(10,4) DEFAULT 0,
    st_rate NUMERIC(10,4) DEFAULT 0,
    vat_rate NUMERIC(10,4) DEFAULT 10,
    et_rate NUMERIC(10,4) DEFAULT 0,
    atp_rate NUMERIC(10,4) DEFAULT 0,
    origin_country TEXT DEFAULT 'XX',
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Exchange rates table
CREATE TABLE IF NOT EXISTS exchange_rates (
    id SERIAL PRIMARY KEY,
    currency_code TEXT NOT NULL,
    currency_name TEXT,
    usd_rate NUMERIC(15,4) DEFAULT 1.0,
    khr_rate NUMERIC(15,4) NOT NULL,
    effective_date DATE DEFAULT CURRENT_DATE,
    source TEXT DEFAULT 'NBC',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(currency_code, effective_date)
);

-- Deduction values (DV per metric ton)
CREATE TABLE IF NOT EXISTS declared_values (
    id SERIAL PRIMARY KEY,
    hs_code TEXT NOT NULL,
    dv_per_metric_ton NUMERIC(15,4) DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    effective_date DATE DEFAULT CURRENT_DATE,
    source TEXT DEFAULT 'government',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hs_code, effective_date)
);

-- Calculation history / audit trail
CREATE TABLE IF NOT EXISTS calculation_history (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    hs_code TEXT,
    origin_country TEXT,
    invoice_value NUMERIC(15,2),
    invoice_currency TEXT,
    freight NUMERIC(15,2),
    insurance NUMERIC(15,2),
    cif_value NUMERIC(15,2),
    customs_duty NUMERIC(15,2),
    special_tax NUMERIC(15,2),
    vat NUMERIC(15,2),
    export_tax NUMERIC(15,2),
    total_tax NUMERIC(15,2),
    exemption_code TEXT,
    calculation_method TEXT,
    formulas_used JSONB,
    input_data JSONB,
    result_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dynamic formulas
CREATE TABLE IF NOT EXISTS formulas (
    formula_id SERIAL PRIMARY KEY,
    formula_name TEXT NOT NULL,
    formula_type TEXT,
    expression TEXT,
    description TEXT,
    variables JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Policies
CREATE TABLE IF NOT EXISTS policies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    policy_type TEXT,
    conditions JSONB,
    value NUMERIC(15,4),
    effective_date DATE DEFAULT CURRENT_DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rounding rules
CREATE TABLE IF NOT EXISTS rounding_rules (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    rule_type TEXT,
    precision INTEGER,
    method TEXT,
    effective_date DATE DEFAULT CURRENT_DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Exemptions
CREATE TABLE IF NOT EXISTS exemptions (
    id SERIAL PRIMARY KEY,
    hs_code TEXT,
    exemption_type TEXT,
    value NUMERIC(15,4),
    conditions JSONB,
    effective_date DATE DEFAULT CURRENT_DATE,
    expires_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fees
CREATE TABLE IF NOT EXISTS fees (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    fee_type TEXT,
    amount NUMERIC(15,4),
    currency TEXT,
    conditions JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rules audit log
CREATE TABLE IF NOT EXISTS rules_audit_log (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER,
    action TEXT,
    old_value JSONB,
    new_value JSONB,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Preferential agreement types + eligible countries (reference only — rates are user-provided)
-- This replaces the old preferential_rates table that contained HS codes + rates.
-- One agreement can cover multiple origin countries (e.g., ATIGA → all ASEAN).
CREATE TABLE IF NOT EXISTS preferential_rates (
    id SERIAL PRIMARY KEY,
    agreement_code TEXT NOT NULL,
    origin_country TEXT NOT NULL,
    hs_code TEXT,
    name_kh TEXT,
    name_en TEXT,
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agreement_code, origin_country)
);

-- Country groups / regions (reference)
CREATE TABLE IF NOT EXISTS country_groups (
    id SERIAL PRIMARY KEY,
    type_id INTEGER,
    code TEXT NOT NULL UNIQUE,
    name TEXT,
    name_kh TEXT,
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Country to region mapping (reference)
CREATE TABLE IF NOT EXISTS countries_by_regions (
    id SERIAL PRIMARY KEY,
    country_code TEXT NOT NULL,
    region_code TEXT NOT NULL,
    region_desc TEXT,
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_code, region_code)
);
"""

SEED_SQL = """
-- Seed default exchange rate (USD -> KHR)
INSERT INTO exchange_rates (currency_code, currency_name, usd_rate, khr_rate, effective_date, source)
VALUES ('USD', 'US Dollar', 1.0, 4029.0, CURRENT_DATE, 'NBC')
ON CONFLICT (currency_code, effective_date) DO NOTHING;

-- Seed petroleum HS codes with hardcoded rates (untartab 2026-05-12)
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('2710.12.11', 'Motor gasoline, leaded', 'L', 'Hardcoded petroleum rate'),
('2710.12.12', 'Motor gasoline, unleaded', 'L', 'Hardcoded petroleum rate'),
('2710.12.13', 'Other motor fuel', 'L', 'Hardcoded petroleum rate'),
('2710.12.21', 'Gas oils (diesel)', 'L', 'Hardcoded petroleum rate'),
('2710.12.22', 'Kerosene', 'L', 'Hardcoded petroleum rate'),
('2710.12.23', 'Fuel oil', 'L', 'Hardcoded petroleum rate'),
('2710.12.24', 'Lubricating oils', 'L', 'Hardcoded petroleum rate'),
('2710.12.25', 'Hydraulic brake fluids', 'L', 'Hardcoded petroleum rate'),
('2710.12.26', 'Anti-freeze preparations', 'L', 'Hardcoded petroleum rate'),
('2710.12.27', 'Other lubricating preparations', 'L', 'Hardcoded petroleum rate'),
('2710.12.28', 'White spirit', 'L', 'Hardcoded petroleum rate'),
('2710.12.29', 'Other light oils', 'L', 'Hardcoded petroleum rate'),
('2710.19.71', 'Base oils for lubricants', 'L', 'Hardcoded petroleum rate'),
('2710.19.72', 'Other petroleum oils', 'L', 'Hardcoded petroleum rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Seed petroleum duty rates (CD=0%, ST=30%, VAT=10%, ATP=0.02$/L)
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT
    hs_code,
    description,
    unit,
    0.00, 0.30, 0.10, 0.0, 0.02,
    'XX',
    'Hardcoded petroleum rate (untartab 2026-05-12)'
FROM hs_codes
WHERE hs_code LIKE '2710.12.%' OR hs_code LIKE '2710.19.%'
ON CONFLICT DO NOTHING;

-- =====================================================================
-- Common HS codes & duty rates (representative Cambodian tariffs)
-- =====================================================================

-- Vehicles
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('8703.22.00', 'Motor cars, spark-ignition >1000cc but <=1500cc', 'u', 'Demo vehicle rate'),
('8703.23.00', 'Motor cars, spark-ignition >1500cc but <=3000cc', 'u', 'Demo vehicle rate'),
('8703.24.00', 'Motor cars, spark-ignition >3000cc', 'u', 'Demo vehicle rate'),
('8703.32.00', 'Motor cars, diesel >1500cc but <=2500cc', 'u', 'Demo vehicle rate'),
('8703.33.00', 'Motor cars, diesel >2500cc', 'u', 'Demo vehicle rate'),
('8711.10.00', 'Motorcycles, with reciprocating piston engine', 'u', 'Demo vehicle rate'),
('8704.21.00', 'Vehicles for transport of goods, diesel <=5 tonnes', 'u', 'Demo vehicle rate'),
('8704.31.00', 'Vehicles for transport of goods, diesel >5 tonnes', 'u', 'Demo vehicle rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Electronics
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('8517.13.00', 'Smartphones', 'u', 'Demo electronics rate'),
('8517.62.00', 'Machines for reception, conversion and transmission', 'u', 'Demo electronics rate'),
('8471.30.00', 'Portable automatic data processing machines (laptops)', 'u', 'Demo electronics rate'),
('8471.41.00', 'Automatic data processing machines, comprising CPU + input/output units', 'u', 'Demo electronics rate'),
('8528.72.00', 'Reception apparatus for television, colour', 'u', 'Demo electronics rate'),
('8525.89.00', 'Transmission apparatus for radio-telephony', 'u', 'Demo electronics rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Machinery
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('8408.10.00', 'Compression-ignition internal combustion piston engines (diesel)', 'u', 'Demo machinery rate'),
('8414.51.00', 'Table, floor, wall, window, ceiling or roof fans', 'u', 'Demo machinery rate'),
('8418.69.00', 'Other refrigerating or freezing equipment', 'u', 'Demo machinery rate'),
('8421.21.00', 'Machinery and apparatus for filtering or purifying water', 'u', 'Demo machinery rate'),
('8431.49.00', 'Parts of machinery of heading 8425 to 8430', 'u', 'Demo machinery rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Food & Agriculture
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('1006.10.00', 'Rice in the husk (paddy or rough)', 'kg', 'Demo agriculture rate'),
('1006.30.00', 'Semi-milled or wholly milled rice', 'kg', 'Demo agriculture rate'),
('0203.19.00', 'Meat of swine, frozen, other cuts', 'kg', 'Demo agriculture rate'),
('0207.14.00', 'Meat and edible offal of poultry, frozen cuts', 'kg', 'Demo agriculture rate'),
('0713.31.00', 'Beans, dried shelled, kidney beans', 'kg', 'Demo agriculture rate'),
('0901.11.00', 'Coffee, not roasted, not decaffeinated', 'kg', 'Demo agriculture rate'),
('1701.12.00', 'Beet sugar, raw, without added flavouring', 'kg', 'Demo agriculture rate'),
('1901.90.00', 'Other food preparations of flour, meal, starch or malt extract', 'kg', 'Demo food rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Textiles & Apparel
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('6109.10.00', 'T-shirts, singlets and other vests of cotton', 'u', 'Demo textile rate'),
('6103.22.00', 'Men\'s trousers, of cotton', 'u', 'Demo textile rate'),
('6104.62.00', 'Women\'s trousers, of cotton', 'u', 'Demo textile rate'),
('6203.42.00', 'Men\'s trousers, of cotton, not knitted', 'u', 'Demo textile rate'),
('6211.11.00', 'Men\'s swimwear', 'u', 'Demo textile rate'),
('6403.91.00', 'Footwear with outer soles of leather, covering the ankle', 'pr', 'Demo textile rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Beverages & Alcohol
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('2203.00.00', 'Beer made from malt', 'L', 'Demo beverage rate'),
('2208.20.00', 'Spirits obtained by distilling grape wine', 'L', 'Demo beverage rate'),
('2208.30.00', 'Whiskies', 'L', 'Demo beverage rate'),
('2208.90.00', 'Other spirituous beverages', 'L', 'Demo beverage rate'),
('2202.10.00', 'Waters, including mineral and aerated, containing added sugar', 'L', 'Demo beverage rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Metals & Materials
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('7204.10.00', 'Waste and scrap of cast iron', 'kg', 'Demo metal rate'),
('7204.21.00', 'Waste and scrap of stainless steel', 'kg', 'Demo metal rate'),
('7210.30.00', 'Flat-rolled products, iron or non-alloy steel, hot-dip galvanized', 'kg', 'Demo metal rate'),
('7308.90.00', 'Other structures and parts of structures, of iron or steel', 'kg', 'Demo metal rate'),
('3923.10.00', 'Boxes, cases, crates and similar articles, of plastics', 'kg', 'Demo plastic rate'),
('3926.90.00', 'Other articles of plastics', 'kg', 'Demo plastic rate')
ON CONFLICT (hs_code) DO NOTHING;

-- Furniture & Miscellaneous
INSERT INTO hs_codes (hs_code, description, unit, notes) VALUES
('9403.20.00', 'Other metal furniture', 'u', 'Demo furniture rate'),
('9403.60.00', 'Other wooden furniture', 'u', 'Demo furniture rate'),
('9405.10.00', 'Chandeliers and other electric ceiling or wall lighting fittings', 'u', 'Demo furniture rate'),
('3304.99.00', 'Other beauty or make-up preparations', 'kg', 'Demo cosmetic rate'),
('3004.90.00', 'Other medicaments, put up in measured doses', 'kg', 'Demo pharmaceutical rate')
ON CONFLICT (hs_code) DO NOTHING;

-- =====================================================================
-- Duty rates for common categories (representative Cambodian tariffs)
-- =====================================================================

-- Vehicles: CD=35%, ST=0%, VAT=10%, VVF=60,000 KHR
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.35, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo vehicle rate (CD 35%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '8703.%' OR hs_code LIKE '8711.%' OR hs_code LIKE '8704.%'
ON CONFLICT DO NOTHING;

-- Electronics: CD=0%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.00, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo electronics rate (CD 0%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '8517.%' OR hs_code LIKE '8471.%' OR hs_code LIKE '8528.%' OR hs_code LIKE '8525.%'
ON CONFLICT DO NOTHING;

-- Machinery: CD=7%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.07, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo machinery rate (CD 7%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '8408.%' OR hs_code LIKE '8414.%' OR hs_code LIKE '8418.%' OR hs_code LIKE '8421.%' OR hs_code LIKE '8431.%'
ON CONFLICT DO NOTHING;

-- Food & Agriculture: CD=7%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.07, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo agriculture rate (CD 7%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '1006.%' OR hs_code LIKE '0203.%' OR hs_code LIKE '0207.%' OR hs_code LIKE '0713.%' OR hs_code LIKE '0901.%' OR hs_code LIKE '1701.%' OR hs_code LIKE '1901.%'
ON CONFLICT DO NOTHING;

-- Textiles: CD=15%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.15, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo textile rate (CD 15%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '6109.%' OR hs_code LIKE '6103.%' OR hs_code LIKE '6104.%' OR hs_code LIKE '6203.%' OR hs_code LIKE '6211.%' OR hs_code LIKE '6403.%'
ON CONFLICT DO NOTHING;

-- Beverages: CD=15%, ST=20%, VAT=10%, ET varies
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.15, 0.20, 0.10, 0.0, 0.0, 'XX', 'Demo beverage rate (CD 15%, ST 20%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '2203.%' OR hs_code LIKE '2202.%'
ON CONFLICT DO NOTHING;

-- Alcohol: CD=35%, ST=30%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.35, 0.30, 0.10, 0.0, 0.0, 'XX', 'Demo alcohol rate (CD 35%, ST 30%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '2208.%'
ON CONFLICT DO NOTHING;

-- Metals: CD=7%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.07, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo metal rate (CD 7%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '7204.%' OR hs_code LIKE '7210.%' OR hs_code LIKE '7308.%'
ON CONFLICT DO NOTHING;

-- Plastics: CD=15%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.15, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo plastic rate (CD 15%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '3923.%' OR hs_code LIKE '3926.%'
ON CONFLICT DO NOTHING;

-- Furniture: CD=15%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.15, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo furniture rate (CD 15%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '9403.%' OR hs_code LIKE '9405.%'
ON CONFLICT DO NOTHING;

-- Cosmetics & Pharmaceuticals: CD=0%, ST=0%, VAT=10%
INSERT INTO duty_rates (hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate, origin_country, notes)
SELECT hs_code, description, unit, 0.00, 0.00, 0.10, 0.0, 0.0, 'XX', 'Demo cosmetic/pharma rate (CD 0%, VAT 10%)'
FROM hs_codes WHERE hs_code LIKE '3304.%' OR hs_code LIKE '3004.%'
ON CONFLICT DO NOTHING;

-- Seed preferential agreements with eligible origin countries (reference only — no rates)
-- Each row = one agreement + one eligible origin country.
-- Full membership inferred from official treaty scopes.
INSERT INTO preferential_rates (agreement_code, origin_country, hs_code, name_kh, name_en, valid_from, valid_to) VALUES
-- AJCEP (ASEAN-Japan) — historical, replaced by AJFTA
('AJCEP','KH',NULL,NULL,'ASEAN-JAPAN Compr. Eco. Partnership','2010-01-01','2017-04-07'),
('AJCEP','TH',NULL,NULL,'ASEAN-JAPAN Compr. Eco. Partnership','2010-01-01','2017-04-07'),
('AJCEP','VN',NULL,NULL,'ASEAN-JAPAN Compr. Eco. Partnership','2010-01-01','2017-04-07'),
('AJCEP','JP',NULL,NULL,'ASEAN-JAPAN Compr. Eco. Partnership','2010-01-01','2017-04-07'),
-- CEPT (ASEAN internal) — historical, replaced by ATIGA
('CEPT','KH',NULL,NULL,'Common Effective Preferent. Tariff','2000-01-01','2015-11-05'),
('CEPT','TH',NULL,NULL,'Common Effective Preferent. Tariff','2000-01-01','2015-11-05'),
('CEPT','VN',NULL,NULL,'Common Effective Preferent. Tariff','2000-01-01','2015-11-05'),
-- ATIGA (ASEAN intra-bloc)
('ATIGA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','LA','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','SG','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','MY','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','ID','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','PH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','BN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
('ATIGA','MM','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន','ASEAN Trade In Goods Agreement','2015-11-01',NULL),
-- AHKCFTA (ASEAN + Hong Kong)
('AHKCFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន-ហុងកុង','ASEAN-Hong Kong Free Trade Agreement','2020-11-14',NULL),
('AHKCFTA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន-ហុងកុង','ASEAN-Hong Kong Free Trade Agreement','2020-11-14',NULL),
('AHKCFTA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន-ហុងកុង','ASEAN-Hong Kong Free Trade Agreement','2020-11-14',NULL),
('AHKCFTA','HK','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន-ហុងកុង','ASEAN-Hong Kong Free Trade Agreement','2020-11-14',NULL),
-- ACFTA (ASEAN + China)
('ACFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ចិន','ASEAN-China Free Trade Agreement','2008-09-22',NULL),
('ACFTA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ចិន','ASEAN-China Free Trade Agreement','2008-09-22',NULL),
('ACFTA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ចិន','ASEAN-China Free Trade Agreement','2008-09-22',NULL),
('ACFTA','CN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ចិន','ASEAN-China Free Trade Agreement','2008-09-22',NULL),
-- AJFTA (ASEAN + Japan)
('AJFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ជប៉ុន','ASEAN-Japan Free Trade Agreement','2017-04-07',NULL),
('AJFTA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ជប៉ុន','ASEAN-Japan Free Trade Agreement','2017-04-07',NULL),
('AJFTA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ជប៉ុន','ASEAN-Japan Free Trade Agreement','2017-04-07',NULL),
('AJFTA','JP','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ជប៉ុន','ASEAN-Japan Free Trade Agreement','2017-04-07',NULL),
-- RCEP (ASEAN + CN + JP + KR + AU + NZ + IN)
('RCEP','KH','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','TH','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','VN','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','CN','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','JP','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','KR','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','AU','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','NZ','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
('RCEP','IN','កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ','Regional Comprehensive Economic Partnership Agreement','2021-10-04',NULL),
-- CCFTA (Cambodia-China bilateral)
('CCFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី កម្ពុជា-ចិន','Cambodia-China Free Trade Agreement','2021-10-05',NULL),
('CCFTA','CN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី កម្ពុជា-ចិន','Cambodia-China Free Trade Agreement','2021-10-05',NULL),
-- CKFTA (Cambodia-Korea bilateral)
('CKFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី កម្ពុជា-កូរ៉េ','Cambodia-Korea Free Trade Agreement','2022-01-29',NULL),
('CKFTA','KR','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី កម្ពុជា-កូរ៉េ','Cambodia-Korea Free Trade Agreement','2022-01-29',NULL),
-- AANZFTA (ASEAN + Australia + New Zealand)
('AANZFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន -អូស្រ្តាលី -ណូវ៉ែលហ្សេឡង់','ASEAN-Australia-New Zealand Free Trade Agreement','2010-10-29',NULL),
('AANZFTA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន -អូស្រ្តាលី -ណូវ៉ែលហ្សេឡង់','ASEAN-Australia-New Zealand Free Trade Agreement','2010-10-29',NULL),
('AANZFTA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន -អូស្រ្តាលី -ណូវ៉ែលហ្សេឡង់','ASEAN-Australia-New Zealand Free Trade Agreement','2010-10-29',NULL),
('AANZFTA','AU','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន -អូស្រ្តាលី -ណូវ៉ែលហ្សេឡង់','ASEAN-Australia-New Zealand Free Trade Agreement','2010-10-29',NULL),
('AANZFTA','NZ','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន -អូស្រ្តាលី -ណូវ៉ែលហ្សេឡង់','ASEAN-Australia-New Zealand Free Trade Agreement','2010-10-29',NULL),
-- AKFTA (ASEAN + Korea)
('AKFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-កូរ៉េ','ASEAN-Korea Free Trade Agreement','2007-12-08',NULL),
('AKFTA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-កូរ៉េ','ASEAN-Korea Free Trade Agreement','2007-12-08',NULL),
('AKFTA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-កូរ៉េ','ASEAN-Korea Free Trade Agreement','2007-12-08',NULL),
('AKFTA','KR','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-កូរ៉េ','ASEAN-Korea Free Trade Agreement','2007-12-08',NULL),
-- AIFTA (ASEAN + India)
('AIFTA','KH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ឥណ្ឌា','ASEAN-India Free Trade Agreement','2011-02-09',NULL),
('AIFTA','TH','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ឥណ្ឌា','ASEAN-India Free Trade Agreement','2011-02-09',NULL),
('AIFTA','VN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ឥណ្ឌា','ASEAN-India Free Trade Agreement','2011-02-09',NULL),
('AIFTA','IN','កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ឥណ្ឌា','ASEAN-India Free Trade Agreement','2011-02-09',NULL),
-- KHUSPT (Cambodia-US bilateral)
('KHUSPT','KH','ពន្ធអនុគ្រោះកម្ពុជា-សហរដ្ឋអាម៉េរិក','KH and US Preferential Tariff','2025-08-08',NULL),
('KHUSPT','US','ពន្ធអនុគ្រោះកម្ពុជា-សហរដ្ឋអាម៉េរិក','KH and US Preferential Tariff','2025-08-08',NULL)
ON CONFLICT (agreement_code, origin_country) DO NOTHING;

-- Seed country groups (regions)
INSERT INTO country_groups (type_id, code, name, name_kh, valid_from) VALUES
(2,'EUU','European Union (Exclude UK)','សហភាពអឺរ៉ុប (មិនរាប់អង់គ្លេស)','2024-01-11'),
(3,'EUR','Europe','អីរ៉ុប','2021-05-26'),
(3,'ASI','Asia','អាស៊ី','2021-05-26'),
(3,'AUS','Australia','អូស្រា្តលី','2021-05-26'),
(3,'ATC','Antarctica','អង់តាកទិក','2021-05-26'),
(3,'AFI','Africa','អាហ្រ្វិក','2021-05-26'),
(3,'NAM','North America','អាមេរិកខាងជើង','2022-03-18'),
(3,'SAM','South America','អាមេរិកខាងត្បូង','2022-03-18'),
(2,'ASE','ASEAN','អាស៊ាន','2021-05-26'),
(2,'CHN','China','ចិន','2022-03-18')
ON CONFLICT (code) DO NOTHING;

-- Seed countries by regions (abbreviated — full data loaded via CSV import)
INSERT INTO countries_by_regions (country_code, region_code, region_desc, valid_from) VALUES
('MY','ASE','ASEAN','2000-01-01'),('ID','ASE','ASEAN','2000-01-01'),('LA','ASE','ASEAN','2000-01-01'),
('VN','ASE','ASEAN','2000-01-01'),('SG','ASE','ASEAN','2000-01-01'),('PH','ASE','ASEAN','2000-01-01'),
('TH','ASE','ASEAN','2000-01-01'),('MM','ASE','ASEAN','2000-01-01'),('BN','ASE','ASEAN','2000-01-01'),
('KH','ASI','ASIA','2000-01-01'),('CN','ASI','ASIA','2000-01-01'),('JP','ASI','ASIA','2000-01-01'),
('KR','ASI','ASIA','2000-01-01'),('IN','ASI','ASIA','2000-01-01'),('US','NAM','NORTH AMERICA','2000-01-01'),
('CA','NAM','NORTH AMERICA','2000-01-01'),('MX','NAM','NORTH AMERICA','2000-01-01'),('GB','EUR','EUROPE','2000-01-01'),
('DE','EUR','EUROPE','2000-01-01'),('FR','EUR','EUROPE','2000-01-01'),('IT','EUR','EUROPE','2000-01-01'),
('ES','EUR','EUROPE','2000-01-01'),('NL','EUR','EUROPE','2000-01-01'),('BE','EUR','EUROPE','2000-01-01'),
('PL','EUR','EUROPE','2000-01-01'),('SE','EUR','EUROPE','2000-01-01'),('FI','EUR','EUROPE','2000-01-01'),
('AU','AUS','AUSTRALIA','2000-01-01'),('NZ','AUS','AUSTRALIA','2000-01-01'),('FJ','AUS','AUSTRALIA','2000-01-01'),
('ZA','AFI','AFRICA','2000-01-01'),('EG','AFI','AFRICA','2000-01-01'),('NG','AFI','AFRICA','2000-01-01'),
('BR','SAM','SOUTH AMERICA','2000-01-01'),('AR','SAM','SOUTH AMERICA','2000-01-01'),('CL','SAM','SOUTH AMERICA','2000-01-01')
ON CONFLICT (country_code, region_code) DO NOTHING;
"""


def get_connection_params():
    """Return calculator DB connection parameters."""
    return {
        "host": os.getenv("CALCULATOR_DB_HOST", "localhost"),
        "port": int(os.getenv("CALCULATOR_DB_PORT", "5432")),
        "database": os.getenv("CALCULATOR_DB_NAME", "gdce_calculator"),
        "user": os.getenv("CALCULATOR_DB_USER", "calc_app"),
        "password": os.getenv("CALCULATOR_DB_PASSWORD", ""),
    }


def _try_connect_psycopg2(params: dict):
    """Try connecting with given params; fallback to localhost on name-resolution failure."""
    import psycopg2
    try:
        return psycopg2.connect(**params)
    except psycopg2.OperationalError as e:
        err_msg = str(e).lower()
        if "could not translate host name" in err_msg or "name or service not known" in err_msg:
            if params.get("host") != "localhost":
                logger.warning(
                    f"  Host '{params['host']}' unresolvable (are you outside Docker?). "
                    f"Falling back to localhost..."
                )
                params["host"] = "localhost"
                return psycopg2.connect(**params)
        raise


def get_postgres_connection(database="postgres"):
    """Connect to the default 'postgres' database to create new DBs."""
    params = get_connection_params()
    params["database"] = database
    params["connect_timeout"] = 5
    try:
        import psycopg2
        return _try_connect_psycopg2(params)
    except ImportError:
        logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
        raise


def create_calculator_database():
    """Create the gdce_calculator database if it does not exist."""
    params = get_connection_params()
    db_name = params["database"]

    logger.info(f"Ensuring database '{db_name}' exists...")

    conn = get_postgres_connection("postgres")
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cur.fetchone()

    if not exists:
        logger.info(f" Creating database '{db_name}'...")
        # PostgreSQL does not allow CREATE DATABASE inside a transaction block
        cur.execute(f'CREATE DATABASE "{db_name}"')
        logger.info(f" Database '{db_name}' created successfully")
    else:
        logger.info(f" Database '{db_name}' already exists")

    cur.close()
    conn.close()
    return True


def _split_sql(sql_text: str):
    """Split multi-statement SQL string into individual executable statements."""
    statements = []
    for raw in sql_text.split(";"):
        stmt = raw.strip()
        # Skip empty lines and pure comment lines
        if stmt and not stmt.startswith("--"):
            statements.append(stmt + ";")
    return statements


def create_tables_and_seed():
    """Create all tables and seed default data."""
    params = get_connection_params()
    params["connect_timeout"] = 5

    logger.info("Creating tables...")
    try:
        import psycopg2
        conn = _try_connect_psycopg2(params)
        cur = conn.cursor()

        for stmt in _split_sql(SCHEMA_SQL):
            cur.execute(stmt)
        for stmt in _split_sql(SEED_SQL):
            cur.execute(stmt)

        conn.commit()

        # Verify
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT COUNT(*) FROM duty_rates;")
        duty_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM exchange_rates;")
        exchange_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM hs_codes;")
        hs_count = cur.fetchone()[0]

        cur.close()
        conn.close()

        logger.info(f" Tables created: {tables}")
        logger.info(f" duty_rates={duty_count}, exchange_rates={exchange_count}, hs_codes={hs_count}")
        return True

    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        return False


def verify_qdrant_connection():
    """Verify Qdrant connectivity (OPTIONAL — only for semantic search)."""
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.warning(" qdrant-client not installed. Semantic search will be unavailable.")
        return False

    qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))

    logger.info(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port} (optional)...")

    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=5)
        collection_name = "gdce_hs_code"
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if collection_name in collection_names:
            logger.info(f" Qdrant connected — collection '{collection_name}' available")
            return True
        else:
            logger.warning(f" Qdrant collection '{collection_name}' not found")
            return False
    except Exception as e:
        logger.warning(f" Qdrant unavailable: {e}")
        return False


def verify_environment_config():
    """Verify environment configuration."""
    logger.info("Verifying environment configuration...")

    primary_vars = [
        ("CALCULATOR_DB_HOST", "localhost"),
        ("CALCULATOR_DB_PORT", "5432"),
        ("CALCULATOR_DB_NAME", "gdce_calculator"),
        ("CALCULATOR_DB_USER", "calc_app"),
    ]
    for var, default in primary_vars:
        value = os.getenv(var, default)
        if value:
            logger.info(f" {var} = {value}")
        else:
            logger.warning(f"  {var} not set (will use default: {default})")

    optional_vars = ["QDRANT_HOST", "QDRANT_PORT", "RETRIEVAL_SERVICE_URL"]
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            logger.info(f" {var} = {value}")

    return True


def main():
    """Main initialization routine."""
    logger.info("=" * 60)
    logger.info("Calculator Service - Standalone Database Initialization")
    logger.info("=" * 60)

    verify_environment_config()

    # 1. Create calculator PostgreSQL database
    try:
        create_calculator_database()
    except Exception as e:
        logger.error(f"Database creation failed: {e}")
        sys.exit(1)

    # 2. Create tables and seed default data
    if not create_tables_and_seed():
        logger.error("Table creation failed. Calculator may not function correctly.")
        sys.exit(1)

    # 3. Verify Qdrant (OPTIONAL — semantic search only)
    qdrant_ok = verify_qdrant_connection()

    logger.info("=" * 60)
    logger.info(" Calculator database initialization complete")
    logger.info(" Calculator is in STANDALONE mode — all calculations use own DB")
    logger.info("=" * 60)

    if not qdrant_ok:
        logger.warning(" Qdrant unavailable — semantic search disabled")


if __name__ == "__main__":
    main()
