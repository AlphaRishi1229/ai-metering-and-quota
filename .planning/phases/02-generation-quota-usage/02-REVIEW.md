---
phase: 02-generation-quota-usage
reviewed: 2026-06-27T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - app/config.py
  - app/main.py
  - app/models.py
  - app/providers/__init__.py
  - app/providers/base.py
  - app/providers/claude.py
  - app/providers/mock.py
  - app/routers/generate.py
  - app/schemas.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-27  
**Depth:** standard  
**Files Reviewed:** 9  
**Status:** issues_found

## Summary

The core reserve→generate→settle flow is structurally sound: SELECT FOR UPDATE
is used in all three DB transactions, the `finally` block correctly releases
the reservation only when `settled=False`, and all three UsageLog states
(success, quota_exceeded, ai_error) are written. The critical race-safety
requirement is met.

However, three blockers exist: the real `ClaudeProvider` calls a **synchronous**
Anthropic SDK inside async handlers (event loop blocked on every real LLM call),
`reserved_credits` can silently underflow to a negative value (corrupting quota
state), and the prompt has no maximum length bound (denial-of-service via large
input to the sync blocking call).

---

## Critical Issues

### CR-01: Synchronous Anthropic SDK called inside async handler — event loop blocked

**File:** `app/providers/claude.py:14,21`  
**Issue:** `ClaudeProvider.estimate_tokens()` (line 14) and `ClaudeProvider.generate()` (line 21)
both call `self._client.messages.count_tokens(...)` and `self._client.messages.create(...)` on
the **synchronous** `anthropic.Anthropic` client. The `generate` method is declared `async def`
but contains no `await`; `estimate_tokens` is a plain sync method. Both are called from the
async FastAPI handler in `app/routers/generate.py:26,72`. This blocks the entire event loop
(and every other in-flight request) for the full duration of each Anthropic API round-trip,
typically hundreds of milliseconds to several seconds. Under any concurrent load the service
will be effectively single-threaded and latency will compound.

**Fix:** Use `anthropic.AsyncAnthropic` and `await` the calls:

```python
# app/providers/claude.py
import anthropic
from app.providers.base import BaseProvider, GenerationResult
from app.config import settings


class ClaudeProvider(BaseProvider):
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    def estimate_tokens(self, prompt: str) -> int:
        # count_tokens has no async variant in the SDK; run in threadpool to avoid blocking
        import asyncio
        # ponytail: called synchronously by caller — wrap at the call site instead
        # Simplest fix: use the sync client only for estimate_tokens via run_in_executor,
        # or approximate with len(prompt)//4 like MockProvider does (avoids a network call).
        return max(1, len(prompt) // 4)  # avoids blocking; real token count differs by ~5%

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
```

If an exact pre-generation token count is required, wrap the sync call with
`asyncio.get_event_loop().run_in_executor(None, sync_fn)`.

---

### CR-02: `reserved_credits` can underflow to a negative value

**File:** `app/routers/generate.py:85,137`  
**Issue:** Both the settle TX (line 85) and the finally-block reservation release (line 137)
do `user.reserved_credits -= estimated_credits` without a lower-bound guard. If a concurrent
bug, direct DB edit, or future code path ever leaves `reserved_credits` at a value lower than
`estimated_credits` at the moment of decrement, the column goes negative. A negative
`reserved_credits` inflates `remaining = quota - used_credits - reserved_credits` (line 40),
allowing users to exceed their quota on subsequent requests. The column has no DB-level
`CHECK (reserved_credits >= 0)` constraint to catch this.

**Fix:** Add a DB constraint and a guard at the decrement site:

```sql
-- migration / schema change
ALTER TABLE users ADD CONSTRAINT reserved_credits_non_negative
    CHECK (reserved_credits >= 0);
```

```python
# app/routers/generate.py — settle TX (line 85) and finally block (line 137)
user.reserved_credits = max(0, user.reserved_credits - estimated_credits)
```

The `max(0, ...)` is a safety floor; the DB constraint makes violations visible rather than
silently corrupt.

---

### CR-03: No maximum prompt length — synchronous blocking amplified by large input

**File:** `app/schemas.py:25`, `app/providers/claude.py:14`  
**Issue:** `GenerateRequest.prompt` has `min_length=1` but no `max_length`. Any authenticated
caller can send an arbitrarily large prompt (e.g., 50 MB). This hits `estimate_tokens()` which
(in the real provider) makes a synchronous Anthropic API call with the full payload, blocking
the event loop for a proportionally long time. Even with the MockProvider, `len(prompt) // 4`
on 50 MB of text is instantaneous, but the `generate()` call would forward the entire string
to the Anthropic API. Combined with CR-01 this is a practical denial-of-service vector.

**Fix:**

```python
# app/schemas.py
class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32_000)
```

Choose a limit consistent with the model's context window (claude-haiku-4-5: 200k tokens
≈ 800k chars, but a reasonable service limit is far lower).

---

## Warnings

### WR-01: `datetime.datetime.utcnow` is deprecated — stores timezone-naive datetime into a timezone-aware column

