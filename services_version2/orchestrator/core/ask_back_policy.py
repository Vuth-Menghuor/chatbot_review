"""
core/ask_back_policy.py — backward-compatibility shim.

This module has been superseded by ask_back_service/.
All symbols are re-exported from the new service for zero-breakage imports.
"""

# Re-export the new service so any existing imports keep working
from ..llm_first_layer import get_llm_first_layer_service as get_ask_back_service
from ..ask_back_service import (        # noqa: F401
    AskBackService as AskBackPolicy,
    ClarificationResult,
)

# Convenience alias that legacy callers used
AskBackPolicy = AskBackPolicy
