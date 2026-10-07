"""Deterministic adapter exercising the same reservations and deadlines as real calls."""
from app.llm_client import CostPolicy, LLMError, ModelReply, Prompt, Usage, encode


class FakeLLMAdapter:
    provider = "fake"
    model = "fixture-v1"
    context_window = 1_047_576
    max_output_tokens = 32_768
    cost_policy = CostPolicy()

    def __init__(self, replies=None):
        self._replies = list(replies if replies is not None else [
            ModelReply('{"schema_version":1,"findings":[]}', Usage(100, 20))])
        self.calls = 0

    @staticmethod
    def context_tokens(text: str) -> int:
        return len(text.encode("utf-8"))

    @staticmethod
    def input_tokens(prompt: Prompt, output_tokens: int) -> int:
        return len(encode({"system": prompt.system, "user": prompt.user,
                           "schema": prompt.schema}).encode("utf-8")) + 256

    async def complete(self, prompt, output_tokens, seconds, connect_seconds, response_bytes):
        self.calls += 1
        if not self._replies:
            raise LLMError("configuration_error")
        reply = self._replies.pop(0)
        if isinstance(reply, LLMError):
            raise reply
        return reply
