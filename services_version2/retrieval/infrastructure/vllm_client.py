# vLLM client migrated from the old retrieval service
import logging
import os
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

class RemoteLLMClient:
    """
    Client for remote vLLM OpenAI-compatible API
    vLLM endpoint exposes OpenAI-compatible chat completions API
    Typically runs on remote GPU instance at {VLLM_HOST}:{VLLM_PORT}
    """
    def __init__(
        self,
        host: str = os.getenv("VLLM_HOST"),
        port: int = int(os.getenv("VLLM_PORT")),
        model_name: str = os.getenv("VLLM_MODEL_NAME"),
        timeout: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.model_name = model_name
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}/v1"
        self.client = httpx.Client(timeout=timeout)
        logger.info(
            f"RemoteLLMClient initialized: {self.base_url}, model={model_name}"
        )

    def health(self) -> dict:
        """Check if vLLM service is accessible"""
        try:
            resp = self.client.get(f"{self.base_url}/models")
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "host": self.host,
                    "port": self.port,
                    "url": self.base_url,
                }
            else:
                return {
                    "ok": False,
                    "error": f"Status {resp.status_code}",
                    "url": self.base_url,
                }
        except Exception as exc:
            logger.exception("Health check failed: %s", exc)
            return {"ok": False, "error": str(exc), "url": self.base_url}

    def generate_answer(
        self,
        query: str,
        context_snippets: list[str],
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> str:
        """
        Generate an answer using vLLM based on query and retrieved context
        Args:
            query: Original user question
            context_snippets: List of relevant document snippets
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum length of generated answer
        Returns:
            Generated answer text
        """
        prompt = self._build_prompt(query, context_snippets)
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a helpful customs assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = self.client.post(f"{self.base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.error(f"vLLM answer generation failed: {exc}")
            return "[Error: Unable to generate answer]"

    def _build_prompt(self, query: str, context_snippets: list[str]) -> str:
        context = "\n\n".join(context_snippets)
        return f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
