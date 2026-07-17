"""
Dynamic Prompt Manager for orchestrator service.
 
Loads prompts from YAML files and provides a unified interface
for the validator service and other components.
 
Usage:
    manager = DynamicPromptManager()
    system_prompt = manager.get_system_prompt("query_validity_unified")
    schema = manager.get_schema("query_validity_unified")
"""
 
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

@dataclass
class SystemPromptSection:
    """Represents a dynamically resolved segment of the system prompt."""
    name: str
    compute: Callable[[], str]
    cache_break: bool = False

@dataclass
class PromptConfig:
    """Represent a single prompt configuration"""
    name : str
    version : str
    description : str
    provider : str
    system_prompt : str
    output_schema : Dict[str, Any]
    confidence_threshold : Optional[float] = None
    fallback_method : Optional[str] = None 

class DynamicPromptManager:
    """"Loads and Manage prompt configuration from YAML files."""
    def __init__ (self, prompts_dir : Optional[Path] = None ):
        """
        Initialize the prompt manager and loads prompt configurations.
        
        Args:
            prompts_dir : Path to the directory containing prompt YAML files.
                          If None, uses default directory where this file resides.
        """ 
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent
        
        self.prompts_dir = prompts_dir 
        self.prompts: Dict[str, PromptConfig] = {}
        self.fallback_schema : Dict[str, Any] = {}
        self.orchestrator_pipeline: Dict[str, Any] = {}
        
        self.section_registry: Dict[str, SystemPromptSection] = {}
        self.section_cache: Dict[str, str] = {}
        self._register_default_sections()

        self._load_prompts()

    def register_section(self, name: str, compute_fn: Callable[[], str], cache_break: bool = False) -> None:
        """Register a dynamic context provider section (e.g. system time)."""
        self.section_registry[name] = SystemPromptSection(name, compute_fn, cache_break)

    def _register_default_sections(self) -> None:
        """Register default volatile and memoized sections."""
        import datetime
        import os

        # Volatile Section: Changes on every turn
        self.register_section(
            name="system_time",
            compute_fn=lambda: f"Current Local Time: {datetime.datetime.now().isoformat()}",
            cache_break=True
        )

        # Memoized Section: Remains static during the session
        self.register_section(
            name="env_info",
            compute_fn=lambda: f"Workspace Directory: {os.getcwd()}\nOS: {os.name}",
            cache_break=False
        )


    
    def _load_prompts(self) -> None:
        """Load prompt configurations from YAML files in the prompts directory."""
        if not self.prompts_dir.exists():
            import logging 
            logging.warning(f"Prompts directory not found: {self.prompts_dir}")
            return 

        # Load all .yaml and .yml files recursively
        for ext in ("*.yaml", "*.yml"):
            for yaml_file in self.prompts_dir.rglob(ext):
                try:
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        # Support multi-document YAML files
                        documents = yaml.safe_load_all(f)
                        for doc in documents:
                            if doc:
                                self._parse_prompt_document(doc)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to load prompt file {yaml_file}: {e}")

    def _parse_prompt_document(self, doc: Any) -> None:
        """
        Parse a YAML document that may contain:
        - A single prompt dict
        - A list of prompt dicts
        - Multiple prompts nested under keys
        - Fallback schemas and other metadata
        """
        # Handle list of documents
        if isinstance(doc, list):
            for item in doc:
                if isinstance(item, dict):
                    self._parse_prompt_document(item)
            return

        if not isinstance(doc, dict):
            return

        # Handle special sections first
        if "fallback_schema" in doc:
            self.fallback_schema = doc["fallback_schema"]
        
        if "orchestrator_pipeline" in doc:
            self.orchestrator_pipeline = doc["orchestrator_pipeline"]

        # Handle single prompt in document 
        if "name" in doc and "system_prompt" in doc:
            prompt = self._parse_single_prompt(doc)
            if prompt:
                self.prompts[prompt.name] = prompt
            return  # It's a single prompt document, don't check for nested prompts

        # Handle multiple prompts in document (nested under "prompts" key or other keys)
        self._parse_nested_prompts(doc)

    def _parse_nested_prompts(self, doc: Dict[str, Any]) -> None:
        """
        Parse multiple prompts from a document.
        Handles cases like:
          - {prompts: [{...}, {...}]}
          - {prompt1: {...}, prompt2: {...}}
          - {email_classifier: {...}, spam_detector: {...}}
        """
        # Case 1: prompts key with list
        if "prompts" in doc and isinstance(doc["prompts"], list):
            for item in doc["prompts"]:
                if isinstance(item, dict):
                    prompt = self._parse_single_prompt(item)
                    if prompt:
                        self.prompts[prompt.name] = prompt
            return
        
        # Case 2: Each top-level key (except special keys) is a prompt config
        special_keys = {"fallback_schema", "orchestrator_pipeline", "metadata", "version", "config"}
        for key, value in doc.items():
            if key not in special_keys and isinstance(value, dict):
                # Check if this value looks like a prompt config
                if "system_prompt" in value:
                    prompt = self._parse_single_prompt(value)
                    if prompt:
                        self.prompts[prompt.name] = prompt

    def _parse_single_prompt(self, doc: Dict[str, Any]) -> Optional[PromptConfig]:
        """Parse a single prompt document."""
        try:
            return PromptConfig(
                name=doc.get("name"),
                version=doc.get("version", "1.0"),
                description=doc.get("description", ""),
                provider=doc.get("provider"),
                system_prompt=doc.get("system_prompt"),
                output_schema=doc.get("output_schema", {}),
                confidence_threshold=doc.get("confidence_threshold"),
                fallback_method=doc.get("fallback_method")
            )
        except KeyError as e:
            import logging
            logging.error(f"Missing required field {e} in prompt document: {doc}")
            return None

    def get_system_prompt(self, prompt_name: str) -> str:
        """
        Get the system prompt text for a given prompt name.
        
        Args:
            prompt_name: Name of the prompt (e.g., "query_validity_unified")
        
        Returns:
            System prompt string, or empty string if not found
        """
        prompt = self.prompts.get(prompt_name)
        if prompt is None:
            import logging
            logging.warning(f"Prompt not found: {prompt_name}")
            return ""
        return prompt.system_prompt

    def get_split_prompt(self, prompt_name: str, **variables: Any) -> Dict[str, str]:
        """
        Retrieves the system prompt and splits it at the boundary marker if present.
        Resolves dynamic sections and appends them to the dynamic block.
        """
        boundary = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"
        raw_prompt = self.get_system_prompt(prompt_name)
        if not raw_prompt:
            return {"static": "", "dynamic": ""}

        # Render variables if any
        if variables:
            try:
                raw_prompt = raw_prompt.format(**variables)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to render variables in prompt {prompt_name}: {e}"
                )

        if boundary in raw_prompt:
            parts = raw_prompt.split(boundary)
            static_part = parts[0].strip()
            dynamic_part = parts[1].strip()

            # Resolve registered sections
            resolved_sections = []
            for name, sec in self.section_registry.items():
                if not sec.cache_break and name in self.section_cache:
                    val = self.section_cache[name]
                else:
                    try:
                        val = sec.compute()
                        self.section_cache[name] = val
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Error computing section {name}: {e}")
                        val = ""
                if val:
                    resolved_sections.append(val)

            if resolved_sections:
                dynamic_joined = "\n\n".join(resolved_sections)
                if dynamic_part:
                    dynamic_part = f"{dynamic_part}\n\n{dynamic_joined}"
                else:
                    dynamic_part = dynamic_joined

            return {"static": static_part, "dynamic": dynamic_part}

        return {"static": raw_prompt, "dynamic": ""}

    def render(self, prompt_name: str, **variables: Any) -> str:
        """
        Get the system prompt and format/render it with the provided variables.
        
        Args:
            prompt_name: Name of the prompt
            **variables: Keyword arguments to format the prompt string
            
        Returns:
            Formatted prompt string, or empty string if not found
        """
        prompt = self.get_system_prompt(prompt_name)
        if not prompt:
            return ""
        try:
            return prompt.format(**variables)
        except KeyError as e:
            import logging
            logging.warning(f"Missing variable {e} when rendering prompt: {prompt_name}")
            return prompt
        except Exception as e:
            import logging
            logging.error(f"Error rendering prompt {prompt_name}: {e}")
            return prompt

    # Validate Response Against Schema
    def get_schema(self, prompt_name: str) -> Dict[str, Any]:
        """
        Get the output schema for a given prompt.
        
        Args:
            prompt_name: Name of the prompt
        
        Returns:
            Schema dict, or empty dict if not found
        """
        prompt = self.prompts.get(prompt_name)
        if prompt is None:
            return {}
        return prompt.output_schema
    
    def get_prompt_config(self, prompt_name: str) -> Optional[PromptConfig]:
        """
        Get the full prompt configuration.
        
        Args:
            prompt_name: Name of the prompt
        
        Returns:
            PromptConfig object, or None if not found
        """
        return self.prompts.get(prompt_name)
    
    def get_confidence_threshold(self, prompt_name: str) -> float:
        """
        Get the confidence threshold for a prompt.
        
        Args:
            prompt_name: Name of the prompt
        
        Returns:
            Confidence threshold (0.0-1.0), defaults to 0.7
        """
        prompt = self.prompts.get(prompt_name)
        if prompt is None or prompt.confidence_threshold is None:
            return 0.7
        return prompt.confidence_threshold
    
    def get_fallback_method(self, prompt_name: str) -> Optional[str]:
        """
        Get the fallback method name for a prompt.
        
        Args:
            prompt_name: Name of the prompt
        
        Returns:
            Fallback method name (e.g., "regex_injection_patterns"), or None
        """
        prompt = self.prompts.get(prompt_name)
        if prompt is None:
            return None
        return prompt.fallback_method
    
    def get_scope_keywords(self, category: str) -> List[str]:
        """
        Get scope keywords for a specific category.
        
        Args:
            category: Category name (e.g., "hs_code_lookup", "calculation", "trade_query")
        
        Returns:
            List of keywords for that category
        """
        if not self.fallback_schema:
            return []
        
        scope_keywords = self.fallback_schema.get("scope_keywords", {})
        return scope_keywords.get(category, [])

    def get_all_scope_keywords(self) -> Dict[str, List[str]]:
        """Get all scope keywords grouped by category."""
        if not self.fallback_schema:
            return {}
        return self.fallback_schema.get("scope_keywords", {})
    
    def list_prompts(self) -> List[str]:
        """List all loaded prompt names."""
        return list(self.prompts.keys())

    def reload(self) -> None:
        """Reload all prompts from disk (useful for hot-reloading in development)."""
        self.prompts.clear()
        self.fallback_schema.clear()
        self.orchestrator_pipeline.clear()
        self._load_prompts()
    
    def get_summary(self) -> str:
        """Get a summary of loaded prompts and configuration."""
        lines = [
            f"DynamicPromptManager loaded from: {self.prompts_dir}",
            f"Total prompts: {len(self.prompts)}",
            "",
            "Loaded Prompts:",
        ]
        for name in sorted(self.list_prompts()):
            prompt = self.prompts[name]
            lines.append(f"  • {name} (v{prompt.version}) - {prompt.description}")
        
        if self.fallback_schema:
            lines.append("")
            lines.append("Fallback Schema:")
            if "scope_keywords" in self.fallback_schema:
                lines.append(f"  • Scope Keywords: {len(self.fallback_schema['scope_keywords'])} categories")
            if "product_keywords" in self.fallback_schema:
                lines.append(f"  • Product Keywords: {len(self.fallback_schema['product_keywords'])} items")
            if "injection_patterns" in self.fallback_schema:
                lines.append(f"  • Injection Patterns: {len(self.fallback_schema['injection_patterns'])} categories")
        
        return "\n".join(lines)