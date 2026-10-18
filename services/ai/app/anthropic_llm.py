"""Official Messages adapter: text JSON only, no tools, SDK or hidden retries."""
import asyncio
from dataclasses import dataclass, field
import json
import os
import re
from typing import Mapping

import httpx

from app.llm_client import CostPolicy, LLMError, ModelReply, Prompt, Usage, encode
from app.openai_llm import _no_duplicates, _reject_constant, _retry_after

ENDPOINT = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
DATA_POLICY = "anthropic-standard-30d-exceptions-reviewed"
# Reviewed official standard API prices, 2026-10-18. No cache discounts.
MODELS = {
    MODEL: (200_000, 64_000, 1_000_000, 5_000_000),
    "claude-sonnet-4-5-20250929": (200_000, 64_000, 3_000_000, 15_000_000),
}


@dataclass(frozen=True)
class AnthropicConfig:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    model: str = MODEL
    context_window: int = 200_000
    max_output_tokens: int = 64_000
    data_policy: str = ""
    source_disclosure_acknowledged: bool = False
    cost: CostPolicy = CostPolicy(1_000_000, 5_000_000)

    def validate(self):
        self.cost.validate()
        if (self.enabled is not True or type(self.api_key) is not str or not self.api_key
                or any(ord(c) < 33 or ord(c) > 126 for c in self.api_key)
                or type(self.model) is not str or self.model not in MODELS
                or not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", self.model)
                or self.data_policy != DATA_POLICY
                or self.source_disclosure_acknowledged is not True):
            raise LLMError("configuration_error")
        window, output, input_rate, output_rate = MODELS[self.model]
        if (type(self.context_window) is not int or not 0 < self.context_window <= window
                or type(self.max_output_tokens) is not int or not 0 < self.max_output_tokens <= output
                or self.cost.input_microusd_per_million < input_rate
                or self.cost.output_microusd_per_million < output_rate):
            raise LLMError("configuration_error")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        try:
            model = env.get("ANTHROPIC_MODEL", MODEL)
            window, output, input_rate, output_rate = MODELS[model]
            config = cls(
                env.get("LLM_REAL_ENABLED", "false") == "true", env["ANTHROPIC_API_KEY"], model,
                int(env.get("ANTHROPIC_CONTEXT_WINDOW", window)),
                int(env.get("ANTHROPIC_MAX_OUTPUT_TOKENS", output)),
                env["ANTHROPIC_DATA_POLICY"],
                env.get("ANTHROPIC_SOURCE_DISCLOSURE_ACKNOWLEDGED") == "true",
                CostPolicy(int(env.get("ANTHROPIC_INPUT_MICROUSD_PER_MILLION", input_rate)),
                           int(env.get("ANTHROPIC_OUTPUT_MICROUSD_PER_MILLION", output_rate)),
                           int(env.get("ANTHROPIC_CALL_MICROUSD", 20_000)),
                           int(env.get("ANTHROPIC_ATTEMPT_MICROUSD", 40_000)),
                           int(env.get("LLM_CALL_CEILING_MICROUSD", 20_000)),
                           int(env.get("LLM_ATTEMPT_CEILING_MICROUSD", 40_000))))
            config.validate()
            return config
        except (KeyError, ValueError, TypeError, LLMError):
            raise LLMError("configuration_error") from None


