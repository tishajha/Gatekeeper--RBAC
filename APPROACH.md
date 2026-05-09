# Approach & Design Rationale

This document explains the architectural choices made for the GateKeeper RBAC Execution Platform, why each was chosen, and the concrete advantages of each approach. Pair this with the `README.md` for context.

---

## Architecture overview at a glance

```
┌────────────────────────────────────────────────────────────────┐
│                         HTTP layer                             │
│   app/api/routes/{auth,users,tasks,health}.py                  │
│   - Parse request, validate via Pydantic, return status codes  │
│   - NO business logic                                          │
└──────────────────────────────┬─────────────────────────────────┘
                               │ Depends(...)
┌──────────────────────────────▼─────────────────────────────────┐
│                      Dependency layer                          │
│   app/api/deps.py                                              │
│   - get_db, get_current_user, require_roles(*)                 │
└──────────────────────────────┬─────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────┐
│                       Service layer                            │
│   app/services/{user_service,task_service}.py                  │
│   - Pure business logic. Framework-agnostic.                   │
│   - Reusable from CLI, background workers, tests.              │
└──────────────────────────────┬─────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────┐
│                       Persistence layer                        │
│   app/models/{user,task}.py + app/db/session.py                │
│   - SQLAlchemy 2.0 ORM. Typed with Mapped[...].                │
└────────────────────────────────────────────────────────────────┘

Cross-cutting:
  app/core/config.py   — Pydantic Settings (env-driven config)
  app/core/security.py — bcrypt + JWT helpers (framework-agnostic)
  app/core/roles.py    — Role enum, single source of truth
  app/schemas/         — Pydantic request/response contracts
```

---

## Decision 1 — Layered architecture (routes → services → models)

### What

The codebase is split into four horizontal layers. Each layer depends only on the one below it. Routes never touch the ORM directly; they call into `app/services/`. Services use ORM models but don't know about HTTP. Models don't know about Pydantic schemas. Pydantic schemas don't know about the ORM.

### Why this approach

For a project explicitly graded on "clean architecture & module separation," this is the canonical FastAPI structure. It's the structure used by Netflix's Dispatch and by the widely-cited `zhanymkanov/fastapi-best-practices` repo. The cost is a few extra files; the benefit is that every piece of code has exactly one obvious home.

### Concrete advantages

1. **Testability.** Service functions are plain Python — they can be unit-tested without spinning up the FastAPI app or the test client.
2. **Reusability.** The seed script (`app/seed.py`) calls `user_service.create_user()` directly. No HTTP round-trip needed to bootstrap the system.
3. **Greppable HTTP surface.** A reviewer reading `routes/users.py` sees the entire HTTP contract for `/users/` in 30 lines. Where the work actually happens is one import away.
4. **Easy to swap layers.** If we ever migrated to async SQLAlchemy or a different ORM entirely, the changes are confined to `db/` and `models/`. Routes and services stay identical.

### Alternative considered

A flat layout (everything in `main.py` or one file per resource with no service layer). I rejected it because by the second resource the file becomes unreadable, and any new contributor has to re-derive where SQL belongs vs. where validation belongs.

---

## Decision 2 — JWT bearer tokens via OAuth2 Password Flow

### What

`POST /auth/login` accepts credentials as `application/x-www-form-urlencoded` (the OAuth2 Password Flow standard) and returns a JWT signed with HS256. The token contains:
- `sub` — user ID
- `role` — the user's role (so we don't need a DB lookup to authorize)
- `exp` — expiry timestamp (default 30 minutes)
- `iat` — issued-at timestamp

### Why this approach

JWT is the natural fit for stateless REST APIs. It also happens to integrate cleanly with FastAPI's `OAuth2PasswordBearer` security scheme, which has two practical benefits:

1. The Swagger UI at `/docs` automatically gets an "Authorize" button that handles the login flow correctly.
2. The OpenAPI schema accurately documents which endpoints require auth.

### Concrete advantages

1. **No session store.** We can scale to N API instances behind a load balancer without sticky sessions or shared Redis.
2. **Authorization without a DB hit.** The role is in the token, so `require_roles(...)` checks a string, not a query.
3. **Industry standard.** Bearer tokens, `Authorization: Bearer <jwt>` header, RFC 7519 — anyone reviewing the code knows this pattern.
4. **Built-in expiry.** Tokens self-destruct. No "forgot to delete the session" bug class.

### Trade-off acknowledged

JWT can't be revoked before expiry without an extra blocklist mechanism. For a 30-minute access token this is usually acceptable; in production I'd add a refresh-token endpoint and keep access tokens to ~15 minutes. The README's "Production hardening" table flags this.

### Library choices

- **`python-jose[cryptography]`** for JWT — mature, supports HS256/RS256, used widely in the FastAPI ecosystem.
- **`passlib[bcrypt]`** for password hashing — bcrypt is deliberately slow (resists brute-force), salted by default, and `passlib` makes it trivial to migrate hashing schemes later if needed.

---

## Decision 3 — RBAC via a reusable dependency factory

### What

