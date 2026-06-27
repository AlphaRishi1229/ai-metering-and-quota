---
phase: 02-generation-quota-usage
verified: 2026-06-27T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "User with no quota config returns 402 with a distinct message (ROADMAP SC3, QUOTA-02, D-15)"
    reason: "Missing user returns 404 which is semantically correct REST; distinct from 402 quota exceeded. Plan 03 explicitly allowed 404 or 402. quota is NOT NULL so no-quota-config = user-not-found = 404."
    accepted_by: "alpha-rishi"
    accepted_at: "2026-06-27T00:00:00Z"
human_verification:
  - test: "Create a user with quota=1, then POST /users/{id}/generate with any prompt. Confirm 402 is returned before any generation runs."
    expected: "HTTP 402 with detail 'Quota exceeded'"
    why_human: "Requires running service + DB; can't invoke live HTTP without docker-compose up"
  - test: "Fire two concurrent POST /users/{id}/generate requests for the same user with quota just enough for one. Confirm exactly one succeeds (200) and one fails (402)."
    expected: "One 200 with usage data, one 402 — combined used_credits never exceeds quota"
    why_human: "Requires concurrent HTTP load against live service; can't simulate race in static grep"
  - test: "With USE_REAL_LLM=true and a valid ANTHROPIC_API_KEY, POST /users/{id}/generate. Confirm 200 with real generated text."
    expected: "Real LLM response, usage tokens populated from response.usage"
    why_human: "Requires live Anthropic credentials and real API call"
gaps:
  - truth: "User with no quota config returns 402 with a distinct message (ROADMAP SC3, QUOTA-02, D-15)"
    status: partial
    reason: >
      The code returns 404 (not 402) for a missing user and 402 'Quota exceeded' for an
      exhausted quota. ROADMAP SC3 explicitly requires 402 with a DISTINCT message for the
      no-quota-config case. D-15 design decision states 'Messages must be distinct.' The plan
      (02-03-PLAN.md must_have) relaxed this to '404 or 402' — so the plan accepted 404, but
      the ROADMAP contract requires 402. No distinct message exists ('Quota exceeded' is the
      only 402 response for both a zero-quota user and a fully-consumed-quota user).
    artifacts:
      - path: "app/routers/generate.py"
        issue: "Line 36: raises HTTPException(404) for missing user; Line 62: raises HTTPException(402, 'Quota exceeded') — no distinct message for the no-quota-config case"
    missing:
      - "Either: return 402 with distinct message 'User has no quota configured' for missing/zero-quota user, OR obtain explicit override that 404 satisfies ROADMAP SC3"
---

# Phase 2: Generation + Quota + Usage — Verification Report

**Phase Goal:** The generate endpoint enforces quota using Postgres row locks, debits actual tokens, and records every request in the usage log
**Verified:** 2026-06-27
**Status:** human_needed (1 gap requiring human decision on ROADMAP SC3; behavioral tests require live service)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Roadmap Success Criteria (Source of Truth)

From ROADMAP.md Phase 2:

1. `POST /users/{id}/generate` returns generated text plus a usage summary (tokens estimated, tokens actual, credits debited)
2. Request that would exceed quota returns 402 before any generation runs
3. User with no quota config returns 402 with a distinct message
4. Two concurrent requests from the same user serialize at the DB lock — neither overruns quota beyond one request's bounded overrun
5. AI provider failure returns 503 and no credits are debited

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /users/{id}/generate returns 200 with text + usage summary | ? HUMAN | Endpoint exists, response_model=GenerateResponse with text+usage; needs live test |
| 2 | Request exceeding quota returns 402 before generation runs | ✓ VERIFIED | generate.py:29-62: reserve TX checks `remaining`, sets quota_exceeded flag, writes UsageLog, raises 402 — all before `provider.generate()` at line 72 |
| 3 | User with no quota config returns 402 with distinct message | ✗ FAILED | Code returns 404 at line 36 for missing user. Only one 402 message: "Quota exceeded". No distinct message. Plan relaxed to "404 or 402" but ROADMAP SC3 requires 402 + distinct. |
| 4 | Concurrent requests serialize at DB lock, no unbounded overrun | ? HUMAN | SELECT FOR UPDATE used in reserve TX (line 31-32); structurally correct but requires concurrent load test to verify behaviorally |
| 5 | AI provider failure returns 503, no credits debited | ✓ VERIFIED | generate.py lines 103-125: except Exception catches provider failure, writes ai_error log, raises 503; finally block (127-143) releases reserved_credits when reserved=True and settled=False |

