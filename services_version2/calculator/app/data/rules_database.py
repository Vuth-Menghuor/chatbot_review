"""
GDCE Calculator Service - Rules Database Adapter
==================================================
Database adapter for reading/writing dynamic rules from PostgreSQL.
Connects to the calculator's own database (gdce_calculator).

Version: 1.0
Created: 2026-05-04
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try importing psycopg2 — graceful degradation if unavailable
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    logger.warning("psycopg2 not available — rules DB adapter will be disabled")


class RulesDatabaseAdapter:
    """
    PostgreSQL adapter for dynamic rules CRUD.
    
    Tables accessed:
      - formulas
      - rounding_rules
      - policies
      - exemptions
      - rules_audit_log
    """

    def __init__(self):
        if not HAS_PSYCOPG2:
            raise RuntimeError("psycopg2 is required for RulesDatabaseAdapter")

        self.conn_params = {
            "host": os.getenv("CALCULATOR_DB_HOST") or os.getenv("POSTGRES_HOST", os.getenv("PG_HOST", "localhost")),
            "port": int(os.getenv("CALCULATOR_DB_PORT") or os.getenv("POSTGRES_PORT", os.getenv("PG_PORT", "5432"))),
            "dbname": os.getenv("CALCULATOR_DB_NAME") or os.getenv("POSTGRES_DB", os.getenv("PG_DATABASE", "gdce_calculator")),
            "user": os.getenv("CALCULATOR_DB_USER") or os.getenv("POSTGRES_USER", os.getenv("PG_USER", "postgres")),
            "password": os.getenv("CALCULATOR_DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD", os.getenv("PG_PASSWORD", "")),
        }
        # Validate connection on init
        try:
            conn = self._get_connection()
            conn.close()
            logger.info(" Rules DB adapter connected to PostgreSQL")
        except Exception as e:
            logger.warning(f"  Rules DB adapter connection test failed: {e}")
            raise

    def _get_connection(self):
        return psycopg2.connect(**self.conn_params)

    # ------------------------------------------------------------------
    # FORMULAS
    # ------------------------------------------------------------------

    def get_active_formulas(self) -> List[Dict[str, Any]]:
        """Get all active formulas."""
        sql = """
            SELECT formula_id, formula_name, formula_type, expression,
                   description, variables, version, effective_date, end_date, is_active
            FROM formulas
            WHERE is_active = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
            ORDER BY formula_type, version DESC
        """
        return self._query(sql)

    def get_formula(self, formula_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific formula by ID."""
        sql = """
            SELECT formula_id, formula_name, formula_type, expression,
                   description, variables, version, effective_date, end_date, is_active
            FROM formulas WHERE formula_id = %s
        """
        rows = self._query(sql, (formula_id,))
        return rows[0] if rows else None

    def upsert_formula(self, data: Dict[str, Any], changed_by: str = "admin") -> None:
        """Insert or update a formula."""
        variables_json = json.dumps(data.get("variables", []))
        sql = """
            INSERT INTO formulas (formula_id, formula_name, formula_type, expression,
                                  description, variables, version, effective_date, end_date, is_active)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            ON CONFLICT (formula_id) DO UPDATE SET
                formula_name = EXCLUDED.formula_name,
                formula_type = EXCLUDED.formula_type,
                expression = EXCLUDED.expression,
                description = EXCLUDED.description,
                variables = EXCLUDED.variables,
                version = formulas.version + 1,
                effective_date = EXCLUDED.effective_date,
                end_date = EXCLUDED.end_date,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """
        params = (
            data["formula_id"], data["formula_name"], data["formula_type"],
            data["expression"], data.get("description", ""),
            variables_json, data.get("version", 1),
            data.get("effective_date"), data.get("end_date"),
            data.get("is_active", True),
        )

        # Audit: get old value first
        old = self.get_formula(data["formula_id"])
        self._execute(sql, params)
        self._log_audit("formulas", data["formula_id"],
                        "UPDATE" if old else "CREATE", old, data, changed_by)

    def deactivate_formula(self, formula_id: str, changed_by: str = "admin") -> bool:
        """Deactivate a formula (soft delete)."""
        old = self.get_formula(formula_id)
        if not old:
            return False
        sql = "UPDATE formulas SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE formula_id = %s"
        self._execute(sql, (formula_id,))
        new_data = {**old, "is_active": False}
        self._log_audit("formulas", formula_id, "DEACTIVATE", old, new_data, changed_by)
        return True

    # ------------------------------------------------------------------
    # ROUNDING RULES
    # ------------------------------------------------------------------

    def get_active_rounding_rules(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT rule_id, rule_name, applies_to, rounding_method,
                   precision, priority, description
            FROM rounding_rules
            WHERE is_active = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
        """
        return self._query(sql)

    def upsert_rounding_rule(self, data: Dict[str, Any], changed_by: str = "admin") -> None:
        applies_to = data.get("applies_to", [])
        if isinstance(applies_to, list):
            applies_to_pg = applies_to  # psycopg2 handles list → array
        else:
            applies_to_pg = [applies_to]

        sql = """
            INSERT INTO rounding_rules (rule_id, rule_name, applies_to, rounding_method,
                                        precision, priority, description, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rule_id) DO UPDATE SET
                rule_name = EXCLUDED.rule_name,
                applies_to = EXCLUDED.applies_to,
                rounding_method = EXCLUDED.rounding_method,
                precision = EXCLUDED.precision,
                priority = EXCLUDED.priority,
                description = EXCLUDED.description,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """
        params = (
            data["rule_id"], data["rule_name"], applies_to_pg,
            data["rounding_method"], data.get("precision", 100),
            data.get("priority", "HIGH"), data.get("description", ""),
            data.get("is_active", True),
        )
        self._execute(sql, params)
        self._log_audit("rounding_rules", data["rule_id"], "UPSERT", None, data, changed_by)

    # ------------------------------------------------------------------
    # POLICIES
    # ------------------------------------------------------------------

    def get_active_policies(self, policy_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if policy_type:
            sql = """
                SELECT policy_id, policy_name, policy_type, conditions, actions,
                       priority, description, is_active
                FROM policies
                WHERE is_active = TRUE AND policy_type = %s
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                ORDER BY priority ASC
            """
            return self._query(sql, (policy_type,))
        else:
            sql = """
                SELECT policy_id, policy_name, policy_type, conditions, actions,
                       priority, description, is_active
                FROM policies
                WHERE is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                ORDER BY priority ASC
            """
            return self._query(sql)

    def upsert_policy(self, data: Dict[str, Any], changed_by: str = "admin") -> None:
        conditions_json = json.dumps(data.get("conditions", {}))
        actions_json = json.dumps(data.get("actions", {}))
        sql = """
            INSERT INTO policies (policy_id, policy_name, policy_type, conditions,
                                  actions, priority, description, is_active)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
            ON CONFLICT (policy_id) DO UPDATE SET
                policy_name = EXCLUDED.policy_name,
                policy_type = EXCLUDED.policy_type,
                conditions = EXCLUDED.conditions,
                actions = EXCLUDED.actions,
                priority = EXCLUDED.priority,
                description = EXCLUDED.description,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """
        params = (
            data["policy_id"], data["policy_name"], data["policy_type"],
            conditions_json, actions_json, data.get("priority", 100),
            data.get("description", ""), data.get("is_active", True),
        )
        self._execute(sql, params)
        self._log_audit("policies", data["policy_id"], "UPSERT", None, data, changed_by)

    # ------------------------------------------------------------------
    # EXEMPTIONS
    # ------------------------------------------------------------------

    def get_active_exemptions(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT
                exemption_code,
                regime_name,
                exemption_type,
                cd_exempt,
                st_exempt,
                vat_exempt,
                et_exempt,
                cd_reduction_pct,
                vat_reduction_pct,
                conditions,
                is_active
            FROM exemptions
            WHERE is_active = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
        """
        return self._query(sql)

    def upsert_exemption(self, data: Dict[str, Any], changed_by: str = "admin") -> None:
        sql = """
            INSERT INTO exemptions (
                exemption_code, regime_name, exemption_type,
                cd_exempt, st_exempt, vat_exempt, et_exempt,
                cd_reduction_pct, vat_reduction_pct, conditions,
                is_active, effective_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT (exemption_code) DO UPDATE SET
                regime_name = EXCLUDED.regime_name,
                exemption_type = EXCLUDED.exemption_type,
                cd_exempt = EXCLUDED.cd_exempt,
                st_exempt = EXCLUDED.st_exempt,
                vat_exempt = EXCLUDED.vat_exempt,
                et_exempt = EXCLUDED.et_exempt,
                cd_reduction_pct = EXCLUDED.cd_reduction_pct,
                vat_reduction_pct = EXCLUDED.vat_reduction_pct,
                conditions = EXCLUDED.conditions,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """

        params = (
            data["exemption_code"],
            data["regime_name"],
            data["exemption_type"],
            data.get("cd_exempt", False),
            data.get("st_exempt", False),
            data.get("vat_exempt", False),
            data.get("et_exempt", False),
            data.get("cd_reduction_pct", 0),
            data.get("vat_reduction_pct", 0),
            data.get("conditions", ""),
            data.get("is_active", True),
        )
        try:
            self._execute(sql, params)
        except Exception as e:
            logger.error(f"Failed to upsert exemption: {e}")
            raise
        self._log_audit("exemptions", data["exemption_code"], "UPSERT", None, data, changed_by)

    # ------------------------------------------------------------------
    # AUDIT LOG
    # ------------------------------------------------------------------

    def get_audit_log(
        self, table_name: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        if table_name:
            sql = """
                SELECT id, table_name, record_id, action, old_value, new_value,
                       changed_by, changed_at, reason
                FROM rules_audit_log WHERE table_name = %s
                ORDER BY changed_at DESC LIMIT %s
            """
            return self._query(sql, (table_name, limit))
        sql = """
            SELECT id, table_name, record_id, action, old_value, new_value,
                   changed_by, changed_at, reason
            FROM rules_audit_log ORDER BY changed_at DESC LIMIT %s
        """
        return self._query(sql, (limit,))

    def _log_audit(
        self, table_name: str, record_id: str, action: str,
        old_value: Any, new_value: Any, changed_by: str,
        reason: str = "",
    ) -> None:
        try:
            sql = """
                INSERT INTO rules_audit_log (table_name, record_id, action,
                                             old_value, new_value, changed_by, reason)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """
            old_json = json.dumps(old_value) if old_value else None
            new_json = json.dumps(new_value, default=str) if new_value else "{}"
            self._execute(sql, (table_name, record_id, action,
                                old_json, new_json, changed_by, reason))
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    # ------------------------------------------------------------------
    # HEALTH CHECK
    # ------------------------------------------------------------------

    def check_health(self) -> Dict[str, Any]:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            return {"ok": True, "message": "Rules DB reachable"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query(self, sql: str, params=None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
            cur.close()
            return rows
        finally:
            conn.close()

    def _execute(self, sql: str, params=None) -> None:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            cur.close()
        finally:
            conn.close()
