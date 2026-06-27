---
phase: 03-inspection-ship
plan: 03
subsystem: docs
tags: [documentation, design, readme, concurrency, quota]

# Dependency graph
requires:
  - phase: 03-inspection-ship
    plan: 01
    provides: inspection endpoints (GET /usage, GET /usage/history)
  - phase: 02-generate-quota
    provides: generate endpoint, SELECT FOR UPDATE pattern, provider abstraction
provides:
  - DESIGN.md at repo root — full design document with concurrency model, Alice example, ASCII diagram, tradeoffs, endpoint reference
  - README.md at repo root — Quick Start, env vars table, test instructions, sample curls for all 5 endpoints
affects: [reviewer, ship]

# Tech tracking
tech-stack:
  added: []
  patterns: [documentation-only plan, no code changes]

key-files:
  created: [DESIGN.md, README.md]
  modified: []

key-decisions:
  - "DESIGN.md reproduces PROJECT.md Alice example verbatim including used=1178, remaining=22"
  - "README.md points to metering_test DB (not metering) for tests to avoid dev/test interference"
  - "DESIGN.md explains 402 vs 429 tradeoff and lock duration rationale (lock held ~1ms, not during generation)"

requirements-completed: [INFRA-03, INFRA-04]

# Metrics
duration: 2min
completed: 2026-06-27
---

# Phase 03 Plan 03: DESIGN.md and README.md Summary

**DESIGN.md (10-section design doc with SELECT FOR UPDATE concurrency model, Alice example verbatim, ASCII diagram, provider abstraction, 402 vs 429 tradeoff, known undercharge limitation) and README.md (docker-compose Quick Start, env vars table, metering_test test instructions, sample curls for all 5 endpoints)**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-06-27T12:35:43Z
- **Completed:** 2026-06-27T12:37:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- DESIGN.md: overview, ASCII architecture diagram, T=0/T=1/T=2 concurrency sequence, Alice example (matches PROJECT.md verbatim), credit formula, provider abstraction (MockProvider/ClaudeProvider), 4 key tradeoffs, known limitation (undercharge on settle failure), endpoint reference table, out-of-scope section. 1285 words.
- README.md: project title + one-liner, docker-compose Quick Start, environment variables table (DATABASE_URL/USE_REAL_LLM/ANTHROPIC_API_KEY), test instructions with metering_test DB creation, sample curls for all 5 endpoints, link to DESIGN.md.

## Task Commits

1. **Task 1: Write DESIGN.md at repo root** - `15609de` (docs)
2. **Task 2: Write README.md at repo root** - `910c2df` (docs)

## Files Created/Modified

- `DESIGN.md` — New file: 182 lines, 10 sections, 1285 words
- `README.md` — New file: 81 lines, Quick Start, env vars, test instructions, 5 endpoint curls

## Decisions Made

- DESIGN.md reproduces the Alice example from PROJECT.md verbatim (quota=1000, multiplier=2.0, used=800, 44-char prompt, 402 then quota raise to 1200, settle to used=1178 remaining=22).
- `metering_test` DB is specified explicitly in test instructions to prevent test runs from modifying the `metering` dev database.
- Known limitation section documents the undercharge scenario (DB crash between T=1 and T=2) and notes that the `finally` block releases the reservation.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

No new security surface introduced — documentation-only plan.

## Self-Check: PASSED

- `DESIGN.md` exists at repo root: FOUND
- `README.md` exists at repo root: FOUND
- `grep -c "SELECT FOR UPDATE" DESIGN.md` returns 2 (>= 1): PASS
- `grep "alice\|Alice" DESIGN.md` returns 3 matches: PASS
- `grep "1178" DESIGN.md` matches (Alice settle value): PASS
- `grep "docker-compose up" README.md` returns 2 matches: PASS
- `grep "pytest" README.md` matches: PASS
- `wc -w DESIGN.md` returns 1285 (>= 400): PASS
- `grep -c "/users/" DESIGN.md` returns 10 (>= 5): PASS
- Commit 15609de exists: PASS
- Commit 910c2df exists: PASS

---
*Phase: 03-inspection-ship*
*Completed: 2026-06-27*
