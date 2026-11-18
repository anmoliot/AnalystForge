"""LLM Provider abstraction and implementations.

Supports:
- openai-compatible (Groq, vLLM, OpenAI, Ollama)
- anthropic
- none (explicit disabled state)
- fake (deterministic provider for testing)
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
import structlog

from analystforge.providers.errors import ProviderError, ProviderNotConfiguredError

logger = structlog.get_logger("providers.llm")


class LLMRateLimitError(ProviderError):
    """Raised when LLM requests exceed provider rate limits or token bucket."""

    def __init__(self, provider: str, retry_after: float = 5.0, message: str | None = None) -> None:
        msg = message or f"LLM rate limited, retry in {int(retry_after)} s"
        super().__init__(provider, msg, retryable=True)
        self.retry_after = retry_after


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        return d


@dataclass(slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None


class TokenBucket:
    """Thread-safe / asyncio-safe token bucket rate limiter."""

    def __init__(self, rate_per_minute: float) -> None:
        self.capacity = float(rate_per_minute)
        self.rate_per_second = self.capacity / 60.0
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 30.0) -> float:  # noqa: ASYNC109 - existing timeout interface
        """Acquire a token, waiting if necessary up to timeout."""
        start_time = time.monotonic()
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
                self.last_refill = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return time.monotonic() - start_time

                needed = 1.0 - self.tokens
                wait_time = needed / self.rate_per_second
                if (time.monotonic() - start_time) + wait_time > timeout:
                    raise LLMRateLimitError(
                        "token_bucket",
                        retry_after=max(1.0, wait_time),
                        message=f"LLM rate limited, retry in {int(wait_time + 1)} s",
                    )
                await asyncio.sleep(min(wait_time, 0.5))


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def check_reachability(self) -> tuple[bool, str | None]: ...

    @abstractmethod
    async def resolve_model(self) -> str: ...

    async def aclose(self) -> None:
        """Cleanup resources."""
        return None


class NoneLLMProvider(LLMProvider):
    name = "none"

    def is_configured(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raise ProviderNotConfiguredError(
            self.name, "No LLM provider configured. Set LLM_PROVIDER and LLM_API_KEY in .env"
        )

    async def stream(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        raise ProviderNotConfiguredError(
            self.name, "No LLM provider configured. Set LLM_PROVIDER and LLM_API_KEY in .env"
        )
        if False:
            yield ""

    async def check_reachability(self) -> tuple[bool, str | None]:
        return False, "LLM provider set to none"

    async def resolve_model(self) -> str:
        return "none"


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible LLM adapter (supports Groq, OpenAI, Ollama, vLLM)."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str = "https://api.groq.com/openai/v1",
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        fallback_model: str = "llama-3.1-8b-instant",
        max_input_tokens: int = 5000,
        requests_per_minute: int = 20,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        user_agent: str = "AnalystForge/0.1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.max_input_tokens = max_input_tokens
        self.requests_per_minute = requests_per_minute
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.user_agent = user_agent

        self.resolved_model = model
        self.last_error: str | None = None
        self._limiter = TokenBucket(requests_per_minute)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
            )
        return self._client

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _estimate_tokens(self, text: str) -> int:
        """Fast heuristic: ~4 characters per token."""
        return max(1, len(text) // 4)

    def _trim_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cap retrieved context to max_input_tokens, trimming intermediate context."""
        total_tokens = sum(self._estimate_tokens(str(m.get("content", ""))) for m in messages)
        if total_tokens <= self.max_input_tokens:
            return messages

        # Preserve system prompt(s) and the latest user message
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        system_tokens = sum(self._estimate_tokens(str(m.get("content", ""))) for m in system_msgs)
        budget = max(0, self.max_input_tokens - system_tokens)

        trimmed: list[dict[str, Any]] = []
        for msg in reversed(other_msgs):
            cost = self._estimate_tokens(str(msg.get("content", "")))
            if cost <= budget:
                trimmed.insert(0, msg)
                budget -= cost
            else:
                # Truncate content of this message if it fits partially
                content = str(msg.get("content", ""))
                allowed_chars = budget * 4
                if allowed_chars > 20:
                    truncated_msg = dict(msg)
                    truncated_msg["content"] = content[:allowed_chars] + "... [context trimmed]"
                    trimmed.insert(0, truncated_msg)
                break

        return [*system_msgs, *trimmed]

    async def resolve_model(self) -> str:
        """Call GET {base}/models, verify LLM_MODEL or fall back to fallback_model."""
        if not self.api_key:
            self.last_error = "API key not configured"
            return self.model

        client = self._get_client()
        try:
            resp = await client.get("/models")
            if resp.status_code == 200:
                data = resp.json()
                model_items = data.get("data", [])
                available_ids = {m.get("id") for m in model_items if isinstance(m, dict)}

                if self.model in available_ids:
                    self.resolved_model = self.model
                elif self.fallback_model in available_ids:
                    logger.info(
                        "llm.model_fallback",
                        requested=self.model,
                        resolved=self.fallback_model,
                    )
                    self.resolved_model = self.fallback_model
                else:
                    # Select first chat model matching common architectures
                    def is_chat_model(mid: str) -> bool:
                        mid_lower = mid.lower()
                        if any(
                            neg in mid_lower
                            for neg in (
                                "guard",
                                "whisper",
                                "embed",
                                "moderation",
                                "tts",
                                "stt",
                                "safeguard",
                            )
                        ):
                            return False
                        return any(
                            pattern in mid_lower
                            for pattern in ("llama", "qwen", "gpt", "mixtral", "allam", "gemma")
                        )

                    candidates = [mid for mid in available_ids if mid and is_chat_model(mid)]
                    if candidates:

                        def sort_key(mid: str) -> tuple[int, str]:
                            m = mid.lower()
                            if "qwen" in m:
                                return (0, m)
                            if "llama" in m:
                                return (1, m)
                            if "gpt" in m:
                                return (2, m)
                            return (3, m)

                        self.resolved_model = sorted(candidates, key=sort_key)[0]
                        logger.info(
                            "llm.model_auto_selected",
                            requested=self.model,
                            resolved=self.resolved_model,
                        )
                    else:
                        self.resolved_model = self.fallback_model
                self.last_error = None
                return self.resolved_model
            else:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
                return self.model
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("llm.resolve_model_failed", error=str(exc))
            return self.model

    async def check_reachability(self) -> tuple[bool, str | None]:
        if not self.api_key:
            return False, "API key not configured"
        try:
            await self.resolve_model()
            if self.last_error:
                return False, self.last_error
            return True, None
        except Exception as exc:
            return False, str(exc)

    def _normalize_messages(
        self, messages: list[ChatMessage | dict[str, Any]]
    ) -> list[dict[str, Any]]:
        raw: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                raw.append(m.to_dict())
            else:
                raw.append(m)
        return self._trim_messages(raw)

    async def complete(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                self.name, "No LLM API key configured. Set LLM_API_KEY in .env"
            )

        await self._limiter.acquire()
        client = self._get_client()
        normalized_msgs = self._normalize_messages(messages)
        target_model = model or self.resolved_model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": normalized_msgs,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools

        for attempt in range(self.max_retries):
            try:
                resp = await client.post("/chat/completions", json=payload)
                if resp.status_code == 429:
                    retry_after_str = resp.headers.get("Retry-After")
                    retry_after = (
                        float(retry_after_str)
                        if retry_after_str and retry_after_str.isdigit()
                        else (2.0**attempt)
                    )
                    if attempt == self.max_retries - 1:
                        raise LLMRateLimitError(
                            self.name,
                            retry_after=retry_after,
                            message=f"LLM rate limited, retry in {int(retry_after + 1)} s",
                        )
                    await asyncio.sleep(min(retry_after, 10.0))
                    continue

                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content") or message.get("reasoning") or ""

                tool_calls: list[ToolCall] = []
                for tc in message.get("tool_calls", []):
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = {}
                    try:
                        fn_args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        fn_args = {"raw": fn.get("arguments")}
                    tool_calls.append(
                        ToolCall(id=tc.get("id", ""), name=fn_name, arguments=fn_args)
                    )

                usage = data.get("usage", {})
                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    model=data.get("model", target_model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    finish_reason=choice.get("finish_reason"),
                )
            except LLMRateLimitError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < self.max_retries - 1:
                    await asyncio.sleep(2.0**attempt)
                    continue
                raise ProviderError(
                    self.name, f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                ) from exc
            except Exception as exc:
                if attempt == self.max_retries - 1:
                    raise ProviderError(self.name, str(exc)) from exc
                await asyncio.sleep(1.0)

        raise ProviderError(self.name, "Failed to complete LLM request after retries")

    async def stream(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                self.name, "No LLM API key configured. Set LLM_API_KEY in .env"
            )

        await self._limiter.acquire()
        client = self._get_client()
        normalized_msgs = self._normalize_messages(messages)
        target_model = model or self.resolved_model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": normalized_msgs,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code == 429:
                    retry_after_str = resp.headers.get("Retry-After")
                    retry_after = (
                        float(retry_after_str)
                        if retry_after_str and retry_after_str.isdigit()
                        else 5.0
                    )
                    raise LLMRateLimitError(
                        self.name,
                        retry_after=retry_after,
                        message=f"LLM rate limited, retry in {int(retry_after + 1)} s",
                    )
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content") or delta.get("reasoning")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                self.name, f"Streaming error HTTP {exc.response.status_code}"
            ) from exc


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API adapter."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        timeout_seconds: float = 30.0,
        requests_per_minute: int = 20,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._limiter = TokenBucket(requests_per_minute)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def resolve_model(self) -> str:
        return self.model

    async def check_reachability(self) -> tuple[bool, str | None]:
        if not self.api_key:
            return False, "Anthropic API key not configured"
        return True, None

    async def complete(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise ProviderNotConfiguredError(self.name, "Anthropic API key not configured")

        await self._limiter.acquire()
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Format messages for Anthropic
        system_prompt: str | None = None
        anthropic_msgs: list[dict[str, Any]] = []
        for m in messages:
            role = m.role if isinstance(m, ChatMessage) else m.get("role")
            content = m.content if isinstance(m, ChatMessage) else m.get("content")
            if role == "system":
                system_prompt = content
            else:
                anthropic_msgs.append({"role": role, "content": content or ""})

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            )
            return LLMResponse(content=text, model=data.get("model", self.model))

    async def stream(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        # Basic streaming fallback
        res = await self.complete(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        yield res.content


class DeterministicFakeLLMProvider(LLMProvider):
    """Deterministic fake provider for test suites and CI without API keys."""

    name = "fake"

    def __init__(
        self,
        canned_response: str
        | dict[str, str] = "This is a deterministic AI response based on retrieved facts.",
    ) -> None:
        self.canned_response = canned_response
        self.call_history: list[list[dict[str, Any]]] = []

    def is_configured(self) -> bool:
        return True

    async def resolve_model(self) -> str:
        return "deterministic-fake-model-v1"

    async def check_reachability(self) -> tuple[bool, str | None]:
        return True, None

    async def complete(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raw_msgs = [m.to_dict() if isinstance(m, ChatMessage) else m for m in messages]
        self.call_history.append(raw_msgs)

        # Resolve content
        last_msg = str(raw_msgs[-1].get("content", "")) if raw_msgs else ""
        all_text = " ".join(str(m.get("content", "")) for m in raw_msgs)

        if response_format and response_format.get("type") == "json_object":
            content = json.dumps(
                {
                    "snapshot": "Deterministic corporate snapshot based on indexed disclosures.",
                    "thesis": "Market leadership substantiated by robust cash generation.",
                    "risks": "Regulatory, supply chain, and macroeconomic interest rate shifts.",
                    "valuation_summary": "In line with sector trading multiples and DCF fair value estimates.",
                    "confidence": 0.95,
                }
            )
        elif isinstance(self.canned_response, dict):
            matched = None
            for k, v in self.canned_response.items():
                if k.lower() in all_text.lower():
                    matched = v
                    break
            content = (
                matched
                or "[citation:1] Deterministic research synthesis based on retrieved disclosures."
            )
        else:
            content = str(self.canned_response)

        tool_calls: list[ToolCall] = []
        if tools:
            # If prompt asks for calculation or tool, return a fake tool call
            last_msg = str(raw_msgs[-1].get("content", ""))
            if "calculate" in last_msg.lower() or "dcf" in last_msg.lower():
                tool_calls.append(
                    ToolCall(
                        id="call_fake_1", name="calculate_dcf", arguments={"growth_rate": 0.05}
                    )
                )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model="deterministic-fake-model-v1",
            prompt_tokens=50,
            completion_tokens=25,
            finish_reason="stop",
        )

    async def stream(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        if isinstance(self.canned_response, dict):
            text = (
                next(iter(self.canned_response.values()))
                if self.canned_response
                else "Deterministic response"
            )
        else:
            text = str(self.canned_response)
        words = text.split(" ")
        for word in words:
            yield word + " "
