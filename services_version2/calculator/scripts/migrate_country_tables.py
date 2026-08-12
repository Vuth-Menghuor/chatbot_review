#!/usr/bin/env python3
"""
Migration: Create country_groups and countries_by_regions tables
==================================================================
Run this against your EXISTING database to add missing reference tables.

Usage: python migrate_country_tables.py
"""

import os
import sys
from pathlib import Path

# Load .env from calculator folder
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_CONFIG = {
    "host": os.getenv("CALCULATOR_DB_HOST", "localhost"),
    "port": int(os.getenv("CALCULATOR_DB_PORT", "5432")),
    "database": os.getenv("CALCULATOR_DB_NAME", "gdce_calculator"),
    "user": os.getenv("CALCULATOR_DB_USER", "calc_app"),
    "password": os.getenv("CALCULATOR_DB_PASSWORD", ""),
}

MIGRATION_SQL = """
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

-- Seed countries by regions (abbreviated)
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


def connect_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        sys.exit(1)


def run_migration():
    conn = connect_db()
    cur = conn.cursor()

    print("Creating country_groups table...")
    print("Creating countries_by_regions table...")

    for stmt in [s.strip() for s in MIGRATION_SQL.split(";") if s.strip()]:
        try:
            cur.execute(stmt + ";")
        except psycopg2.Error as e:
            print(f"  Statement failed (may already exist): {e.pgerror.strip() if e.pgerror else e}")

    conn.commit()

    # Verify
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name IN ('country_groups', 'countries_by_regions')
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT COUNT(*) FROM country_groups;")
    cg_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM countries_by_regions;")
    cbr_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"Done. Tables: {tables}")
    print(f"  country_groups rows: {cg_count}")
    print(f"  countries_by_regions rows: {cbr_count}")


if __name__ == "__main__":
    run_migration()
