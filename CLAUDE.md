<!-- GSD:project-start source:PROJECT.md -->
## Project

**AI Metering and Quota Service**

A FastAPI service that wraps an AI text generation layer and enforces per-user credit quotas. Users submit prompts, the service estimates cost, checks quota, generates text, then debits actual token usage converted to credits via a per-user multiplier. Built as a Terrabase interview submission due 2026-06-29 9PM IST.

**Core Value:** Correct per-user quota enforcement with Postgres row locking — the quota check, reservation, and debit must be race-safe even under concurrent requests from the same user.

### Constraints

- **Language/Framework**: Python + FastAPI — specified by assignment
- **Storage**: Postgres via Docker Compose — reviewer must be able to `docker-compose up` and run
- **Complexity**: Ponytail full — no abstractions beyond what's tested
- **Timeline**: ~58 hours total, ~10-15 hrs available
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
