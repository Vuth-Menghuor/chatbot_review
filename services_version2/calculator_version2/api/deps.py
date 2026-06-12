"""
GDCE Calculator Service - FastAPI Dependencies
===============================================
Dependency-injection providers for use with FastAPI's Depends() system.

Exported for use with @router.post(...) and @router.get(...) decorators.
"""

from __future__ import annotations

import json
import logging
from typing import Generator
from pathlib import Path

from fastapi import Depends

from ..config import get_settings
from ..core.models import (  # noqa: F401
    CalculationRequest,
    CalculationResult,
    TaxLineItem,
    TaxReference,
)
from ..infrastructure.unified_database import UnifiedDatabase

logger = logging.getLogger(__name__)

# Lazy global database instance (created once, reused)
_db_instance: UnifiedDatabase | None = None
_calculator_config: dict | None = None


def load_calculator_config() -> dict:
    """Load all 5 JSON configuration files from local configs/ directory."""
    global _calculator_config
    
    if _calculator_config is not None:
        return _calculator_config
    
    # Self-contained: load from calculator_version2/configs/ (local to this service)
    config_dir = Path(__file__).parent.parent / "configs"
    
    try:
        _calculator_config = {
            "request_schema": _load_json(config_dir / "calculate_import_taxes.schema.json"),
            "exchange_policy": _load_json(config_dir / "exchange_rate_policy.json"),
            "formula_registry": _load_json(config_dir / "formula_registry.json"),
            "rounding_rules": _load_json(config_dir / "rounding_rules.json"),
            "calculator_rules": _load_json(config_dir / "calculator_config.json"),
        }
        logger.info(" Loaded all 5 calculator configuration files (self-contained)")
        return _calculator_config
    except Exception as e:
        logger.warning(f"  Failed to load config files: {e}")
        return {}


def _load_json(file_path: Path) -> dict:
    """Load JSON configuration file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_db() -> Generator[UnifiedDatabase, None, None]:
    """
    Dependency provider: get initialized unified database connection.
    
    Uses hierarchical fallback:
    - Primary: Qdrant for duty rates, PostgreSQL for exchange rates
    - Fallback: CSV for both
    - Final fallback: Environment variables for rates
    
    Usage in route handlers:
        @router.post("/calculate")
        async def calculate(..., db=Depends(get_db)):
            ...
    """
    global _db_instance
    if _db_instance is None:
        logger.info("Initializing UnifiedDatabase...")
        _db_instance = UnifiedDatabase(
            enable_qdrant=True,
            enable_postgres=True,
            enable_csv=True
        )
        logger.info(" UnifiedDatabase initialized")
    try:
        yield _db_instance
    finally:
        # Cleanup handled by adapters
        pass


def get_calculator_config() -> dict:
    """Dependency provider: get calculator configuration"""
    return load_calculator_config()


def get_settings_dep():
    """Dependency provider: get cached settings."""
    return get_settings()


__all__ = [
    "get_db",
    "get_settings_dep",
    # Re-export Pydantic models for use in routes
    "CalculationRequest",
    "CalculationResult",
    "TaxLineItem",
    "TaxReference",
]
