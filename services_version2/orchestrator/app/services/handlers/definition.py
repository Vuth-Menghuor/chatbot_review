from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

from prompts.dynamic_prompt_manager import DynamicPromptManager
from ...infrastructure.cache_service import get_cache_service

if TYPE_CHECKING:
    from ..coordinator import ServiceCoordinator
    from ..workflow import WorkflowContext

logger = logging.getLogger(__name__)
_prompt_manager = DynamicPromptManager()


class DefinitionHandler:
    @staticmethod
    async def generate_parametric_definition_answer(coordinator: ServiceCoordinator, query: str) -> str:
        """Generates a direct LLM parametric answer for general terminology/definition queries when RAG has no document info."""
        if coordinator.llm_service and coordinator.llm_service.is_available():
            prompt = _prompt_manager.render(
                "generate_parametric_definition",
                query=query,
            )
            try:
                provider = coordinator.llm_service.router.providers.get("gemini")
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
                logger.warning(f"LLM parametric definition generation failed: {e}")
        return f"I could not find an official document reference for '{query}'. Please specify if you are looking for customs procedures, tariff classifications, or duty calculations."

    @staticmethod
    async def handle(coordinator: ServiceCoordinator, context: WorkflowContext) -> None:
        try:
            from ..workflow import WorkflowStatus
            if not coordinator.general_client:
                context.add_error("General service not configured")
                context.status = WorkflowStatus.FAILED
                return
            
            timeout_sec = min(
                coordinator.timeout_config.get_intent_timeout(context.intent),
                coordinator.timeout_config.get_service_timeout("general")
            )
            cache = get_cache_service()
            intent_key = "general"
            service_query = coordinator._get_service_query(context)
            cached_result = cache.get_cached_response(service_query, intent=intent_key)
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return
            
            async def run_call():
                return await asyncio.wait_for(
                    coordinator.general_client.definition(
                        query=service_query,
                        top_k=5,
                        generate_answer=True,
                        session_id=context.session_id
                    ),
                    timeout=timeout_sec
                )

            result = await coordinator._execute_service_call(
                context=context,
                service_name="general_definition",
                client_call_fn=run_call,
                request_payload={"query": service_query, "top_k": 5, "generate_answer": True, "session_id": context.session_id}
            )

            # Fallback check: If RAG returned no document info, use direct LLM parametric knowledge
            if result and isinstance(result, dict):
                ans_text = result.get("final_answer") or result.get("answer") or ""
                if coordinator._is_rag_no_info_response(ans_text, result):
                    logger.info(f"[{context.request_id}] RAG returned no document info for query '{service_query}'. Invoking LLM parametric fallback.")
                    parametric_ans = await DefinitionHandler.generate_parametric_definition_answer(coordinator, service_query)
                    result["answer"] = parametric_ans
                    result["final_answer"] = parametric_ans
                    result["source"] = "llm_parametric_knowledge"

            cache.cache_response(question=service_query, response=result, intent=intent_key, ttl_seconds=48*3600, source="general")
            context.set_result("retrieval", result)
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            context.add_error(f"General service error: {str(e)}")
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.FAILED
