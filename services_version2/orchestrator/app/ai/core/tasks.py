"""LLM task definitions and prompt templates."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class LLMTask(str, Enum):
    INTENT_CLASSIFICATION = "intent_classification"
    CURRENCY_DETECTION = "currency_detection"
    REWRITE = "rewrite"
    SUMMARIZATION = "summarization"
    HS_SELECTION = "hs_selection"
    TRANSLATION_TO_EN = "translation_to_en"
    TRANSLATION_TO_KM = "translation_to_km"



@dataclass
class LLMTaskRequest:
    """Normalized request passed through the abstraction layer."""

    task: LLMTask
    prompt: str
    input_text: str
    context: Dict[str, Any] = field(default_factory=dict)