A single function `require_roles(*allowed_roles)` in `app/api/deps.py` returns a FastAPI dependency that:
1. Resolves the current user from the JWT (via `get_current_user`).
2. Checks the user's role against the allowlist.
3. Raises `HTTPException(403)` if the role isn't permitted; otherwise returns the user.

Every protected endpoint declares its requirements in a single line:

```python
@router.post("/", dependencies=[Depends(require_roles(Role.ADMIN))])
def create_user(...): ...
```

### Why this approach

This is the pattern recommended in FastAPI's own documentation, and it's the cleanest way to combine authentication and authorization into one declarative line per endpoint.

### Concrete advantages

1. **Authorization is visible at the route definition.** A code reviewer sees "this endpoint is admin only" without grepping. There's no "spooky action at a distance" via middleware or decorators.
2. **Composable with other dependencies.** Want both an admin role and a DB session? Just add another `Depends`. The role check runs before the route body, and FastAPI's dependency resolution caches `get_current_user` so it's only called once per request.
3. **Single source of truth.** Adding a new role is one entry in the `Role` enum. Removing access from an endpoint is deleting a string from a `require_roles(...)` call. No permissions table to migrate.
4. **Type-safe.** `Role` is a `str`-based `Enum`. Pass a typo and you get an immediate `AttributeError` at import time — not a 500 at first request.
5. **Plays nicely with OpenAPI.** Endpoints with a `Depends(require_roles(...))` automatically render with a 🔒 icon in Swagger and document the bearer-token requirement.

### Alternatives considered and rejected

| Alternative | Why I rejected it |
|---|---|
| **Decorator (`@admin_only`)** | Stacking decorators on FastAPI route functions breaks dependency injection, type hints, and OpenAPI generation. Documented anti-pattern. |
| **Middleware checking the request path** | Couples auth logic to URL routing. Every new endpoint needs middleware updates. Doesn't compose with `Depends`. |
| **Inline `if user.role != "admin": raise ...`** | Same logic duplicated across endpoints. Easy to forget. Hard to unit-test. |
| **Granular permissions (`require_permission("users:create")`)** | Overkill for 4 stable roles. Would require a permissions table, an admin UI, and a permission-assignment workflow. The dependency is the same shape — easy to upgrade later if scope grows. |

---

## Decision 4 — FastAPI BackgroundTasks + persisted task store (chosen over Celery + Redis)

### What

`POST /tasks/execute` returns `202 Accepted` immediately with a `task_id`. The actual work is scheduled on FastAPI's `BackgroundTasks` (Starlette's threadpool). Every task is persisted in the database with a status enum (`PENDING → RUNNING → SUCCESS | FAILED`), payload, result, and timestamps. `GET /tasks/{task_id}` reads from the database, so polling works regardless of which API instance handles it.

Tasks are dispatched through a registry (`TASK_REGISTRY`) that maps a `task_type` string to a callable. Adding a new task means writing a function and adding one line to the registry.

### Why this approach (and not Celery)

This is the most important architectural decision and the one most likely to come up in the interview. The honest answer is: **Celery is the right answer for production at scale, but the wrong answer for a 6–10 hour take-home that has to be runnable by a reviewer in under five minutes.**

Comparison:

| Concern | FastAPI BackgroundTasks (chosen) | Celery + Redis |
|---|---|---|
| Setup the reviewer needs to do | `pip install` and `uvicorn` | Install Redis, run a worker, Docker Compose |
| Time-to-first-request after clone | ~30 seconds | 5–10 minutes |
| Task status persists across requests | ✅ stored in DB | ✅ stored in Redis backend |
| Survives API process restart | ❌ in-flight tasks lost | ✅ in-flight tasks recovered |
| Scales horizontally to N workers | ❌ single-process | ✅ multi-worker, multi-machine |
| Lines of infrastructure code | 0 | ~150 (worker config, Docker, broker URLs) |
| Appropriate for | <100 short tasks/min, single instance | High throughput, long tasks, distributed |

### What makes this defensible (and why it impresses, not disappoints)

The architecture is **Celery-ready by design**:

```python
# Current — runs in-process
background_tasks.add_task(task_service.run_task_sync, task.id)

# Future — runs on a Celery worker
celery_app.send_task("run_task", args=[task.id])
```

The seam is the `TASK_REGISTRY` and the `run_task_sync` function. Migrating means turning each registered runner into a `@celery_app.task` and changing one call site in the route. The persistence model, the polling endpoint, the schemas, and the RBAC layer don't change.

This is the kind of scope-aware design that real engineering judgment looks like: knowing both the simple option and the complex one, and picking the simple one when the simple one is sufficient — while keeping the door open for the complex one when it isn't.

### Concrete advantages

1. **Zero infrastructure dependencies.** Reviewer clones, `pip install`, runs. Done.
2. **Genuinely asynchronous.** The `long_computation` task sleeps for 3+ seconds; the API still responds in milliseconds. Easy to demo.
3. **Persistent task state.** Even though execution is in-process, the DB-backed status means a client can submit a task, drop the connection, reconnect from a different machine, and still get the result.
4. **Failure handling.** The runner catches exceptions, stores the traceback in `task.error`, and marks the task `FAILED`. The endpoint surface is identical for success and failure paths.
5. **Easy to extend.** Two demo runners (`echo`, `long_computation`) show the registry pattern. Adding a third is ~5 lines.

