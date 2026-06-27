---
phase: 02-generation-quota-usage
fixed_at: 2026-06-27T00:00:00Z
review_path: .planning/phases/02-generation-quota-usage/02-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-06-27  
**Source review:** .planning/phases/02-generation-quota-usage/02-REVIEW.md  
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (3 Critical + 4 Warning; Info excluded by fix_scope)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: Synchronous Anthropic SDK called inside async handler

**Files modified:** `app/providers/claude.py`  
**Commit:** 079cf3d  
**Applied fix:** Switched `anthropic.Anthropic` to `anthropic.AsyncAnthropic`; added `await` to `self._client.messages.create()`; replaced the blocking `count_tokens` network call in `estimate_tokens` with `max(1, len(prompt) // 4)` approximation.

### WR-02: ClaudeProvider instantiated fresh on every request

**Files modified:** `app/providers/claude.py`  
**Commit:** 079cf3d (same commit as CR-01 — both touch claude.py)  
**Applied fix:** Added a module-level `_provider: BaseProvider | None = None` singleton; `get_provider()` now initialises on first call and returns the cached instance on all subsequent calls.

### WR-03: Empty ANTHROPIC_API_KEY silenced until first request

**Files modified:** `app/providers/claude.py`  
**Commit:** 079cf3d (same commit as CR-01/WR-02 — same file)  
**Applied fix:** `ClaudeProvider.__init__` now raises `ValueError` immediately if `settings.ANTHROPIC_API_KEY` is falsy, surfacing the misconfiguration at startup (via the singleton) rather than per-request.

### CR-02: reserved_credits can underflow to a negative value

**Files modified:** `app/routers/generate.py`  
**Commit:** 3074be3  
**Applied fix:** Both decrement sites now use `max(0, user.reserved_credits - estimated_credits)` — the settle TX at line 85 and the finally-block release at line 137.

### CR-03: No maximum prompt length

**Files modified:** `app/schemas.py`  
**Commit:** aa9352a  
**Applied fix:** Added `max_length=32_000` to `GenerateRequest.prompt` Field, capping input before it reaches estimation or the Anthropic API.

### WR-01: datetime.utcnow deprecated — timezone-naive datetime

**Files modified:** `app/models.py`  
**Commit:** 1394639  
**Applied fix:** Replaced `default=datetime.datetime.utcnow` with `default=lambda: datetime.datetime.now(datetime.timezone.utc)` — now returns a timezone-aware UTC datetime matching the `DateTime(timezone=True)` column.

### WR-04: estimate_tokens called before user existence check

**Files modified:** `app/routers/generate.py`  
**Commit:** 642d4dc  
**Applied fix:** Added a cheap `SELECT User.id` pre-check before `estimate_tokens`; non-existent users receive 404 immediately without triggering token estimation. The FOR UPDATE guard inside the reserve TX is retained as a safety net.

---

_Fixed: 2026-06-27_  
_Fixer: Claude (gsd-code-fixer)_  
_Iteration: 1_
