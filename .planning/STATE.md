# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-27)

**Core value:** Correct per-user quota enforcement with Postgres row locking — race-safe under concurrent requests
**Current focus:** Phase 1 — Scaffold + User Config

## Current Position

Phase: 1 of 3 (Scaffold + User Config)
Plan: 0 of ? in current phase
Status: Ready to plan
Last activity: 2026-06-27 — Roadmap created

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

Key decisions affecting all phases:
- SELECT FOR UPDATE pattern: reserve on estimate, settle on actual (not hold lock during generation)
- Credits = total_tokens × multiplier (simple, auditable)
- MockProvider default; ClaudeProvider opt-in via USE_REAL_LLM=true env var
- 402 for quota exceeded (not 429 — semantic correctness over convention)

### Pending Todos

None yet.

### Blockers/Concerns

**Deadline:** 2026-06-29 9PM IST — ~58 hours from project start. Tight but achievable with 3 coarse phases.

## Session Continuity

Last session: 2026-06-27
Stopped at: Roadmap created, ready to plan Phase 1
Resume file: None
