# Roadmap: AI Metering and Quota Service

## Overview

Three phases: scaffold the working app with user config storage, wire up generation with race-safe quota enforcement and usage tracking, then add inspection endpoints and ship the deliverable (tests, design doc, Docker, README).

## Phases

- [x] **Phase 1: Scaffold + User Config** - FastAPI app, DB models, CRUD for user quota/multiplier (completed 2026-06-26)
- [x] **Phase 2: Generation + Quota + Usage** - Generate endpoint, SELECT FOR UPDATE enforcement, usage log (completed 2026-06-27)
- [ ] **Phase 3: Inspection + Ship** - GET usage endpoints, pytest suite, design doc, Docker Compose, README

## Phase Details

### Phase 1: Scaffold + User Config

**Goal**: A running FastAPI app backed by Postgres where users can be created with quota and multiplier and those values can be updated
**Depends on**: Nothing (first phase)
**Requirements**: UCONF-01, UCONF-02, UCONF-03, UCONF-04
**Success Criteria** (what must be TRUE):

  1. `POST /users` creates a user row with quota and multiplier stored in Postgres
  2. `PATCH /users/{id}` updates quota or multiplier and the change is reflected immediately
  3. Request to a non-existent user returns 404 with a clear message
  4. App starts cleanly via `uvicorn` with Postgres connected (migrations applied)

**Plans**: 2 plans

Plans:

- [x] 01-01-PLAN.md — Project scaffold: package, config, async DB, ORM model, schemas, FastAPI app, Docker Compose
- [x] 01-02-PLAN.md — User endpoints: POST /users (201), PATCH /users/{id} (200/404), wired into main.py

### Phase 2: Generation + Quota + Usage

**Goal**: The generate endpoint enforces quota using Postgres row locks, debits actual tokens, and records every request in the usage log
**Depends on**: Phase 1
**Requirements**: GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, QUOTA-01, QUOTA-02, QUOTA-03, QUOTA-04, QUOTA-05, USAGE-01, USAGE-02, USAGE-03
**Success Criteria** (what must be TRUE):

  1. `POST /users/{id}/generate` returns generated text plus a usage summary (tokens estimated, tokens actual, credits debited)
  2. Request that would exceed quota returns 402 before any generation runs
  3. User with no quota config returns 402 with a distinct message
  4. Two concurrent requests from the same user serialize at the DB lock — neither overruns quota beyond one request's bounded overrun
  5. AI provider failure returns 503 and no credits are debited

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Provider package: config additions, BaseProvider ABC, MockProvider, ClaudeProvider, get_provider factory
- [x] 02-02-PLAN.md — UsageLog ORM model (models.py) + generate schemas (schemas.py)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Generate router with quota enforcement flow + wire into main.py

### Phase 3: Inspection + Ship

**Goal**: The service is reviewable end-to-end — inspection endpoints work, all 9 test scenarios pass, design doc and Docker Compose let a reviewer run and understand the project
**Depends on**: Phase 2
**Requirements**: INSPECT-01, INSPECT-02, INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):

  1. `GET /users/{id}/usage` returns current used, reserved, remaining, quota, multiplier
  2. `GET /users/{id}/usage/history` returns paginated usage log rows
  3. `docker-compose up` starts the service and Postgres; `curl` against it works with no manual setup
  4. `pytest` passes all 9 required scenarios from the spec
  5. DESIGN.md exists in repo and explains the concurrency model and key tradeoffs

**Plans**: 3 plans

Plans:
**Wave 1**

- [ ] 03-01-PLAN.md — Inspection schemas (UsageResponse, UsageLogEntry) + inspection router (GET /usage, GET /usage/history) + wire into main.py + test deps in requirements.txt

**Wave 2** *(blocked on Wave 1 completion; 03-02 and 03-03 run in parallel)*

- [ ] 03-02-PLAN.md — pytest suite: conftest.py with metering_test DB, all 9 test scenarios
- [ ] 03-03-PLAN.md — DESIGN.md + README.md at repo root

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scaffold + User Config | 2/2 | Complete   | 2026-06-26 |
| 2. Generation + Quota + Usage | 3/3 | Complete   | 2026-06-27 |
| 3. Inspection + Ship | 0/3 | Not started | - |