def wire_schema(value):
    """Translate only unsupported provider constraints; B09 retains ALL checks."""
    if isinstance(value, list):
        return [wire_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    unsupported = {"minimum", "maximum", "minLength", "maxLength", "maxItems"}
    result = {key: wire_schema(item) for key, item in value.items() if key not in unsupported}
    constraints = {key: item for key, item in value.items() if key in unsupported}
    if constraints:
        result["description"] = "Required local constraints: " + encode(constraints)
    return result


class AnthropicAdapter:
    provider = "anthropic"

    def __init__(self, config: AnthropicConfig, transport=None):
        config.validate()
        self._config = config
        self.model = config.model
        self.context_window = config.context_window
        self.max_output_tokens = config.max_output_tokens
        self.cost_policy = config.cost
        self._transport = transport

    def payload(self, prompt: Prompt, output_tokens: int) -> dict:
        return {"model": self.model, "max_tokens": output_tokens, "stream": False, "service_tier": "standard_only",
                "system": prompt.system,
                "messages": [{"role": "user", "content": prompt.user}],
                "output_config": {"format": {"type": "json_schema", "schema": wire_schema(prompt.schema)}}}

    @staticmethod
    def context_tokens(text):
        return len(text.encode("utf-8"))

    def input_tokens(self, prompt, output_tokens):
        # Byte upper bound plus room for framing and structured-output instructions.
        return len(encode(self.payload(prompt, output_tokens)).encode("utf-8")) + 1024

    async def complete(self, prompt: Prompt, output_tokens: int, seconds: float,
                       connect_seconds: float, response_bytes: int) -> ModelReply:
        try:
            async with asyncio.timeout(seconds):
                async with httpx.AsyncClient(
                    transport=self._transport, follow_redirects=False,
                    timeout=httpx.Timeout(seconds, connect=connect_seconds),
                ) as client:
                    async with client.stream(
                        "POST", ENDPOINT,
                        headers={"x-api-key": self._config.api_key, "anthropic-version": "2023-06-01",
                                 "Content-Type": "application/json", "Accept": "application/json"},
                        content=encode(self.payload(prompt, output_tokens)).encode("utf-8"),
                    ) as response:
                        status = response.status_code
                        if status != 200:
                            if status in (401, 403, 400, 404, 422):
                                raise LLMError("configuration_error")
                            if status == 429:
                                raise LLMError("upstream_rate_limited",
                                               retry_after=_retry_after(response.headers.get("Retry-After")))
                            if status in (408, 504):
                                raise LLMError("upstream_timeout")
                            if 500 <= status <= 599:
                                raise LLMError("upstream_unavailable")
                            raise LLMError("invalid_result")  # Includes redirects.
                        if response.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                            raise LLMError("invalid_result")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > response_bytes:
                                raise LLMError("limit_exceeded")
                            body.extend(chunk)
            return self._translate(bytes(body))
        except (TimeoutError, httpx.TimeoutException):
            raise LLMError("upstream_timeout") from None
        except httpx.TransportError:
            raise LLMError("network_unavailable") from None
        except LLMError:
            raise
        except Exception:
            raise LLMError("invalid_result") from None

    def _translate(self, body: bytes) -> ModelReply:
        usage = Usage()
        try:
            value = json.loads(body.decode("utf-8"), object_pairs_hook=_no_duplicates,
                               parse_constant=_reject_constant)
            if (type(value) is not dict or value.keys() - {
                    "id", "type", "role", "model", "content", "stop_reason", "stop_sequence", "stop_details", "usage"}
                    or value.get("type") != "message" or value.get("role") != "assistant"
                    or value.get("model") != self.model):
                raise ValueError()
            counters = value["usage"]
            if (type(counters) is not dict or not {"input_tokens", "output_tokens"} <= counters.keys()
                    or counters.keys() - {"input_tokens", "output_tokens", "cache_creation_input_tokens",
                                          "cache_read_input_tokens", "cache_creation", "service_tier",
                                          "inference_geo", "server_tool_use", "output_tokens_details", "speed"}):
                raise ValueError()
            names = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            if any(type(counters.get(k, 0)) is not int or counters.get(k, 0) < 0 for k in names):
                raise ValueError()
            usage = Usage(counters["input_tokens"] + counters.get("cache_creation_input_tokens", 0)
                          + counters.get("cache_read_input_tokens", 0), counters["output_tokens"])
            # Caching, server tools and premium service tiers were never requested.
            if (counters.get("cache_creation_input_tokens", 0)
                    or counters.get("service_tier") not in (None, "standard")
                    or counters.get("inference_geo") not in (None, "global")
                    or counters.get("speed") not in (None, "standard")):
                raise LLMError("invalid_result", usage)
            for name, allowed in (
                ("cache_creation", {"ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens"}),
                ("server_tool_use", {"web_fetch_requests", "web_search_requests"}),
                ("output_tokens_details", {"thinking_tokens"}),
            ):
                details = counters.get(name)
                if details is not None and (type(details) is not dict or details.keys() - allowed
                        or any(type(v) is not int or v != 0 for v in details.values())):
                    raise LLMError("invalid_result", usage)
            if value.get("stop_details") is not None:
                raise LLMError("invalid_findings", usage)
            if value.get("stop_reason") in ("max_tokens", "refusal"):
                raise LLMError("invalid_findings", usage)
            if value.get("stop_reason") != "end_turn" or value.get("stop_sequence") is not None:
                raise LLMError("invalid_result", usage)
            blocks = value["content"]
            if (type(blocks) is not list or len(blocks) != 1 or type(blocks[0]) is not dict
                    or blocks[0].keys() != {"type", "text"} or blocks[0]["type"] != "text"
                    or type(blocks[0]["text"]) is not str):
                raise LLMError("invalid_result", usage)
            if not blocks[0]["text"].strip():
                raise LLMError("invalid_findings", usage)
            return ModelReply(blocks[0]["text"], usage)
        except LLMError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise LLMError("invalid_result", usage) from None
