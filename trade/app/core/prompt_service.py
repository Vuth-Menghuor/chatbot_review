"""Dynamic Prompt Manager for trade service.

Loads prompts dynamically from YAML configuration files.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PromptConfig:
    """Represents a loaded prompt configuration."""
    name: str
    version: str
    description: str
    provider: str
    system_prompt: str
    output_schema: Dict[str, Any]


class DynamicPromptManager:
    """Loads and manages prompt configurations from YAML files with dynamic reloading support."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern so prompt configurations are shared/loaded once."""
        if not cls._instance:
            cls._instance = super(DynamicPromptManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, prompts_dir: Optional[Path] = None) -> None:
        if getattr(self, "_initialized", False):
            return

        if prompts_dir is None:
            prompts_dir = Path(__file__).resolve().parent.parent.parent / "prompts"

        self.prompts_dir = prompts_dir
        self.prompts: Dict[str, PromptConfig] = {}
        self.file_mtimes: Dict[str, float] = {}

        self._load_prompts()
        self._initialized = True

    def _load_prompts(self) -> None:
        """Scan and load all .yaml and .yml files from prompts directory."""
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            return

        for ext in ("*.yaml", "*.yml"):
            for yaml_file in self.prompts_dir.glob(ext):
                self._load_single_file(yaml_file)

    def _load_single_file(self, file_path: Path) -> None:
        """Parse prompt configuration from a single YAML file."""
        try:
            mtime = os.path.getmtime(file_path)
            self.file_mtimes[str(file_path)] = mtime

            with open(file_path, "r", encoding="utf-8") as f:
                documents = yaml.safe_load_all(f)
                for doc in documents:
                    if not doc or not isinstance(doc, dict):
                        continue

                    if "name" in doc and "system_prompt" in doc:
                        prompt = PromptConfig(
                            name=doc.get("name"),
                            version=doc.get("version", "1.0"),
                            description=doc.get("description", ""),
                            provider=doc.get("provider", "gemini"),
                            system_prompt=doc.get("system_prompt"),
                            output_schema=doc.get("output_schema", {}),
                        )
                        self.prompts[prompt.name] = prompt
                        logger.info(f"Loaded prompt configuration: '{prompt.name}' (v{prompt.version})")
        except Exception as e:
            logger.error(f"Failed to load prompt file {file_path}: {e}")

    def _check_reload(self) -> None:
        """Reload prompt templates if their files have been modified since last read."""
        for ext in ("*.yaml", "*.yml"):
            for yaml_file in self.prompts_dir.glob(ext):
                file_path_str = str(yaml_file)
                if not yaml_file.exists():
                    continue
                try:
                    current_mtime = os.path.getmtime(yaml_file)
                    last_mtime = self.file_mtimes.get(file_path_str)
                    if last_mtime is None or current_mtime > last_mtime:
                        logger.info(f"Prompt template file modified, reloading: {yaml_file.name}")
                        self._load_single_file(yaml_file)
                except Exception as e:
                    logger.debug(f"Error checking modification time for {yaml_file}: {e}")

    def get_system_prompt(self, prompt_name: str) -> str:
        """Retrieve system prompt by name, hot-reloading if the source file was modified.

        Args:
            prompt_name: Canonical name of the prompt template.

        Returns:
            The raw system prompt template text.
        """
        self._check_reload()
        prompt = self.prompts.get(prompt_name)
        if prompt is None:
            logger.warning(f"System prompt '{prompt_name}' not found.")
            return ""
        return prompt.system_prompt
