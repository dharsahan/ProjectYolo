from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

try:
    from litellm import acompletion as litellm_acompletion
except Exception:
    litellm_acompletion = None


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: Optional[str]
    base_url: Optional[str]


def _default_model(provider: str) -> str:
    defaults = {
        "openai": "gpt-4o-mini",
        "openrouter": "openai/gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
        "compatible": "gpt-4o-mini",
    }
    return defaults.get(provider, "gpt-4o-mini")


def load_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()

    if provider == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("OPENROUTER_API_KEY"):
            provider = "openrouter"
        else:
            provider = "openai"

    model = os.getenv("MODEL_NAME")

    if provider == "openrouter":
        return LLMConfig(
            provider="openrouter",
            model=model or os.getenv("OPENROUTER_MODEL") or _default_model("openrouter"),
            api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )

    if provider == "anthropic":
        return LLMConfig(
            provider="anthropic",
            model=model or os.getenv("ANTHROPIC_MODEL") or _default_model("anthropic"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            base_url=os.getenv("ANTHROPIC_BASE_URL"),
        )

    if provider == "compatible":
        return LLMConfig(
            provider="compatible",
            model=model or os.getenv("LLM_MODEL") or _default_model("compatible"),
            api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

    return LLMConfig(
        provider="openai",
        model=model or os.getenv("OPENAI_MODEL") or _default_model("openai"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


class LLMRouter:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._openai_client: Optional[AsyncOpenAI] = None

        if self.config.provider in {"openai", "openrouter", "compatible"}:
            # Some compatible providers/local proxies do not require a key.
            api_key = self.config.api_key or "not-required"
            self._openai_client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.base_url,
                timeout=60.0,
            )

    async def chat_completions(
        self,
        *,
        messages: list,
        tools: list,
        tool_choice: str = "auto",
    ) -> Any:
        if self.config.provider in {"openai", "openrouter", "compatible"}:
            if not self._openai_client:
                raise RuntimeError("OpenAI-compatible client is not initialized")

            kwargs: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }

            extra_headers = {}
            if self.config.provider == "openrouter":
                referer = os.getenv("OPENROUTER_HTTP_REFERER")
                title = os.getenv("OPENROUTER_X_TITLE")
                if referer:
                    extra_headers["HTTP-Referer"] = referer
                if title:
                    extra_headers["X-Title"] = title
            if extra_headers:
                kwargs["extra_headers"] = extra_headers

            return await self._openai_client.chat.completions.create(**kwargs)

        if self.config.provider == "anthropic":
            if litellm_acompletion is None:
                raise RuntimeError(
                    "Anthropic provider requires `litellm`. Install dependencies with `pip install -r requirements.txt`."
                )
            if not self.config.api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is required for provider `anthropic`.")

            kwargs: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "api_key": self.config.api_key,
                "timeout": 60,
            }
            if self.config.base_url:
                kwargs["api_base"] = self.config.base_url
                kwargs["base_url"] = self.config.base_url

            return await litellm_acompletion(**kwargs)

        raise RuntimeError(f"Unsupported provider: {self.config.provider}")