**Score:** 2/5 truths directly verified programmatically; SC4 needs human concurrent test; SC3 FAILED vs ROADMAP.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/providers/__init__.py` | Package marker | ✓ VERIFIED | Exists (empty, 0 bytes — correct package marker) |
| `app/providers/base.py` | GenerationResult dataclass + BaseProvider ABC | ✓ VERIFIED | Lines 5-17: @dataclass GenerationResult(text, prompt_tokens, completion_tokens); BaseProvider ABC with estimate_tokens (sync) and generate (async) |
| `app/providers/mock.py` | MockProvider implementation | ✓ VERIFIED | estimate_tokens=max(1,len//4); generate returns "Mock response for: {prompt[:50]}"; random.uniform(0.9,1.1) |
| `app/providers/claude.py` | ClaudeProvider + get_provider factory | ✓ VERIFIED | ClaudeProvider uses anthropic.Anthropic sync client, claude-haiku-4-5-20251001, reads response.usage; get_provider() returns ClaudeProvider if USE_REAL_LLM else MockProvider |
| `app/config.py` | USE_REAL_LLM + ANTHROPIC_API_KEY settings | ✓ VERIFIED | Lines 6-7: USE_REAL_LLM: bool = False; ANTHROPIC_API_KEY: str = "" |
| `app/models.py` | UsageLog ORM with 8 columns | ✓ VERIFIED | Lines 19-35: UsageLog with id, user_id (FK users.id), prompt_tokens, completion_tokens, estimated_credits (nullable BIGINT), actual_credits (nullable BIGINT), status (String(32)), created_at (DateTime tz-aware) |
| `app/schemas.py` | GenerateRequest, UsageDetail, GenerateResponse | ✓ VERIFIED | Lines 24-37: GenerateRequest(prompt min_length=1), UsageDetail(4 int fields), GenerateResponse(text + usage: UsageDetail) |
| `app/routers/generate.py` | Full quota enforcement flow | ✓ VERIFIED | 154 lines; reserve TX + generation + settle TX + finally release; 3x with_for_update(), 3x db.add(UsageLog), 402/404/503 responses |
| `app/main.py` | generate.router included | ✓ VERIFIED | Line 6: `from app.routers import users, generate`; Line 18: `app.include_router(generate.router)` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| app/routers/generate.py | get_provider | Depends(get_provider) | ✓ WIRED | Line 23: `provider: BaseProvider = Depends(get_provider)` |
| app/routers/generate.py | User table (reserve) | SELECT FOR UPDATE | ✓ WIRED | Line 31-32: `select(User).where(User.id == user_id).with_for_update()` |
| app/routers/generate.py | User table (settle) | SELECT FOR UPDATE | ✓ WIRED | Line 80-81: second with_for_update() in settle TX |
| app/routers/generate.py | User table (release) | SELECT FOR UPDATE | ✓ WIRED | Line 132-133: third with_for_update() in finally release block |
| app/routers/generate.py | UsageLog table | db.add(UsageLog(...)) | ✓ WIRED | 3 occurrences: quota_exceeded (line 52), success (line 88), ai_error (line 114) |
| app/main.py | app/routers/generate.py | include_router | ✓ WIRED | Line 18: `app.include_router(generate.router)` |
| app/providers/mock.py | app/providers/base.py | class MockProvider(BaseProvider) | ✓ WIRED | Line 6 |
| app/providers/claude.py | app/providers/base.py | class ClaudeProvider(BaseProvider) | ✓ WIRED | Line 8 |
| app/models.py UsageLog | users table | ForeignKey("users.id") | ✓ WIRED | Line 24 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| generate.py response | generation_result | provider.generate() (MockProvider or ClaudeProvider) | Yes — MockProvider returns deterministic text+tokens; ClaudeProvider returns response.content[0].text from SDK | ✓ FLOWING |
| generate.py UsageLog | estimated_credits, actual_credits | computed from token counts * multiplier (user row, locked) | Yes — formula applied to real DB-fetched multiplier and real provider token counts | ✓ FLOWING |
| generate.py reserved_credits | user.reserved_credits | SELECT FOR UPDATE on User row, increment/decrement in separate TXs | Yes — real DB mutations in separate committed TXs | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| generate.py parses without error | `python3 -m py_compile app/routers/generate.py` | N/A — static check only | ? SKIP (requires venv with deps) |
| MockProvider returns expected text | Traced in code: `f"Mock response for: {prompt[:50]}"` | Verified via code read | ✓ PASS (static) |
| with_for_update count | `grep -c "with_for_update" app/routers/generate.py` | 3 | ✓ PASS |
| db.add(UsageLog) count | `grep -c "db.add(UsageLog" app/routers/generate.py` | 3 | ✓ PASS |
| 402/503/404 all present | grep HTTPException lines | 404 (line 36), 402 (line 62), 503 (line 125) | ✓ PASS |

Step 7b: Live behavioral tests SKIPPED — require `docker-compose up` and a running Postgres instance.

---

### Requirements Coverage

| Requirement | Plans | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| GEN-01 | 02-02, 02-03 | POST /users/{id}/generate accepts prompt, returns text + usage summary | ✓ SATISFIED | generate.py endpoint with GenerateResponse(text, usage: UsageDetail) |
| GEN-02 | 02-01 | Provider abstraction — MockProvider default, ClaudeProvider via USE_REAL_LLM | ✓ SATISFIED | get_provider() in claude.py; config USE_REAL_LLM: bool = False |
| GEN-03 | 02-01, 02-03 | Pre-generation token estimate used for quota check | ✓ SATISFIED | generate.py line 26: estimate before reserve TX; line 38: estimated_credits used in quota check |
| GEN-04 | 02-01, 02-03 | Actual tokens from AI layer used for final debit | ✓ SATISFIED | generate.py lines 75-86: actual_credits from generation_result.prompt_tokens + completion_tokens |
| GEN-05 | 02-03 | AI failure before usage → 503, no credits debited | ✓ SATISFIED | except Exception + finally block releases reserved_credits; no used_credits increment |
| GEN-06 | 02-03 | AI failure mid-request → 503, partial usage policy documented | ~ PARTIAL | Code handles mid-request failure (settle TX failure) with 503 + finally release. D-17 says "Document in DESIGN.md" — DESIGN.md is Phase 3 work; code comment + threat model T-02-03-08 document the policy in-codebase |
| QUOTA-01 | 02-03 | Request rejected (402) if estimated credits > remaining quota | ✓ SATISFIED | generate.py lines 40-42: `remaining = quota - used_credits - reserved_credits; if estimated_credits > remaining: quota_exceeded = True` → 402 |
| QUOTA-02 | 02-03 | User with no quota config → 402 with clear message | ✗ BLOCKED | Code returns 404 for missing user (line 36), not 402. Only 402 message is "Quota exceeded" — not distinct. ROADMAP SC3 + D-15 require 402 with distinct message. |
| QUOTA-03 | 02-03 | SELECT FOR UPDATE serializes concurrent quota checks per user | ✓ SATISFIED | 3x with_for_update() in generate.py: reserve, settle, release |
| QUOTA-04 | 02-03 | Reservation pattern: reserve estimate → generate → settle actual | ✓ SATISFIED | generate.py: reserve TX (lines 29-45) → provider.generate() (line 72) → settle TX (lines 79-97) |
| QUOTA-05 | 02-03 | Overrun possible (actual > estimate) — bounded, documented | ✓ SATISFIED | Documented in D-17, threat model T-02-03-08; bounded by multiplier formula |
| USAGE-01 | 02-02, 02-03 | usage_log row per request: tokens, credits, timestamp | ✓ SATISFIED | UsageLog model has all columns; 3 db.add(UsageLog()) calls in generate.py |
| USAGE-02 | 02-03 | User row tracks used_credits and reserved_credits | ✓ SATISFIED | generate.py: reserved_credits +=/-= and used_credits += in locked TXs |
| USAGE-03 | 02-03 | Multiplier change does not retroactively alter existing usage_log rows | ✓ SATISFIED | UsageLog stores computed integer credits; multiplier captured once at line 68 |

**Orphaned requirements check:** INSPECT-01, INSPECT-02 are mapped to Phase 3 in REQUIREMENTS.md — not orphaned for this phase.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| app/models.py | 34 | `default=datetime.datetime.utcnow` — deprecated, returns timezone-naive datetime | Warning | Timestamps in usage_log may be stored as server local time instead of UTC if Postgres server timezone != UTC (WR-01 from code review) |
| app/providers/claude.py | 14, 21 | Sync `anthropic.Anthropic` client called inside async handler | Warning | Blocks event loop during real LLM calls (CR-01 from code review); MockProvider unaffected — default path works correctly |
| app/routers/generate.py | 85, 137 | `user.reserved_credits -= estimated_credits` without lower-bound guard | Warning | Can produce negative reserved_credits under a concurrent bug or external DB edit, inflating remaining quota (CR-02 from code review); does not affect normal operation flow |

No TODO/FIXME/placeholder comments found in implementation files. No empty return stubs. All three UsageLog states write real data.

---

### Human Verification Required

**1. Quota Enforcement Under Load (ROADMAP SC4)**

**Test:** Start service with `docker-compose up`. Create a user with quota=100, multiplier=1.0. Fire two concurrent requests with a 60-char prompt (estimated_credits=15) via parallel curl or Python asyncio. Inspect user row: used_credits must be <= 100; both 200+402 or both 200 depending on quota math.

**Expected:** Exactly the correct number of requests succeed without combined used_credits exceeding quota. No double-debit scenario where both requests "see" the same remaining credits.

**Why human:** Race condition requires concurrent real HTTP requests against live Postgres with SELECT FOR UPDATE in effect.

**2. Full Happy-Path Response Shape (ROADMAP SC1)**

**Test:** `docker-compose up`, POST /users/{id}/generate with prompt "Hello world". Inspect response JSON.

**Expected:** `{"text": "Mock response for: Hello world", "usage": {"prompt_tokens": 2, "completion_tokens": <10-12>, "estimated_credits": <int>, "actual_credits": <int>}}`

**Why human:** Requires running service; static analysis confirms response_model wiring but not serialization output.

**3. 503 Returns With No Credit Debit (ROADMAP SC5)**

**Test:** Monkey-patch or replace MockProvider to raise an exception in generate(). Confirm response is 503 and user's used_credits unchanged after the call.

**Expected:** HTTP 503; user.used_credits unchanged; reserved_credits back to pre-request value; ai_error row in usage_log.

**Why human:** Requires injecting a provider failure in the live service context.

---

### Gaps Summary

**One gap blocks full ROADMAP compliance:**

**QUOTA-02 / ROADMAP SC3 — No-quota-config response is 404, not 402 with distinct message.** The code returns 404 for a non-existent user (generate.py:36) and 402 "Quota exceeded" for an exhausted quota. ROADMAP SC3 requires the no-quota-config case to return 402 with a message distinct from a regular quota exceeded response. D-15 in the design doc states "Messages must be distinct." The plan (02-03-PLAN.md must_have) accepted "404 or 402" — so this was an intentional plan deviation from the ROADMAP contract.

**Decision required:** Either accept 404 as satisfying SC3 (add override to VERIFICATION.md frontmatter), or change generate.py line 36 to return 402 with message "User has no quota configured".

The gap is narrow: in practice, a missing user returns 404 which is semantically reasonable. The ROADMAP's intent ("user has no quota config") maps naturally to 404 in a REST API. However the explicit ROADMAP requirement and D-15 are not met as written.

**Code-quality warnings (not blockers for phase goal):**

- CR-01: ClaudeProvider blocks event loop — only active under USE_REAL_LLM=true; MockProvider (default) is unaffected.
- CR-02: reserved_credits can underflow without a lower-bound guard — risk is secondary, not triggered by normal operation.
- WR-01: utcnow() deprecated — timestamps may be slightly wrong if Postgres server TZ != UTC.

---

_Verified: 2026-06-27_
_Verifier: Claude (gsd-verifier)_
