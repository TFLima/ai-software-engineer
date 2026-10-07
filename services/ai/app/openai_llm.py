"""One fixed OpenAI Chat Completions adapter; no SDK retries or tool support."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from typing import Mapping

import httpx

from app.llm_client import (BoundedLLMClient, CostPolicy, LLMError, ModelReply,
                            Prompt, Usage, encode)

MODEL = "gpt-4.1-mini-2025-04-14"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
DATA_POLICY = "standard-abuse-monitoring-30d"


@dataclass(frozen=True)
class OpenAIConfig:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    model: str = MODEL
    context_window: int = 1_047_576
    data_policy: str = ""
    source_disclosure_acknowledged: bool = False
    cost: CostPolicy = CostPolicy()

    def validate(self):
        self.cost.validate()
        if (self.enabled is not True or type(self.api_key) is not str
                or not self.api_key or any(ord(c) < 33 or ord(c) > 126 for c in self.api_key)
                or self.model != MODEL or type(self.context_window) is not int
                or self.context_window != 1_047_576 or self.data_policy != DATA_POLICY
                or self.source_disclosure_acknowledged is not True
                or self.cost.input_microusd_per_million < 400_000
                or self.cost.output_microusd_per_million < 1_600_000):
            raise LLMError("configuration_error")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        try:
            if env.get("LLM_REAL_ENABLED", "false") != "true":
                raise ValueError()
            cost = CostPolicy(*(int(env[name]) for name in (
                "LLM_INPUT_MICROUSD_PER_MILLION", "LLM_OUTPUT_MICROUSD_PER_MILLION",
                "LLM_CALL_MICROUSD", "LLM_ATTEMPT_MICROUSD")))
            config = cls(True, env["OPENAI_API_KEY"], env["LLM_MODEL"],
                         int(env["LLM_CONTEXT_WINDOW"]), env["LLM_DATA_POLICY"],
                         env.get("LLM_SOURCE_DISCLOSURE_ACKNOWLEDGED") == "true", cost)
            config.validate()
            return config
        except (KeyError, ValueError, TypeError, LLMError):
            raise LLMError("configuration_error") from None


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError()


def _usage(value) -> Usage:
    if value is None:
        return Usage()
    if (type(value) is not dict or value.keys() - {
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_tokens_details", "completion_tokens_details"}):
        raise LLMError("invalid_result")
    counters = [value.get("prompt_tokens"), value.get("completion_tokens")]
    if any(v is not None and (type(v) is not int or v < 0)
           for v in [*counters, value.get("total_tokens")]):
        raise LLMError("invalid_result")
    for name, allowed in (
        ("prompt_tokens_details", {"cached_tokens", "audio_tokens"}),
        ("completion_tokens_details", {"reasoning_tokens", "audio_tokens",
                                       "accepted_prediction_tokens", "rejected_prediction_tokens"}),
    ):
        details = value.get(name)
        if details is not None and (type(details) is not dict or details.keys() - allowed
                                    or any(type(v) is not int or v < 0 for v in details.values())):
            raise LLMError("invalid_result")
    return Usage(*counters)


def _retry_after(value: str | None) -> float:
    if value is None:
        return 0
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0
    return max(0, seconds) if math.isfinite(seconds) else 0


class OpenAIAdapter:
    provider = "openai"
    model = MODEL
    context_window = 1_047_576
    max_output_tokens = 32_768

    def __init__(self, config: OpenAIConfig, transport: httpx.AsyncBaseTransport | None = None):
        config.validate()
        self._config = config
        self.cost_policy = config.cost
        # Transport injection is for deterministic tests. The runtime path uses
        # httpx's verified TLS and session proxy; redirects and retries stay off.
        self._transport = transport

    def __repr__(self):
        return "OpenAIAdapter(model='gpt-4.1-mini-2025-04-14')"

    def payload(self, prompt: Prompt, output_tokens: int) -> dict:
        return {
            "model": self.model, "store": False, "stream": False, "n": 1,
            "service_tier": "default",
            "max_completion_tokens": output_tokens,
            "messages": [{"role": "system", "content": prompt.system},
                         {"role": "user", "content": prompt.user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "findings_v1", "strict": True, "schema": prompt.schema}},
        }

    @staticmethod
    def context_tokens(text: str) -> int:
        # No compatible tokenizer is installed. B07 can use this same counter.
        return len(text.encode("utf-8"))

    def input_tokens(self, prompt: Prompt, output_tokens: int) -> int:
        # Count the entire serialized provider payload, schema and instructions,
        # plus a conservative allowance for provider message framing.
        return len(encode(self.payload(prompt, output_tokens)).encode("utf-8")) + 256

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
                        headers={"Authorization": "Bearer " + self._config.api_key,
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
        try:
            value = json.loads(body.decode("utf-8"), object_pairs_hook=_no_duplicates,
                               parse_constant=_reject_constant)
            if (type(value) is not dict or value.get("model") != self.model
                    or value.keys() - {"id", "object", "created", "model", "choices", "usage",
                                       "service_tier", "system_fingerprint"}
                    or type(value.get("choices")) is not list or len(value["choices"]) != 1):
                raise ValueError()
            # Provider envelope metadata is translated, not forwarded. The
            # candidate string is NEVER parsed, repaired or filtered here.
            usage = _usage(value.get("usage"))
            if value.get("service_tier") not in (None, "default"):
                raise LLMError("invalid_result", usage)
            choice = value["choices"][0]
            if (type(choice) is not dict or choice.keys() - {
                    "index", "message", "finish_reason", "logprobs"}
                    or type(choice.get("index")) is not int or choice["index"] != 0
                    or choice.get("logprobs") is not None):
                raise LLMError("invalid_result", usage)
            message = choice["message"]
            if (type(message) is not dict or message.keys() - {
                    "role", "content", "refusal", "annotations", "audio", "tool_calls", "function_call"}
                    or message.get("role") != "assistant"
                    or message.get("tool_calls") or message.get("function_call")
                    or message.get("audio") or message.get("annotations")):
                raise LLMError("invalid_result", usage)
            if message.get("refusal") or choice.get("finish_reason") in ("length", "content_filter"):
                raise LLMError("invalid_findings", usage)
            if choice.get("finish_reason") != "stop" or type(message.get("content")) is not str:
                raise LLMError("invalid_result", usage)
            if not message["content"].strip():
                raise LLMError("invalid_findings", usage)
            return ModelReply(message["content"], usage)
        except LLMError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise LLMError("invalid_result") from None


def openai_client_from_env(environ: Mapping[str, str] | None = None,
                           transport: httpx.AsyncBaseTransport | None = None) -> BoundedLLMClient:
    config = OpenAIConfig.from_env(environ)
    return BoundedLLMClient(OpenAIAdapter(config, transport), config.cost)
