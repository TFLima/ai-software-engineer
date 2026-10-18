"""Single composition point. Never fall back after configuration or transport errors."""
import os
from app.anthropic_llm import AnthropicAdapter, AnthropicConfig
from app.fake_llm import FakeLLMAdapter
from app.llm_client import BoundedLLMClient, LLMError
from app.openai_llm import openai_client_from_env


def llm_client_from_env(environ=None, transport=None):
    env = os.environ if environ is None else environ
    provider = env.get("LLM_PROVIDER", "openai")
    if provider == "openai":
        return openai_client_from_env(env, transport)
    if provider == "anthropic":
        return BoundedLLMClient(AnthropicAdapter(AnthropicConfig.from_env(env), transport))
    if provider == "fake":
        if (env.get("LLM_ENVIRONMENT") not in ("test", "development")
                or env.get("LLM_FAKE_ENABLED") != "true"
                or env.get("LLM_REAL_ENABLED", "false") != "false"):
            raise LLMError("configuration_error")
        return BoundedLLMClient(FakeLLMAdapter())
    raise LLMError("configuration_error")
