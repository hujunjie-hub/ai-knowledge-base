"""Unified LLM calling client supporting DeepSeek, Qwen, and OpenAI providers.

Uses httpx to call OpenAI-compatible chat completions APIs. Provider selection
via LLM_PROVIDER environment variable, with per-provider API key and base URL.
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("model_client")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """Token usage statistics for a single LLM request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Unified response from any LLM provider.

    Attributes:
        content: The text content of the model response.
        usage: Token usage statistics returned by the API.
        model: The model name used for this request.
        finish_reason: Why the model stopped generating (stop, length, etc.).
    """

    content: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""


# ---------------------------------------------------------------------------
# Provider configuration (env-var driven)
# ---------------------------------------------------------------------------

# Pricing in USD per 1M tokens: (input_price, output_price)
_PROVIDER_PRICING: dict[str, tuple[float, float]] = {
    "deepseek": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
    "qwen": (0.50, 2.00),
    "qwen-max": (2.00, 8.00),
    "openai": (2.50, 10.00),
    "openai-mini": (0.15, 0.60),
}

_DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "openai": "gpt-4o",
}

_DEFAULT_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": "https://api.openai.com/v1",
}


def _get_provider_config() -> tuple[str, str, str, str]:
    """Read provider configuration from environment variables.

    Returns:
        A tuple of (provider_name, api_key, base_url, model).
    """
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()

    api_key = os.getenv(f"{provider.upper()}_API_KEY", "")
    if not api_key:
        api_key = os.getenv("LLM_API_KEY", "")

    base_url = os.getenv(
        f"{provider.upper()}_BASE_URL",
        _DEFAULT_BASE_URLS.get(provider, ""),
    )
    model = os.getenv("LLM_MODEL", _DEFAULT_MODELS.get(provider, ""))

    return provider, api_key, base_url, model


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Subclasses must implement :meth:`chat`.
    """

    provider_name: str = ""
    model: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request and return a unified response.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            temperature: Sampling temperature, clamped by the API to [0.0, 2.0].
            max_tokens: Upper bound on response token count.
            **kwargs: Additional provider-specific parameters passed through.

        Returns:
            Unified response object with content, usage, model, and finish_reason.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI-compatible provider
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider targeting OpenAI-compatible chat completions endpoints.

    Works with DeepSeek, Qwen (via DashScope compatible mode), OpenAI, and any
    self-hosted endpoint that speaks the ``/v1/chat/completions`` protocol.
    """

    def __init__(
        self, api_key: str, base_url: str, model: str, provider_name: str = ""
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self.provider_name = provider_name

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request to the OpenAI-compatible endpoint.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            temperature: Sampling temperature, clamped by the API to [0.0, 2.0].
            max_tokens: Upper bound on response token count.
            **kwargs: Additional parameters forwarded to the API (top_p, stop, etc.).

        Returns:
            Unified response with content, usage stats, model, and finish_reason.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
            httpx.TimeoutException: If the request exceeds the client timeout.
        """
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        logger.debug("chat request url=%s model=%s", url, self.model)

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        choice = data["choices"][0]
        usage_raw = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            usage=Usage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
                total_tokens=usage_raw.get("total_tokens", 0),
            ),
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason", ""),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_provider(
    provider_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """Create an LLM provider instance from explicit args or environment variables.

    Args:
        provider_name: One of ``deepseek`` / ``qwen`` / ``openai``. Reads
            ``LLM_PROVIDER`` if omitted (default ``deepseek``).
        api_key: API key for the chosen provider. Reads the provider-specific
            env var (e.g. ``DEEPSEEK_API_KEY``) or ``LLM_API_KEY`` if omitted.
        base_url: Override the default chat completions base URL.
        model: Override the default model for the selected provider.

    Returns:
        A ready-to-use :class:`LLMProvider` instance.

    Raises:
        ValueError: If no API key can be resolved.
    """
    _name, _api_key, _base_url, _model = _get_provider_config()

    name = provider_name or _name
    key = api_key or _api_key
    url = base_url or _base_url
    mdl = model or _model

    if not key:
        raise ValueError(
            f"No API key configured for provider '{name}'. "
            f"Set {name.upper()}_API_KEY or LLM_API_KEY."
        )

    logger.info("creating provider=%s model=%s base_url=%s", name, mdl, url)
    return OpenAICompatibleProvider(api_key=key, base_url=url, model=mdl, provider_name=name)


# ---------------------------------------------------------------------------
# Retry wrapper with exponential backoff
# ---------------------------------------------------------------------------


async def chat_with_retry(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    max_retries: int = 3,
    timeout: float = 60.0,
    **kwargs: Any,
) -> LLMResponse:
    """Send a chat request with automatic retry and exponential backoff.

    Retries on server errors (5xx), rate-limit responses (429), and network
    failures. Client errors (4xx except 429) are re-raised immediately.

    Args:
        provider: The LLM provider to call.
        messages: Chat messages to send.
        max_retries: Total attempts before giving up.
        timeout: Per-attempt timeout in seconds.
        **kwargs: Forwarded to ``provider.chat()``.

    Returns:
        The successful :class:`LLMResponse`.

    Raises:
        RuntimeError: If all attempts are exhausted.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            logger.debug("chat attempt %d/%d", attempt + 1, max_retries)
            return await asyncio.wait_for(
                provider.chat(messages, **kwargs),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"request timed out after {timeout}s")
            logger.warning("chat timeout (attempt %d/%d)", attempt + 1, max_retries)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            last_error = exc
            logger.warning(
                "chat http %d on attempt %d/%d", status, attempt + 1, max_retries
            )
            if status < 500 and status != 429:
                raise
        except (httpx.RequestError, OSError) as exc:
            last_error = exc
            logger.warning(
                "chat network error on attempt %d/%d: %s",
                attempt + 1, max_retries, exc,
            )

        if attempt < max_retries - 1:
            delay = 2 ** attempt
            logger.debug("retrying in %ds ...", delay)
            await asyncio.sleep(delay)

    raise RuntimeError(
        f"chat failed after {max_retries} attempts"
    ) from last_error


# ---------------------------------------------------------------------------
# Token estimation & cost calculation
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Roughly estimate the token count of a string.

    Uses a character-based heuristic: ~1 token per 4 ASCII characters and
    ~1 token per 1.5 CJK characters. Not a replacement for a real tokenizer;
    useful for pre-flight cost estimates.

    Args:
        text: The text to estimate.

    Returns:
        Estimated token count, minimum 1 for non-empty input.
    """
    if not text:
        return 0

    cjk = sum(
        1 for c in text
        if "一" <= c <= "鿿" or "　" <= c <= "〿"
    )
    ascii_chars = len(text) - cjk
    tokens = int(cjk / 1.5 + ascii_chars / 4.0)
    return max(tokens, 1)


