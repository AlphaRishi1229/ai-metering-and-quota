import anthropic

from app.providers.base import BaseProvider, GenerationResult
from app.providers.mock import MockProvider
from app.config import settings


class ClaudeProvider(BaseProvider):
    def __init__(self):
        # ponytail: sync client, switch to AsyncAnthropic if throughput matters
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def estimate_tokens(self, prompt: str) -> int:
        response = self._client.messages.count_tokens(
            model="claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.input_tokens

    async def generate(self, prompt: str) -> GenerationResult:
        response = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return GenerationResult(
            text=response.content[0].text,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )


def get_provider() -> BaseProvider:
    if settings.USE_REAL_LLM:
        return ClaudeProvider()
    return MockProvider()
