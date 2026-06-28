from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GenerationResult:
    """Result returned by a provider after text generation."""

    text: str
    prompt_tokens: int
    completion_tokens: int


class BaseProvider(ABC):
    """Abstract base class for LLM provider implementations."""

    @abstractmethod
    def estimate_tokens(self, prompt: str) -> int:
        """Return a token count estimate for the prompt without a network call."""
        ...

    @abstractmethod
    async def generate(self, prompt: str) -> GenerationResult:
        """Generate text and return the result with actual token counts."""
        ...
