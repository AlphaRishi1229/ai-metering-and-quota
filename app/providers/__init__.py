import logging

from app.config import settings
from app.providers.base import BaseProvider
from app.providers.claude import ClaudeProvider
from app.providers.mock import MockProvider

logger = logging.getLogger(__name__)

# ponytail: module-level singleton avoids new httpx pool per request
_provider: BaseProvider | None = None


def get_provider() -> BaseProvider:
    """Return the singleton provider (Claude or Mock based on USE_REAL_LLM)."""
    global _provider
    if _provider is None:
        _provider = ClaudeProvider() if settings.USE_REAL_LLM else MockProvider()
        logger.info("Provider initialized: %s (USE_REAL_LLM=%s)", type(_provider).__name__, settings.USE_REAL_LLM)
    return _provider
