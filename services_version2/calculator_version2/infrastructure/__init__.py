"""
GDCE Calculator Service - Infrastructure Package
=================================================
I/O adapters: database access, external service clients, data loaders.

Exports:
    CSVDatabase: Default database implementation (CSV-backed)
"""

from .csv_database import CSVDatabase  # noqa: F401

__all__ = ["CSVDatabase"]
