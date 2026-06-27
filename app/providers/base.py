from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class BaseProvider(ABC):
    @abstractmethod
    def estimate_tokens(self, prompt: str) -> int: ...

    @abstractmethod
    async def generate(self, prompt: str) -> GenerationResult: ...