def estimate_cost(
    prompt_text: str,
    completion_text: str = "",
    *,
    provider: str | None = None,
    model: str | None = None,
) -> float:
    """Estimate USD cost from raw text using heuristic token counts.

    Args:
        prompt_text: The input prompt text.
        completion_text: The model response text (empty for pre-flight estimates).
        provider: Provider name for pricing lookup. Reads ``LLM_PROVIDER`` if
            omitted.
        model: Specific model name for refined pricing. Falls back to provider
            default pricing.

    Returns:
        Estimated cost in USD, rounded to 6 decimal places.
    """
    resolved_provider = provider or os.getenv("LLM_PROVIDER", "deepseek").lower()

    pricing_key: str = resolved_provider
    if model and model in _PROVIDER_PRICING:
        pricing_key = model
    elif pricing_key not in _PROVIDER_PRICING:
        pricing_key = "openai"

    input_price, output_price = _PROVIDER_PRICING[pricing_key]
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)

    cost = (
        prompt_tokens / 1_000_000 * input_price
        + completion_tokens / 1_000_000 * output_price
    )
    return round(cost, 6)


def usage_cost(usage: Usage, provider: str | None = None) -> float:
    """Calculate actual USD cost from API-returned Usage data.

    Args:
        usage: Token usage stats from an :class:`LLMResponse`.
        provider: Provider name for pricing. Reads ``LLM_PROVIDER`` if omitted.

    Returns:
        Cost in USD, rounded to 6 decimal places.
    """
    resolved = provider or os.getenv("LLM_PROVIDER", "deepseek").lower()
    pricing_key = resolved if resolved in _PROVIDER_PRICING else "openai"
    input_price, output_price = _PROVIDER_PRICING[pricing_key]

    cost = (
        usage.prompt_tokens / 1_000_000 * input_price
        + usage.completion_tokens / 1_000_000 * output_price
    )
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


async def quick_chat(
    prompt: str,
    *,
    provider: LLMProvider | None = None,
    system: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Send a single-turn prompt and return the text response.

    Creates a default provider from environment if none is supplied.

    Args:
        prompt: The user message to send.
        provider: An existing provider instance. Auto-created if ``None``.
        system: Optional system message to set model behavior.
        temperature: Sampling temperature.

    Returns:
        The model's text response.
    """
    if provider is None:
        provider = create_provider()

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await chat_with_retry(provider, messages, temperature=temperature)
    cost = usage_cost(response.usage, provider.provider_name or None)
    logger.info(
        "quick_chat model=%s tokens=%d cost=$%.6f",
        response.model,
        response.usage.total_tokens,
        cost,
    )
    return response.content


def quick_chat_sync(
    prompt: str,
    *,
    provider: LLMProvider | None = None,
    system: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Synchronous wrapper for :func:`quick_chat`.

    Args:
        prompt: The user message to send.
        provider: An existing provider instance. Auto-created if ``None``.
        system: Optional system message.
        temperature: Sampling temperature.

    Returns:
        The model's text response.
    """
    return asyncio.run(
        quick_chat(prompt, provider=provider, system=system, temperature=temperature)
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _test() -> None:
        provider_name, api_key, base_url, model = _get_provider_config()
        logger.info("provider=%s base_url=%s model=%s", provider_name, base_url, model)
        logger.info("api_key configured: %s", "yes" if api_key else "no")

        # --- Token estimation ---
        en_text = "Hello, how are you today?"
        cn_text = "你好，今天过得怎么样？"
        logger.info(
            "token estimate: EN=%d CN=%d",
            estimate_tokens(en_text),
            estimate_tokens(cn_text),
        )

        # --- Cost estimation ---
        cost = estimate_cost(en_text, "I'm doing great, thank you!", provider=provider_name)
        logger.info("estimated cost for sample exchange: $%.6f", cost)

        if not api_key:
            logger.info("no API key configured, skipping live tests")
            return

        # --- Live chat ---
        prov = create_provider()
        try:
            response = await chat_with_retry(
                prov,
                [{"role": "user", "content": "Say 'hello world' in exactly 5 words."}],
                max_tokens=50,
            )
            logger.info("live response: %s", response.content.strip())
            logger.info("usage: %s", response.usage)
            logger.info("cost: $%.6f", usage_cost(response.usage, provider_name))
        except Exception as exc:
            logger.exception("live chat test failed: %s", exc)

        # --- quick_chat ---
        try:
            result = await quick_chat("Reply with just the word OK.")
            logger.info("quick_chat result: %s", result.strip())
        except Exception as exc:
            logger.exception("quick_chat test failed: %s", exc)

    asyncio.run(_test())
