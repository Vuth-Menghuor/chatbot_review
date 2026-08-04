from __future__ import annotations
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from prompts.dynamic_prompt_manager import DynamicPromptManager

if TYPE_CHECKING:
    from ..coordinator import ServiceCoordinator
    from ..workflow import WorkflowContext

logger = logging.getLogger(__name__)
_prompt_manager = DynamicPromptManager()


async def generate_small_talk_response(query: str, llm_service=None) -> str:
    """
    Generates a polite/friendly response for small talk, chitchat, or out-of-scope queries
    using the LLM, falling back to a default greeting if the LLM is unavailable.
    """
    DEFAULT_FALLBACK = "Hello! I'm here to help you with Cambodia customs and trade questions. How can I assist you today?"
    
    # Call LLM as a general-purpose conversational assistant.
    if llm_service and llm_service.is_available():
        current_datetime = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
        prompt = _prompt_manager.render(
            "generate_small_talk_response",
            query=query,
            current_datetime=current_datetime,
        )
        try:
            provider = llm_service.router.providers.get("gemini")
            if provider and provider.is_available():
                response = await asyncio.to_thread(
                    provider.client.models.generate_content,
                    model=provider.model_name,
                    contents=prompt,
                )
                content = (response.text or "").strip()
                if content:
                    return content
        except Exception as e:
            logger.warning(f"LLM small talk generation failed: {e}")

    return DEFAULT_FALLBACK


class SmallTalkHandler:
    @staticmethod
    async def handle(coordinator: ServiceCoordinator, context: WorkflowContext) -> None:
        logger.info(f"[{context.request_id}] Routing to small talk handler")
        try:
            # Audit and warn if customs keywords are confidently classified as small_talk
            low = (context.question or "").lower()
            customs_keywords = ["duty", "tariff", "hs code", "atiga", "rcep", "import", "export", "calculate", "tax"]
            matched_kws = [kw for kw in customs_keywords if re.search(rf"\b{re.escape(kw)}\b", low)]
            if matched_kws:
                logger.warning(
                    f"[{context.request_id}] [MONITOR] Query with customs keywords {matched_kws} "
                    f"was routed to small_talk: '{context.question}'"
                )

            # Check if already cached in metadata
            small_talk_response = context.metadata.get("small_talk_response")
            if not small_talk_response:
                small_talk_response = await generate_small_talk_response(context.question, coordinator.llm_service)
            
            context.set_result("small_talk", {"answer": small_talk_response})
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            logger.error(f"[{context.request_id}] Small talk handler failed: {e}")
            context.add_error(f"Small talk service error: {str(e)}")
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.FAILED
