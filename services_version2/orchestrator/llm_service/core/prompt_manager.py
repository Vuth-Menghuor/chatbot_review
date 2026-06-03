"""Prompt templates used by the orchestrator LLM abstraction layer."""

from dataclasses import dataclass, field
from typing import Any, Dict

from .tasks import LLMTask


@dataclass
class PromptManager:
    """Central place for task prompt templates."""

    templates: Dict[LLMTask, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.templates:
            self.templates = {
                LLMTask.REWRITE: (
                    "Rewrite the user query with strict fidelity to the original meaning. "
                    "Do not add new information. Do not remove important constraints or parameters. "
                    "Preserve ambiguity when the original query is ambiguous. "
                    "Do not infer missing product details, trade terms, quantities, classifications, or countries beyond what the user explicitly provided."
                    "Keep the rewrite as close to the original query as possible. "
                    "If the query is already clear, return it unchanged. "
                    "Preserve structured values like HS codes, origin country names, cif values, currencies, and dates exactly.\n\n"
                    "User query: {input_text}\n\n"
                    "Return only the rewritten query."
                ),
                LLMTask.SUMMARIZATION: (
                    "Summarize the following content in 3-5 concise bullet points. "
                    "Keep the summary factual and do not add new information.\n\n"
                    "Content: {input_text}"
                ),
                LLMTask.HS_SELECTION: (
                    "Rank the top 3 HS code matches for the query.\n\n"
                    "Rules:\n"
                    "- Use only the provided candidates.\n"
                    "- Do not invent missing product details.\n"
                    "- Keep explanations short and user-friendly.\n\n"
                    "Return ONLY valid JSON using this schema:\n"
                    "{\n"
                    '  \"top_matches\": [\n'
                    "    {\n"
                    '      \"rank\": 1,\n'
                    '      \"hs_code\": \"string\",\n'
                    '      \"description\": \"string\",\n'
                    '      \"confidence\": 0.95,\n'
                    '      \"why_selected\": \"string\"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "Query: {input_text}\n\n"
                    "Candidates:\n{candidates}"
                ),
            }

    def render(self, task: LLMTask, **values: Any) -> str:
        template = self.templates.get(task, "{input_text}")
        return template.format(**values)
