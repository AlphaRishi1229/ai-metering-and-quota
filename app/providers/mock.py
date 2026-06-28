import random

from app.providers.base import BaseProvider, GenerationResult

# Trigger words (case-insensitive) that simulate specific AI-side failures.
# Include any of these in a prompt to force the corresponding error path.
_TRIGGERS: dict[str, Exception] = {
    "MOCK_ERROR": RuntimeError("Simulated AI provider error"),
    "MOCK_TIMEOUT": TimeoutError("Simulated AI provider timeout"),
    "MOCK_RATE_LIMIT": RuntimeError("Simulated rate limit: too many requests"),
    "MOCK_OVERLOAD": RuntimeError("Simulated provider overload: service unavailable"),
}


class MockProvider(BaseProvider):
    """Deterministic mock provider for tests and local development."""

    def estimate_tokens(self, prompt: str) -> int:
        return max(1, len(prompt) // 4)

    async def generate(self, prompt: str) -> GenerationResult:
        """Return a mock response with ±10% random variance in completion tokens.

        Include a trigger word in the prompt to simulate AI-side failures:
          MOCK_ERROR       → generic provider error
          MOCK_TIMEOUT     → timeout
          MOCK_RATE_LIMIT  → rate limit exceeded
          MOCK_OVERLOAD    → provider overload / 529
        """
        upper = prompt.upper()
        for trigger, exc in _TRIGGERS.items():
            if trigger in upper:
                raise exc

        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(10, int(prompt_tokens * random.uniform(0.9, 1.1)))
        return GenerationResult(
            text=f"Mock response for: {prompt[:50]}",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
