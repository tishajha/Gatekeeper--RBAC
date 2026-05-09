# GateKeeper RBAC Execution Platform

A production-grade backend service providing JWT-based authentication, role-based access control over protected APIs, and asynchronous background task execution.

Built with **FastAPI**, **SQLAlchemy 2.0**, **Pydantic v2**, and **Python 3.10+**.

---

## Table of contents

1. [Quick start](#quick-start)
2. [Project layout](#project-layout)
3. [Approach and rationale](#approach-and-rationale)
4. [API reference](#api-reference)
5. [Permission matrix](#permission-matrix)
6. [Running tests](#running-tests)
7. [Trade-offs and production hardening](#trade-offs-and-production-hardening)

---

## Quick start

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate            # macOS/Linux
# .venv\Scripts\activate              # Windows PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) copy .env.example to .env and tweak values
cp .env.example .env

# 4. Seed the database with the default admin user
python -m app.seed

# 5. Run the API
uvicorn app.main:app --reload
```

The API is now live at <http://127.0.0.1:8000>. Interactive Swagger docs at <http://127.0.0.1:8000/docs>.

Default admin credentials (configurable in `.env`): `admin` / `admin123`.

---

## Project layout

```
gatekeeper/
├── app/
│   ├── api/
│   │   ├── deps.py              # DB session, current user, RBAC dependencies
│   │   └── routes/
│   │       ├── auth.py          # POST /auth/login
│   │       ├── users.py         # POST /users/, GET /users/
│   │       ├── tasks.py         # POST /tasks/execute, GET /tasks/{id}
│   │       └── health.py        # GET /health
│   ├── core/
│   │   ├── config.py            # Pydantic Settings, .env loading
│   │   ├── security.py          # bcrypt + JWT helpers
│   │   └── roles.py             # Role enum
│   ├── db/
│   │   └── session.py           # SQLAlchemy engine, Base, SessionLocal
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── user.py
│   │   └── task.py
│   ├── schemas/                 # Pydantic request/response models
│   │   ├── user.py
│   │   ├── token.py
│   │   └── task.py
│   ├── services/                # Business logic, framework-agnostic
│   │   ├── user_service.py
│   │   └── task_service.py      # Task runner registry + lifecycle
│   ├── main.py                  # FastAPI app factory + router wiring
│   └── seed.py                  # CLI: create tables and the default admin
├── tests/
│   ├── conftest.py              # In-memory test DB + fixtures
│   ├── test_auth.py
│   ├── test_users.py
│   └── test_tasks.py
├── postman_collection.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## Approach and rationale

This is the most important section for the interviewer. Each architectural choice is deliberate; here's what was chosen and why.

### 1. Layered architecture (routes → services → models)

**What:** API routes only handle HTTP concerns (parsing input, returning status codes). Business logic lives in `app/services/`. Database access is encapsulated by SQLAlchemy ORM models. Pydantic schemas are the input/output contract.

**Why:** This is the canonical clean-architecture split for FastAPI. Routes stay short and grep-able. Service functions are pure Python and reusable from CLI scripts (the seed command is one example), background workers, and tests — without dragging FastAPI in as a dependency. Swapping the database engine, the ORM, or even the web framework would touch only one layer at a time.

**Advantage over a flat layout:** When the codebase grows, you don't end up with 800-line route files mixing validation, business rules, and SQL. The boundaries make it obvious where new code goes.

### 2. JWT + OAuth2 Password Flow for authentication

**What:** `POST /auth/login` accepts a username/password as `application/x-www-form-urlencoded` (the OAuth2 standard) and returns a signed JWT containing `sub` (user id) and `role`. Subsequent requests carry this token in the `Authorization: Bearer <token>` header.

**Why:**
- **Stateless.** No server-side session store required. Horizontal scaling is trivial.
- **The role is embedded in the token,** so authorization decisions don't require a DB roundtrip on every request.
- **Compatible with Swagger UI's "Authorize" button** out of the box, which makes the auto-generated docs page directly testable.

**Library choices:** `python-jose` for JWT (mature, battle-tested), `passlib[bcrypt]` for password hashing (industry standard, deliberately slow, salted by default).

### 3. RBAC via reusable dependency factory

**What:** Authorization is implemented as a single dependency factory in `app/api/deps.py`:

```python
def require_roles(*allowed_roles: Role) -> Callable[[User], User]:
    allowed = {r.value for r in allowed_roles}
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(403, ...)
        return current_user
    return role_checker
```

Each protected route declares its required roles in one line:

```python
@router.post("/", dependencies=[Depends(require_roles(Role.ADMIN))])
def create_user(...): ...
```

**Why this pattern over alternatives:**

| Alternative | Why I rejected it |
|---|---|
| Decorator like `@admin_only` | Decorators on FastAPI route functions break dependency injection, type hints, and OpenAPI doc generation. |
| Middleware that inspects request paths | Couples routing knowledge to authorization. New endpoints would need middleware updates. Doesn't compose with FastAPI's `Depends`. |
| Inline `if user.role != "admin"` checks | Logic duplicated across endpoints. Easy to forget on a new route. Hard to test in isolation. |
| Per-permission strings (`require_permission("users:create")`) | Overkill for four roles with stable permissions. Adds a permissions table and admin UI for no concrete win. Easy to upgrade to later if needed — the dependency is the same shape. |

**Advantage of the factory approach:** Authorization is declarative and visible at the route definition. A reviewer reading `users.py` can see exactly which roles can hit which endpoint without searching elsewhere.

### 4. Background task execution via FastAPI `BackgroundTasks` with a persisted task store

**What:** `POST /tasks/execute` returns `202 Accepted` with a `task_id` immediately. The actual work is scheduled on FastAPI's `BackgroundTasks` (Starlette's threadpool). Every task is persisted in the database with a status enum (`PENDING → RUNNING → SUCCESS | FAILED`), so `GET /tasks/{task_id}` can answer at any time. Task type is dispatched via a small registry (`TASK_REGISTRY`) so adding a new task is one function plus one line.

**Why this approach over Celery + Redis:**

The assignment is sized at 6–10 hours and asks for "production-grade" — but production-grade does not automatically mean Celery. For the scope here:

| | FastAPI BackgroundTasks (chosen) | Celery + Redis |
|---|---|---|
| **Setup complexity** | Zero. `pip install` and run. | Requires Redis, a worker process, Docker Compose. |
| **Reviewer can run instantly** | Yes — `uvicorn app.main:app`. | No — needs `docker compose up`. |
| **Task status persists across requests** | Yes — stored in DB. | Yes — stored in Redis backend. |
| **Survives API process restart** | In-flight tasks lost. | In-flight tasks recovered. |
| **Scales horizontally** | Limited to one process. | Multi-worker, multi-machine. |
| **Lines of code** | ~80 in `task_service.py`. | Substantially more, plus infra config. |

**Critically, the architecture is Celery-ready.** The route layer hands a task to a registered runner via the `TASK_REGISTRY` dict and a single function call. To upgrade to Celery, you swap `background_tasks.add_task(...)` for `celery_task.delay(...)` and turn each runner into a `@celery_app.task`. The route, the schemas, the persistence model, and the polling endpoint don't change. **The seam is in the right place.**

This is the kind of scope-appropriate pragmatism interviewers look for: knowing both options and picking the smaller one when justified.

### 5. Pydantic v2 + SQLAlchemy 2.0

**What:** Modern, type-checked stack. Pydantic schemas validate every request body and serialize every response. `from_attributes=True` lets response schemas read directly from ORM objects.

**Why:**
- **Auto-generated OpenAPI docs** are accurate by construction — they're derived from the Pydantic models.
- **Validation is declarative.** A 422 with a useful error message is automatic when input doesn't match the schema.
- **Separate `UserCreate` and `UserRead` schemas** mean it is structurally impossible to accidentally leak a password hash through an endpoint — there is no field for it on the response model.
- **SQLAlchemy 2.0's typed `Mapped[...]`** gives proper type hints on model attributes, which static analysis can check.

### 6. Configuration via Pydantic Settings + `.env`

**What:** All configuration (JWT secret, DB URL, token expiry) is loaded from environment variables, with a `.env` file for local development. `Settings` is a Pydantic class so missing or malformed values fail at startup, not at first request.

**Why:** No secrets in source control. Same code runs in dev, staging, and prod by changing env vars. `.env.example` documents what's required without committing real secrets.

### 7. SQLite by default, swappable for Postgres

**What:** Default `DATABASE_URL` is SQLite (`sqlite:///./gatekeeper.db`). Production deployments override with a Postgres URL (`postgresql+psycopg2://...`).

**Why:** Reviewer experience. SQLite means no Docker, no service to start, no port collisions. Switching to Postgres is one env var change — the SQLAlchemy code is identical.

### 8. Test isolation via dependency override + in-memory SQLite

**What:** The test suite (`tests/conftest.py`) uses FastAPI's `dependency_overrides` to replace `get_db` with a session against an in-memory SQLite database. Schema is dropped and recreated before every test (autouse fixture). The task runner's session factory is also overridden so background tasks share the same in-memory DB as the API.

**Why:** Tests are hermetic, fast (~30s for 24 tests), and deterministic. They never touch the developer's real database. Running `pytest` requires no setup beyond installing dependencies.

---

## API reference

Interactive docs: <http://127.0.0.1:8000/docs> (Swagger UI) and <http://127.0.0.1:8000/redoc> (ReDoc).

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | Public | Liveness probe. Returns `{"status": "ok"}`. |
| POST | `/auth/login` | Public | Form body `username` + `password`. Returns JWT. |
| POST | `/users/` | Admin | Create a new user. JSON body. Returns 201. |
| GET | `/users/` | Admin, Manager | List users. Supports `?skip` and `?limit`. |
| POST | `/tasks/execute` | Manager | Submit a task. Returns 202 with `task_id`. |
| GET | `/tasks/{task_id}` | Any authenticated | Poll task status and result. |

### Built-in task types

- **`echo`** — returns `{"echoed": <payload>}`. Useful for smoke tests.
- **`long_computation`** — sleeps for `payload.duration` seconds (default 5), then returns the sum of `payload.numbers`. Useful for proving the endpoint is genuinely non-blocking.

Add a new task by registering a function in `TASK_REGISTRY` (in `app/services/task_service.py`).

---

## Permission matrix

| Endpoint | Admin | Manager | Operator | Viewer | Anonymous |
|---|:---:|:---:|:---:|:---:|:---:|
| `GET /health` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `POST /auth/login` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `POST /users/` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `GET /users/` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `POST /tasks/execute` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `GET /tasks/{id}` | ✅ | ✅ | ✅ | ✅ | ❌ |

The matrix matches the assignment specification exactly. Note: `Admin` cannot submit tasks per the spec — task execution is a `Manager` operation. This is enforced by `require_roles(Role.MANAGER)` on `POST /tasks/execute` and verified by `test_admin_cannot_submit_task`.

---

## Running tests

```bash
pytest -v
```

24 tests, all passing. Coverage spans:

- **Auth flow** — login success, wrong password, unknown user, missing token, garbage token.
- **RBAC** — every protected endpoint tested with both an authorized role (200/201/202) and a forbidden role (403).
- **User CRUD** — duplicate username (409), short password (422), password hash never in response.
- **Task lifecycle** — submit → poll → success path; unknown `task_type` returns 400; missing task returns 404.

---

## Trade-offs and production hardening

Things deliberately left out of scope, with the path to add them:

| Concern | Current state | Production fix |
|---|---|---|
| Long-running tasks across restarts | Lost on API process kill. | Swap `BackgroundTasks` for Celery + Redis. The runner registry is the seam. |
| DB migrations | `Base.metadata.create_all()` on startup. | Alembic. Add `alembic.ini` and `alembic/` directory; replace `create_all` call. |
| Refresh tokens | Only access tokens, 30 min expiry. | Add `/auth/refresh` issuing a long-lived refresh token + short-lived access token. |
| Rate limiting on `/auth/login` | None. | `slowapi` middleware or an upstream WAF. |
| Logging | Default uvicorn access log. | Structured JSON logs (e.g. `structlog`) routed to a log aggregator. |
| Secrets in `.env` | Plaintext file. | Vault, AWS Secrets Manager, or platform-native secret store. |
| CORS | Not configured. | `CORSMiddleware` with an explicit allowlist of frontend origins. |
| `GET /tasks/{id}` access control | All authenticated users can read any task. | Filter by `created_by == current_user.id` (or admin override). The spec says "all authenticated", so I matched the spec. |

---

## License

For interview / take-home purposes.
