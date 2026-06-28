import anthropic

from app.config import settings
from app.providers.base import BaseProvider, GenerationResult


class ClaudeProvider(BaseProvider):
    """Production provider backed by Claude Haiku via the Anthropic API."""

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY must be set when USE_REAL_LLM=true")
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    def estimate_tokens(self, prompt: str) -> int:
        # ponytail: approx avoids a blocking network call; real count differs ~5%
        return max(1, len(prompt) // 4)

    async def generate(self, prompt: str) -> GenerationResult:
        response = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",  # can be made configurable later
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return GenerationResult(
            text=response.content[0].text,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
