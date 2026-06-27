---
phase: 02-generation-quota-usage
plan: "01"
subsystem: providers
tags: [provider-abstraction, mock-provider, claude-provider, config]
dependency_graph:
  requires: []
  provides: [app/providers/base.py, app/providers/mock.py, app/providers/claude.py, get_provider]
  affects: [app/routers/generate.py]
tech_stack:
  added: [anthropic>=0.30.0]
  patterns: [ABC provider abstraction, dataclass result type, env-driven feature flag]
key_files:
  created:
    - app/providers/__init__.py
    - app/providers/base.py
    - app/providers/mock.py
    - app/providers/claude.py
  modified:
    - app/config.py
    - requirements.txt
decisions:
  - "get_provider() lives in claude.py (not __init__.py) to avoid circular imports between mock and claude submodules"
  - "estimate_tokens is sync; generate is async — consistent with SDK patterns (count_tokens is fast/sync, generate has network I/O)"
  - "MockProvider completion_tokens uses max(10, ...) floor to prevent zero-token results"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-06-27"
---

# Phase 2 Plan 01: Provider Package Summary

Provider abstraction package with MockProvider (default) and ClaudeProvider (USE_REAL_LLM=true), plus Settings extension for LLM toggles.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend config + create providers base | 603865a | app/config.py, app/providers/__init__.py, app/providers/base.py |
| 2 | MockProvider + ClaudeProvider + get_provider | 1da12c9 | app/providers/mock.py, app/providers/claude.py, requirements.txt |

## What Was Built

- `GenerationResult` dataclass: `text`, `prompt_tokens`, `completion_tokens`
- `BaseProvider` ABC: sync `estimate_tokens()` + async `generate()`
- `MockProvider`: char/4 token heuristic, ±10% completion variance, deterministic text prefix
- `ClaudeProvider`: `anthropic.Anthropic` sync client, `claude-haiku-4-5-20251001`, reads `response.usage`
- `get_provider()` factory in `claude.py`: returns `ClaudeProvider` if `USE_REAL_LLM` else `MockProvider`
- `Settings` extended with `USE_REAL_LLM: bool = False` and `ANTHROPIC_API_KEY: str = ""`

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface

T-02-01-01 (ANTHROPIC_API_KEY disclosure): Key read from env/`.env` only; `.env` confirmed in `.gitignore`. No hardcoded key anywhere.

T-02-01-03 (sync estimate_tokens in async path): Documented with `ponytail:` comment in `ClaudeProvider.__init__` — upgrade path is `AsyncAnthropic` if throughput matters.

## Known Stubs

None — MockProvider is intentional, not a stub. `get_provider()` wires correctly to `USE_REAL_LLM`.

## Self-Check: PASSED

- app/providers/__init__.py: exists
- app/providers/base.py: exists with GenerationResult and BaseProvider
- app/providers/mock.py: exists with MockProvider
- app/providers/claude.py: exists with ClaudeProvider and get_provider
- app/config.py: USE_REAL_LLM and ANTHROPIC_API_KEY present
- requirements.txt: anthropic>=0.30.0 present
- Commits 603865a and 1da12c9 verified in git log
