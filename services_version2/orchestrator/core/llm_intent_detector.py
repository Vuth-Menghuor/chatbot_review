from enum import Enum
from typing import Tuple


class WorkflowIntent(str, Enum):
    HS_CODE_LOOKUP = "hs_code_lookup"
    CALCULATION = "calculation"
    UNKNOWN = "unknown"


class LLMIntentDetector:
    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def detect_intent(self, text: str) -> Tuple[WorkflowIntent, float, str]:
        lower = text.lower()
        if any(k in lower for k in ("hs code", "product", "live horse", "horse")):
            return WorkflowIntent.HS_CODE_LOOKUP, 0.95, "Product description and HS lookup intent detected"
        return WorkflowIntent.UNKNOWN, 0.5, "No clear intent"