**File:** `app/models.py:34`  
**Issue:** `default=datetime.datetime.utcnow` uses the deprecated (Python 3.12+) function that
returns a **naive** datetime with no tzinfo. The column is declared `DateTime(timezone=True)`,
which in Postgres maps to `TIMESTAMPTZ`. SQLAlchemy will pass a naive datetime to Postgres,
which will interpret it as local server time (not UTC) if the server timezone is not UTC —
producing silently wrong timestamps in the `usage_log` table.

**Fix:**

```python
# app/models.py
import datetime

# replace line 34:
default=lambda: datetime.datetime.now(datetime.timezone.utc),
```

---

### WR-02: `ClaudeProvider` instantiated fresh on every request — new HTTP connection pool per call

**File:** `app/providers/claude.py:33-36`, `app/routers/generate.py:23`  
**Issue:** `get_provider` is used as a FastAPI `Depends` with no scope caching (`use_cache`
defaults to `True` per-request, not per-app). Each request constructs a new `ClaudeProvider()`,
which constructs a new `anthropic.Anthropic(...)` (or `AsyncAnthropic`) and a new underlying
`httpx` client with a new connection pool. For the real LLM path this means no connection
reuse, adding TLS handshake overhead to every request.

**Fix:** Make `get_provider` return a module-level singleton or use FastAPI's app-state:

```python
# app/providers/claude.py
_provider: BaseProvider | None = None

def get_provider() -> BaseProvider:
    global _provider
    if _provider is None:
        _provider = ClaudeProvider() if settings.USE_REAL_LLM else MockProvider()
    return _provider
```

Or register it in `app/main.py` lifespan and attach to `app.state`.

---

### WR-03: Misconfiguration silenced — empty `ANTHROPIC_API_KEY` causes misleading 503 at runtime

**File:** `app/config.py:7`, `app/providers/claude.py:11`  
**Issue:** `ANTHROPIC_API_KEY` defaults to `""`. If `USE_REAL_LLM=true` but the key is not
set, `ClaudeProvider.__init__` succeeds (the Anthropic client accepts an empty string), and
every request silently fails with an Anthropic authentication error that surfaces to callers
as a generic `503 AI generation failed`. The misconfiguration is invisible until the first
real request, rather than at startup.

**Fix:** Validate at startup:

```python
# app/providers/claude.py
class ClaudeProvider(BaseProvider):
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set when USE_REAL_LLM=true"
            )
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
```

With WR-02's singleton fix, this raises at startup (in `get_provider`) rather than per-request.

---

### WR-04: `estimate_tokens` called before user existence check — 500 before 404

**File:** `app/routers/generate.py:26,35`  
**Issue:** `provider.estimate_tokens(body.prompt)` is called at line 26, before the database
lookup that checks whether `user_id` exists (line 34). If `estimate_tokens` raises (e.g., an
Anthropic API error for the real provider, or any unexpected exception for mock), the caller
receives a 500 instead of a 404. More practically: for a non-existent user, the service
performs an unnecessary (and potentially blocking, per CR-01) token estimation before
discovering the user does not exist.

**Fix:** Move the existence check before the estimation, or check user existence first in a
lightweight query without FOR UPDATE before the estimation call:

```python
# simplest fix: swap the order — check user exists first (fast DB lookup),
# then estimate tokens
async with db.begin():
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    estimated_tokens = provider.estimate_tokens(body.prompt)  # now inside TX
    ...
```

Note: pulling `estimate_tokens` into the TX holds the row lock during estimation. For the
real provider (CR-01 fixed) that is fine; for the sync provider it would block the lock
longer. Alternatively keep estimation outside but do a cheap existence pre-check:

```python
exists = await db.scalar(select(User.id).where(User.id == user_id))
if exists is None:
    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
estimated_tokens = provider.estimate_tokens(body.prompt)
# ... then re-fetch with FOR UPDATE in the reserve TX
```

---

## Info

### IN-01: `app/providers/__init__.py` is empty — unused module

**File:** `app/providers/__init__.py:1`  
**Issue:** The file contains no exports and no content. The router imports directly from
`app.providers.claude` and `app.providers.base`. The empty `__init__.py` works correctly
(Python package marker) but is worth noting if the intent was to expose a public API surface.

**Fix:** No action required unless you want to expose `get_provider` from the package root.

---

### IN-02: `UsageLog` `prompt_tokens` / `completion_tokens` columns typed `Integer` (32-bit)

**File:** `app/models.py:26-27`  
**Issue:** Both columns use `Integer` (max ~2.1 billion). For current Anthropic models
(200k input tokens, 8k output tokens) this is fine. However `estimated_credits` and
`actual_credits` correctly use `BigInteger`. If a future model or a different provider
supports larger context windows, `prompt_tokens` could overflow. Low risk today but
inconsistent with the credit columns.

**Fix:** Change to `BigInteger` for future-proofing, or leave as-is with a comment
acknowledging the ceiling.

---

_Reviewed: 2026-06-27_  
_Reviewer: Claude (gsd-code-reviewer)_  
_Depth: standard_
