import random

from app.providers.base import BaseProvider, GenerationResult


class MockProvider(BaseProvider):
    def estimate_tokens(self, prompt: str) -> int:
        return max(1, len(prompt) // 4)

    async def generate(self, prompt: str) -> GenerationResult:
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(10, int(prompt_tokens * random.uniform(0.9, 1.1)))
        return GenerationResult(
            text=f"Mock response for: {prompt[:50]}",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
