---
status: partial
phase: 02-generation-quota-usage
source: [02-VERIFICATION.md]
started: 2026-06-27T00:00:00Z
updated: 2026-06-27T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Quota exceeded returns 402 before generation runs
expected: POST /users/{id}/generate with quota=1 returns HTTP 402 with detail 'Quota exceeded'
result: [pending]

### 2. Concurrent requests serialize correctly — no over-quota
expected: Two concurrent POSTs for same user with quota for only one: exactly one 200, one 402; combined used_credits never exceeds quota
result: [pending]

### 3. Real LLM generation (USE_REAL_LLM=true)
expected: Valid ANTHROPIC_API_KEY + real prompt returns 200 with actual generated text and token counts
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
