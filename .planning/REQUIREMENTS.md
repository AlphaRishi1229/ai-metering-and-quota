# Requirements

## v1 Requirements

### User Config (UCONF)

- [ ] **UCONF-01**: Client can create a user with quota (credits) and multiplier
- [ ] **UCONF-02**: Client can update quota for an existing user
- [ ] **UCONF-03**: Client can update multiplier for an existing user
- [ ] **UCONF-04**: Request to non-existent user returns 404

### Generation (GEN)

- [ ] **GEN-01**: POST /users/{id}/generate accepts prompt, returns text + usage summary
- [ ] **GEN-02**: Provider abstraction — MockProvider default, ClaudeProvider via USE_REAL_LLM=true
- [ ] **GEN-03**: Pre-generation token estimate used for quota check
- [ ] **GEN-04**: Actual tokens from AI layer used for final debit
- [ ] **GEN-05**: AI failure before usage → 503, no credits debited
- [ ] **GEN-06**: AI failure mid-request → 503, partial usage policy documented

### Quota Enforcement (QUOTA)

- [ ] **QUOTA-01**: Request rejected (402) if estimated credits > remaining quota
- [ ] **QUOTA-02**: User with no quota config → 402 with clear message
- [ ] **QUOTA-03**: Postgres SELECT FOR UPDATE serializes concurrent quota checks per user
- [ ] **QUOTA-04**: Reservation pattern: reserve estimate → generate → settle actual
- [ ] **QUOTA-05**: Overrun possible (actual > estimate) — bounded, documented

### Usage Tracking (USAGE)

- [ ] **USAGE-01**: usage_log row per request: prompt_tokens, completion_tokens, estimated_credits, actual_credits, timestamp
- [ ] **USAGE-02**: User row tracks used_credits and reserved_credits
- [ ] **USAGE-03**: Multiplier change does not retroactively alter existing usage_log rows

### Inspection (INSPECT)

- [ ] **INSPECT-01**: GET /users/{id}/usage returns used, reserved, remaining, quota, multiplier
- [ ] **INSPECT-02**: GET /users/{id}/usage/history returns paginated usage_log rows

### Infrastructure (INFRA)

- [ ] **INFRA-01**: Docker Compose: Postgres + app, single docker-compose up
- [ ] **INFRA-02**: pytest suite covers all 9 required scenarios from spec
- [ ] **INFRA-03**: Design document (DESIGN.md in repo)
- [ ] **INFRA-04**: README with setup + test instructions

## v2 (Deferred)

- Quota period reset (monthly rollover)
- Multi-tenant auth / API keys
- Rate limiting beyond quota
- Async generation / webhooks
- Admin UI

## Out of Scope

- Redis or second data store — Postgres row lock is sufficient
- Per-endpoint credit pricing — flat token-based model only
- Soft quota warnings — hard block at limit only

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UCONF-01 | Phase 1 | Pending |
| UCONF-02 | Phase 1 | Pending |
| UCONF-03 | Phase 1 | Pending |
| UCONF-04 | Phase 1 | Pending |
| GEN-01 | Phase 2 | Pending |
| GEN-02 | Phase 2 | Pending |
| GEN-03 | Phase 2 | Pending |
| GEN-04 | Phase 2 | Pending |
| GEN-05 | Phase 2 | Pending |
| GEN-06 | Phase 2 | Pending |
| QUOTA-01 | Phase 2 | Pending |
| QUOTA-02 | Phase 2 | Pending |
| QUOTA-03 | Phase 2 | Pending |
| QUOTA-04 | Phase 2 | Pending |
| QUOTA-05 | Phase 2 | Pending |
| USAGE-01 | Phase 2 | Pending |
| USAGE-02 | Phase 2 | Pending |
| USAGE-03 | Phase 2 | Pending |
| INSPECT-01 | Phase 3 | Pending |
| INSPECT-02 | Phase 3 | Pending |
| INFRA-01 | Phase 3 | Pending |
| INFRA-02 | Phase 3 | Pending |
| INFRA-03 | Phase 3 | Pending |
| INFRA-04 | Phase 3 | Pending |
