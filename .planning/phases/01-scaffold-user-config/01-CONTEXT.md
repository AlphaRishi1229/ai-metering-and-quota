# Phase 1: Scaffold + User Config - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

A running FastAPI app backed by Postgres where users can be created with quota (credits) and multiplier, and those values can be updated. No generation, no quota enforcement, no usage tracking — that is Phase 2.

Deliverables:
- `POST /users` — create a user with quota and multiplier
- `PATCH /users/{id}` — update quota and/or multiplier
- 404 for requests to non-existent users
- App starts cleanly via uvicorn with Postgres connected and tables created

</domain>

<decisions>
## Implementation Decisions

### Project Layout
- **D-01:** Use a top-level `app/` package (not `src/`). Entry point: `app/main.py`.
- **D-02:** Routers separated: `app/routers/users.py` (and later `app/routers/generate.py` etc.).
- **D-03:** SQLAlchemy ORM models in `app/models.py`, Pydantic request/response schemas in `app/schemas.py`.
- **D-04:** DB session factory in `app/database.py`.

### PATCH Semantics
- **D-05:** Single `PATCH /users/{id}` endpoint. Body accepts both `quota` and `multiplier` as optional fields — either or both may be provided.
- **D-06:** `PATCH /users/{id}` returns 200 + the full updated user object (same schema as GET/POST response).
- **D-07:** `POST /users` returns 201 Created + the full created user object.

### DB Bootstrap
- **D-08:** `Base.metadata.create_all(bind=engine)` called in a FastAPI `startup` event (or `@asynccontextmanager` lifespan). No Alembic — reviewer runs `docker-compose up` and tables exist.
- **D-09:** Docker Compose uses `healthcheck` on the Postgres container and `depends_on: condition: service_healthy` on the app container. No retry logic in app code.
- **D-10:** App config via `pydantic-settings` (`BaseSettings` subclass). Reads from env vars or `.env` file. Key var: `DATABASE_URL` (e.g., `postgresql+asyncpg://...`).

### Validation Rules
- **D-11:** `quota` must be a positive integer (> 0). Pydantic `Field(gt=0)`. FastAPI returns 422 automatically on violation.
- **D-12:** `multiplier` must be a positive float (> 0). Pydantic `Field(gt=0.0)`. Stored as `FLOAT` in Postgres (not NUMERIC — token estimates are already approximate).
- **D-13:** Invalid input → 422 Unprocessable Entity (FastAPI default from Pydantic validation). No custom 400 handler needed.

### Claude's Discretion
- Field names on the user object (e.g., `used_credits`, `reserved_credits` — needed in Phase 2 but the column should exist from Phase 1 for schema consistency).
- Whether to create a `user_id` as UUID or auto-increment integer.
- Error message format for 404 (just a clear JSON message).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project decisions and constraints
- `.planning/PROJECT.md` — Key Decisions table (SELECT FOR UPDATE pattern, credit formula, provider abstraction, SQLAlchemy + asyncpg choice, 402 semantics). MUST read before designing any data model.
- `.planning/REQUIREMENTS.md` — UCONF-01 through UCONF-04 (exact wording of Phase 1 requirements).

### Phase scope
- `.planning/ROADMAP.md` — Phase 1 success criteria and boundaries.

No external specs — requirements fully captured in decisions above and the referenced planning files.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — fresh codebase.

### Established Patterns
- None yet. Phase 1 sets the patterns that Phases 2 and 3 will follow.

### Integration Points
- Phase 2 will add `app/routers/generate.py` and `app/providers/`. It expects `app/models.py` to already have the `User` table with `used_credits` and `reserved_credits` columns (even though Phase 1 doesn't use them).

</code_context>

<specifics>
## Specific Ideas

- The `User` table should include `used_credits` (default 0) and `reserved_credits` (default 0) even in Phase 1, since Phase 2 needs them and adding columns mid-run is unnecessary friction.
- The user response schema should expose: `id`, `quota`, `multiplier`, `used_credits`, `reserved_credits`.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Scaffold + User Config*
*Context gathered: 2026-06-27*
