"""Configuration for the orchestrator formatter service."""
from dataclasses import dataclass
from typing import Optional

@dataclass
class FormatterServiceConfig:
    """Configuration for LLM formatter tasks."""
    provider: str = "ollama"
    
    # Ollama configuration (legacy)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_port: int = 11434  # Deprecated, kept for backward compatibility
    ollama_model: str = "mistral"
    
    # Gemini configuration
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    
    timeout: int = 30
    enabled: bool = True