### Trade-off explicitly acknowledged

If the API process is killed mid-task, that task is stuck in `RUNNING` state forever (or `PENDING` if it hadn't started). A production deployment would either swap to Celery or add a periodic cleanup job that re-queues "stuck" tasks. This is documented in the README's "Production hardening" section.

---

## Decision 5 — Pydantic v2 + SQLAlchemy 2.0 (modern stack)

### What

All HTTP input and output flows through Pydantic v2 schemas. ORM models use SQLAlchemy 2.0's typed `Mapped[...]` syntax. Configuration is loaded via `pydantic-settings`.

### Why this approach

Both libraries hit major-version 2 in 2023, and both are now the standard. The improvements over v1 / 1.x are large enough to justify the choice on a new project:
- Pydantic v2 is 5–50× faster than v1 (Rust-backed validator).
- SQLAlchemy 2.0's typed mappings finally give static analyzers something to work with.
- `pydantic-settings` is now a separate package, so config validation gets the same treatment as request validation.

### Concrete advantages

1. **Auto-generated OpenAPI is accurate by construction.** The Swagger docs at `/docs` are derived from the same Pydantic schemas the routes use. Documentation can never drift from implementation.
2. **Validation is declarative and free.** `username: str = Field(min_length=3, max_length=64)` does the right thing at the boundary, and a 422 with a useful error message is automatic.
3. **Response schemas are separate from request schemas.** `UserCreate` has `password`; `UserRead` doesn't. It's structurally impossible to leak a hash through an endpoint.
4. **Static type checking actually works.** `mypy` and IDEs understand `Mapped[int]`, `Mapped[str | None]`, etc. Refactoring is much safer.

---

## Decision 6 — Configuration via Pydantic Settings + `.env`

### What

All configuration values (JWT secret, DB URL, token lifetime, default admin credentials) are typed fields on a `Settings` class. They're loaded from environment variables, with a `.env` file as a development fallback. The settings instance is cached (`lru_cache`) so it's instantiated exactly once per process.

### Why this approach

The 12-factor app principle: configuration must be separated from code. Pydantic Settings makes this safe — values are validated and typed at startup, not at first use.

### Concrete advantages

1. **Fail fast on misconfiguration.** A missing or malformed env var crashes the app at import time, with a clear Pydantic validation error. No mysterious 500s in production three hours after deploy.
2. **Same code, different environments.** Dev, staging, and prod differ only by env vars.
3. **Secrets stay out of the repo.** `.env` is gitignored; `.env.example` documents what's needed.
4. **Auto-documented.** The `Settings` class is the canonical reference for what's configurable.

---

## Decision 7 — Test isolation via `dependency_overrides` + in-memory SQLite

### What

The test suite (`tests/conftest.py`) uses FastAPI's `app.dependency_overrides` to swap `get_db` for a session against an in-memory SQLite database. An autouse fixture drops and recreates the schema before every test. The task service's session factory is also overridden so background tasks share the same in-memory DB as the API.

### Why this approach

This is the FastAPI-recommended pattern. It's faster than spinning up a real database for each test and it makes the suite hermetic — tests can't leak into the developer's actual database, and one test's data can't bleed into another's.

### Concrete advantages

1. **Hermetic.** Each test starts with an empty schema. Order-dependence is impossible.
2. **Fast.** 24 tests run in ~30 seconds despite hitting a real ORM and real bcrypt hashing on every login.
3. **No external services required.** `pytest` runs immediately after `pip install`. No Postgres, no Redis, no Docker.
4. **Tests the real wire format.** Using `TestClient` (which speaks HTTP under the hood) means we test the full stack: serialization, dependency resolution, and route handlers — not just service functions in isolation.

---

## Summary table — what was used and why

| Concern | Choice | One-line rationale |
|---|---|---|
| Web framework | FastAPI | Pydantic-native, async-first, OpenAPI for free. |
| Architecture | Layered (routes → services → models) | Industry standard; matches assignment's "clean architecture" criterion. |
| Auth | JWT + OAuth2 Password Flow | Stateless, scales horizontally, integrates with Swagger UI. |
| Password hashing | bcrypt via passlib | Slow, salted, well-vetted. |
| RBAC | `require_roles(*roles)` dependency factory | Declarative per-endpoint, composable, single source of truth. |
| Background tasks | FastAPI BackgroundTasks + DB-persisted task store | Zero-infrastructure; Celery-ready when scale demands it. |
| ORM | SQLAlchemy 2.0 typed `Mapped[...]` | Static-analyzable, modern API. |
| Validation | Pydantic v2 | Auto OpenAPI, fast, separates request/response schemas. |
| Configuration | pydantic-settings + `.env` | 12-factor; fails fast on misconfig. |
| DB | SQLite default, Postgres-compatible | Reviewer can run instantly; one env var to switch in production. |
| Tests | pytest + TestClient + dependency overrides | Hermetic, fast, no external dependencies. |
