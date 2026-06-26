# Phase 1: Scaffold + User Config - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 1-Scaffold + User Config
**Areas discussed:** Project layout, PATCH semantics, DB bootstrap, Validation rules

---

## Project Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Flat (main.py + models.py in root) | Simple, ponytail — everything visible at a glance | |
| Routers separated | app/main.py, app/routers/users.py, app/models.py, etc. Typical FastAPI structure. | ✓ |
| You decide | Claude picks based on project size | |

**User's choice:** Routers separated

| Option | Description | Selected |
|--------|-------------|----------|
| Top-level app/ package | app/main.py, app/routers/, etc. Standard for FastAPI. | ✓ |
| src/ layout | src/app/... Common in Python packages but uncommon for web services. | |
| You decide | Claude picks the conventional one | |

**User's choice:** Top-level app/ package

| Option | Description | Selected |
|--------|-------------|----------|
| Separate: models.py + schemas.py | SQLAlchemy models separate from Pydantic schemas | ✓ |
| Combined: models.py has both | Smaller surface, mixes concerns | |
| You decide | Claude picks standard practice | |

**User's choice:** Separate files

**Notes:** None — all choices were straightforward.

---

## PATCH Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Single PATCH, both fields optional | Body: {quota, multiplier} — either or both. RESTful. | ✓ |
| Two separate endpoints | PATCH /users/{id}/quota and PATCH /users/{id}/multiplier | |
| You decide | Claude picks conventional approach | |

**User's choice:** Single PATCH with optional fields

| Option | Description | Selected |
|--------|-------------|----------|
| Full updated user object | Returns same schema as GET/POST | ✓ |
| Just the changed fields | Less predictable for client | |
| 204 No Content | No body; caller must re-fetch | |

**User's choice:** Full updated user object

| Option | Description | Selected |
|--------|-------------|----------|
| 201 Created + full user object | Standard REST for creation | ✓ |
| 200 OK + full user object | Works but less semantically correct | |
| You decide | Claude picks standard | |

**User's choice:** 201 Created + full user object

**Notes:** None.

---

## DB Bootstrap

| Option | Description | Selected |
|--------|-------------|----------|
| create_all() on startup | SQLAlchemy Base.metadata.create_all() in startup event. Zero-config for reviewer. | ✓ |
| Alembic migrations | Industry standard but requires extra setup steps | |
| You decide | Claude picks based on reviewer requirements | |

**User's choice:** create_all() on startup

| Option | Description | Selected |
|--------|-------------|----------|
| healthcheck + depends_on in docker-compose.yml | Docker handles readiness, no retry in app code | ✓ |
| Retry loop in app startup | App polls Postgres until available | |
| You decide | Claude picks simpler approach | |

**User's choice:** healthcheck + depends_on

| Option | Description | Selected |
|--------|-------------|----------|
| pydantic-settings with .env file | Settings class reads from env vars or .env. FastAPI standard. | ✓ |
| Direct os.getenv() calls | Simpler but no type safety | |
| You decide | Claude picks pydantic-settings as FastAPI standard | |

**User's choice:** pydantic-settings with .env file

**Notes:** None.

---

## Validation Rules

| Option | Description | Selected |
|--------|-------------|----------|
| quota > 0 (positive integer) | Reject non-positive values with 422 | ✓ |
| quota >= 0 (allows zero) | Zero = disabled user | |
| No validation | Ponytail: no enforcement | |

**User's choice:** quota > 0

| Option | Description | Selected |
|--------|-------------|----------|
| float, multiplier > 0 | Any positive float. Stored as FLOAT in Postgres. | ✓ |
| Decimal (Python Decimal / NUMERIC) | Exact arithmetic, more complex | |
| You decide | Claude picks float for simplicity | |

**User's choice:** float, multiplier > 0

| Option | Description | Selected |
|--------|-------------|----------|
| 422 Unprocessable Entity | FastAPI default from Pydantic. No extra code. | ✓ |
| 400 Bad Request | Needs custom exception handler | |
| You decide | Claude uses 422 as natural behavior | |

**User's choice:** 422 Unprocessable Entity

**Notes:** None.

---

## Claude's Discretion

- `user_id` type (UUID vs auto-increment integer)
- Error message format for 404 responses
- Whether to pre-create `used_credits` and `reserved_credits` columns in Phase 1 (decided yes, to avoid schema changes in Phase 2)

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
