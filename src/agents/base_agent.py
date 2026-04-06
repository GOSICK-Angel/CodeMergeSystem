import logging
import time
from abc import ABC, abstractmethod
from typing import Any
import asyncio
from pydantic import BaseModel
from src.models.config import AgentLLMConfig
from src.models.message import AgentType, AgentMessage
from src.models.state import MergeState
from src.llm.client import LLMClient, LLMClientFactory, ParseError
from src.tools.trace_logger import TraceLogger


class BaseAgent(ABC):
    agent_type: AgentType

    def __init__(self, llm_config: AgentLLMConfig):
        self.llm_config = llm_config
        self.llm: LLMClient = LLMClientFactory.create(llm_config)
        self.logger = logging.getLogger(f"agent.{self.agent_type.value}")
        self._trace_logger: TraceLogger | None = None

    def set_trace_logger(self, trace_logger: TraceLogger) -> None:
        self._trace_logger = trace_logger

    @abstractmethod
    async def run(self, state: Any) -> AgentMessage:
        pass

    @abstractmethod
    def can_handle(self, state: MergeState) -> bool:
        pass

    async def _call_llm_with_retry(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        schema: type[BaseModel] | None = None,
        max_retries: int | None = None,
    ) -> str | BaseModel:
        retries = (
            max_retries if max_retries is not None else self.llm_config.max_retries
        )
        last_error: Exception | None = None

        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        prompt_preview = messages[-1].get("content", "")[:300] if messages else ""
        self.logger.info(
            "LLM call: model=%s, provider=%s, prompt_chars=%d, max_tokens=%d",
            self.llm_config.model,
            self.llm_config.provider,
            prompt_chars,
            self.llm_config.max_tokens,
        )

        for attempt in range(retries):
            t0 = time.monotonic()
            try:
                llm_result: str | BaseModel
                if schema is not None:
                    llm_result = await self.llm.complete_structured(
                        messages, schema, system=system
                    )
                else:
                    llm_result = await self.llm.complete(messages, system=system)
                elapsed = time.monotonic() - t0
                resp_str = str(llm_result)
                resp_len = len(resp_str)
                self.logger.info(
                    "LLM response: attempt=%d/%d, elapsed=%.1fs, response_chars=%d",
                    attempt + 1,
                    retries,
                    elapsed,
                    resp_len,
                )
                if self._trace_logger:
                    self._trace_logger.record(
                        agent=self.agent_type.value,
                        model=self.llm_config.model,
                        provider=self.llm_config.provider,
                        prompt_chars=prompt_chars,
                        response_chars=resp_len,
                        elapsed_seconds=elapsed,
                        attempt=attempt + 1,
                        max_attempts=retries,
                        success=True,
                        prompt_preview=prompt_preview,
                        response_preview=resp_str[:300],
                    )
                return llm_result
            except ParseError as e:
                last_error = e
                elapsed = time.monotonic() - t0
                self.logger.warning(
                    "Parse error on attempt %d/%d (%.1fs): %s",
                    attempt + 1,
                    retries,
                    elapsed,
                    e,
                )
                if self._trace_logger:
                    self._trace_logger.record(
                        agent=self.agent_type.value,
                        model=self.llm_config.model,
                        provider=self.llm_config.provider,
                        prompt_chars=prompt_chars,
                        response_chars=0,
                        elapsed_seconds=elapsed,
                        attempt=attempt + 1,
                        max_attempts=retries,
                        success=False,
                        error=str(e)[:200],
                        prompt_preview=prompt_preview,
                    )
                if attempt + 1 < retries:
                    await asyncio.sleep(2**attempt)
            except Exception as e:
                last_error = e
                elapsed = time.monotonic() - t0
                self.logger.warning(
                    "LLM error on attempt %d/%d (%.1fs): %s",
                    attempt + 1,
                    retries,
                    elapsed,
                    e,
                )
                if self._trace_logger:
                    self._trace_logger.record(
                        agent=self.agent_type.value,
                        model=self.llm_config.model,
                        provider=self.llm_config.provider,
                        prompt_chars=prompt_chars,
                        response_chars=0,
                        elapsed_seconds=elapsed,
                        attempt=attempt + 1,
                        max_attempts=retries,
                        success=False,
                        error=str(e)[:200],
                        prompt_preview=prompt_preview,
                    )
                if attempt + 1 < retries:
                    await asyncio.sleep(2**attempt)

        raise RuntimeError(
            f"LLM call failed after {retries} attempts: {last_error}"
        ) from last_error
