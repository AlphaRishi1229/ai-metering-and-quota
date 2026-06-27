import anthropic

from app.providers.base import BaseProvider, GenerationResult
from app.providers.mock import MockProvider
from app.config import settings


class ClaudeProvider(BaseProvider):
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY must be set when USE_REAL_LLM=true")
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    def estimate_tokens(self, prompt: str) -> int:
        # ponytail: approx avoids a blocking network call; real count differs ~5%
        return max(1, len(prompt) // 4)

    async def generate(self, prompt: str) -> GenerationResult:
        response = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return GenerationResult(
            text=response.content[0].text,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )


# ponytail: module-level singleton avoids new httpx pool per request
_provider: BaseProvider | None = None


def get_provider() -> BaseProvider:
    global _provider
    if _provider is None:
        _provider = ClaudeProvider() if settings.USE_REAL_LLM else MockProvider()
    return _provider
