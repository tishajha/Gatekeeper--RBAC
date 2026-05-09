# Interviewer Talking Points

A concise, dialogue-ready cheat sheet for explaining the GateKeeper project. Use this alongside `APPROACH.md` (which has the deep technical reasoning) — this doc is the *spoken* version.

---

## The 60-second elevator pitch

> "GateKeeper is a FastAPI backend with three concerns layered cleanly: JWT-based authentication, role-based access control implemented as a reusable dependency, and asynchronous task execution with persisted status. The architecture is split into routes, services, and models — so HTTP concerns, business logic, and persistence each have one obvious home. I deliberately chose FastAPI's built-in BackgroundTasks over Celery for this scope, but the design has a clean seam to swap in Celery later without touching the API surface."

If you only get one minute, that's it. Everything below is for follow-up questions.

---

## Likely interviewer questions and how to answer

### Q: "Walk me through what happens when a user calls `POST /tasks/execute`."

> "The request hits the FastAPI route handler in `app/api/routes/tasks.py`. Three dependencies fire before the handler body runs: `get_db` opens a database session, `get_current_user` decodes the JWT and loads the user, and `require_roles(Role.MANAGER)` checks the user's role and raises 403 if they're not a manager. If all that passes, the handler calls `task_service.create_task` to insert a row in PENDING state, schedules `run_task_sync` on FastAPI's BackgroundTasks queue, and returns 202 with the task ID — all within a few milliseconds. After the response is sent, Starlette runs the background task on its threadpool. The task opens its own DB session, transitions the row through RUNNING, calls the registered runner function, then writes either SUCCESS with the result or FAILED with the error. The client polls `GET /tasks/{id}` to see what happened."

### Q: "Why JWT instead of sessions?"

> "JWT is stateless. The role is embedded in the token, so authorization decisions don't need a database lookup on every request. It also means we can scale to multiple API instances behind a load balancer without sticky sessions or a shared session store. Sessions are simpler to revoke, but for a stateless REST API that needs to scale horizontally, the trade-off favors JWT. I'd add refresh tokens and a shorter access-token lifetime in production — that's flagged in the README's hardening section."

### Q: "Walk me through the RBAC implementation."

> "It's a single dependency factory called `require_roles` in `app/api/deps.py`. It takes a variable number of `Role` enum values and returns a FastAPI dependency that resolves the current user, checks their role against the allowlist, and raises 403 if they're not authorized. Every protected route declares its requirements in one line — for example, `dependencies=[Depends(require_roles(Role.ADMIN))]`. The advantage is that authorization is *visible at the route definition*. There's no middleware doing path-matching elsewhere, no decorators wrapping handlers, no inline `if user.role` checks scattered across the codebase. A reviewer reading `users.py` can see exactly which roles can hit which endpoint without grepping."

### Q: "Why didn't you use Celery?"

> "Celery is the right answer for production at scale, but I think it's the wrong answer for this particular scope. The assignment is sized at 6–10 hours and asks for production-grade quality — but production-grade doesn't automatically mean Celery. With FastAPI's BackgroundTasks plus a database-persisted task store, I get genuinely asynchronous responses, persisted status that survives client disconnects, and zero infrastructure dependencies — you can run the project with just `pip install` and `uvicorn`. The trade-off is that in-flight tasks are lost if the API process restarts, and you can't scale to multiple workers. So I designed the system to be Celery-ready: there's a `TASK_REGISTRY` that maps task type strings to runner functions. To migrate to Celery, you turn each runner into a `@celery_app.task` and change `background_tasks.add_task` to `task.delay`. The route handlers, schemas, persistence, and RBAC don't change. The seam is in the right place."

This answer matters. It demonstrates *judgment*, not just knowledge.

### Q: "How do you handle the `/tasks/{id}` access control? Anyone authenticated can see anyone's tasks?"

> "Yes — that matches the spec, which says 'all authenticated.' I flagged this as a known trade-off in the README. In a production system I'd usually filter by `task.created_by == current_user.id` with an admin override. The change is a one-line filter in the route. I chose to match the spec rather than second-guess it."

### Q: "How do you make sure passwords don't leak in the API responses?"

> "Two things. First, the password is hashed with bcrypt before it ever reaches the database — the plaintext is only in memory for the duration of the login or create-user request. Second, the response schema `UserRead` is a separate Pydantic model from the request schema `UserCreate`. `UserRead` simply has no `password` or `hashed_password` field, so it's *structurally impossible* to leak a hash through this endpoint. Even if a developer accidentally returns the ORM object directly, Pydantic's `from_attributes=True` only reads the fields declared on the schema. There's a test that asserts `password` and `hashed_password` keys aren't present in the response."

### Q: "How does authentication actually validate the token?"

> "The `get_current_user` dependency extracts the bearer token via FastAPI's `OAuth2PasswordBearer`. It decodes the JWT using the same secret the login endpoint signs with, validates the signature and expiry — `python-jose` handles both — extracts the `sub` claim which is the user ID, and loads the user from the database. If the token is missing, malformed, expired, or signed with the wrong key, we raise a 401 with a `WWW-Authenticate: Bearer` header, which is required by RFC 6750."

### Q: "Why bcrypt for passwords?"

> "Bcrypt is deliberately slow — that's its security property. It resists brute-force attacks because each guess takes computational work. It's salted by default, which defeats rainbow-table attacks, and it's been battle-tested for over 20 years. I'm using it through `passlib`, which abstracts the scheme — if we ever needed to migrate to argon2 or change the cost factor, `passlib`'s `deprecated="auto"` would transparently rehash on the next successful login."

### Q: "How would you scale this to handle 10,000 tasks per minute?"

> "Three changes. First, swap BackgroundTasks for Celery with Redis as the broker — that's a one-day migration given the seam I built. Second, move from SQLite to Postgres — the SQLAlchemy code is identical, just an env-var change. Third, run multiple uvicorn workers behind a load balancer; the JWT-based auth means there's no shared session state to coordinate. For *very* high throughput on the read path, I'd add a Redis cache for `GET /tasks/{id}` so polling clients don't hammer the database. Beyond that, separate the worker fleet from the API fleet so heavy task workloads don't starve the request handlers."

### Q: "What if a task is malicious or runs forever?"

> "Currently nothing — every registered runner is trusted code I wrote. In a multi-tenant system you'd add a few layers: hard timeouts on the worker side, resource limits via cgroups or Docker, and an allowlist of task types per user role. Celery has a `time_limit` and `soft_time_limit` for exactly this. The current design's task type whitelist is a first line of defense — clients can't execute arbitrary code, only one of the runners I've registered."

### Q: "Walk me through the project layout."

> "Top level is `app/` for source and `tests/` for tests. Inside `app`: `api/routes/` is the HTTP layer — every file here is one resource. `api/deps.py` has the shared dependencies — DB session, current user, RBAC. `core/` has the cross-cutting infrastructure: settings, security primitives, the role enum. `db/session.py` has the SQLAlchemy engine and base. `models/` is ORM, `schemas/` is Pydantic, and `services/` is where business logic lives. The split between `models` and `schemas` is deliberate — ORM models are about persistence, Pydantic schemas are about wire format, and they're not the same thing."

### Q: "How are the tests structured?"

> "There are 24 tests across three files — auth, users, tasks. The key trick is in `conftest.py`: I use FastAPI's `dependency_overrides` to swap `get_db` for an in-memory SQLite session, and an autouse fixture drops and recreates the schema before every test. So tests are hermetic — no shared state, no order dependence, no real database touched. The task service's session factory is also overridden so background tasks share the same in-memory DB. The suite runs in about 30 seconds and requires zero external services."

### Q: "What's the riskiest piece of this code?"

> "Honestly? The JWT secret in `.env`. If that leaks, an attacker can mint admin tokens. In production it goes in a secrets manager — Vault, AWS Secrets Manager, whatever the platform provides. The `.env` mechanism is convenient for development but I wouldn't ship that to production. The second-riskiest is that `Base.metadata.create_all` on startup is fine for SQLite, but in a multi-instance Postgres deployment you'd race-condition the schema creation — that's why production uses Alembic migrations. I flagged both of these in the README's hardening table."

### Q: "Why Pydantic v2 and SQLAlchemy 2.0?"

> "Both are the current major versions, both shipped in 2023. Pydantic v2 is 5 to 50 times faster than v1 because the validator is written in Rust. SQLAlchemy 2.0's typed `Mapped[...]` syntax finally gives static type checkers something real to work with — refactoring is much safer. There's no reason to start a new project on the older versions."

### Q: "If you had another four hours, what would you add?"

> "Three things, in this order. First, refresh tokens with shorter access-token lifetimes — the current 30-minute access token is fine for a demo but loose for production. Second, structured logging with `structlog` so requests, auth failures, and task lifecycle events are all greppable JSON. Third, Alembic migrations replacing the `create_all` startup hook — this becomes important the moment you add a column to an existing table. Beyond that, rate limiting on `/auth/login`, CORS configuration, and a real worker process for tasks."

---

## Things to volunteer (don't wait to be asked)

When you walk them through the project, proactively call out:

1. **The Celery decision.** Don't wait for them to ask why you didn't use it. Lead with: "I deliberately chose BackgroundTasks here, and I want to explain why and how it's still production-shaped." This shows judgment.

2. **The RBAC pattern.** Show them the `require_roles` factory before they ask. It's the cleanest piece of the codebase and the one most worth showing off.

3. **The schema separation for password leakage.** "Notice that `UserRead` and `UserCreate` are different schemas — that's intentional, here's why." This pre-empts a security question.

4. **The trade-offs you flagged in the README.** Saying "I know what's missing for production, here's the list" is much stronger than letting them find gaps.

---

## Things to push back on (politely)

If the interviewer says something like:

- *"You should have used Celery."* → "Happy to discuss when Celery is the right call. For this scope my judgment was that the infrastructure cost wasn't justified, and I built the seam so the migration is mechanical. What scale are you imagining?"

- *"The tests should hit a real Postgres."* → "Integration tests against a real Postgres are valuable and I'd add them in CI. The unit-level tests use SQLite for speed and isolation; a CI pipeline would run both."

- *"Why didn't you implement refresh tokens?"* → "Scope. The spec asked for JWT login, not full token lifecycle management. I flagged it in the hardening section. Would have been an extra hour."

You're allowed to defend choices. Engineering interviews reward people with opinions, as long as the opinions are reasoned.

---

## Demo flow if they say "show me it working"

Have two terminals open before the call.

**Terminal 1 — server:**
```bash
uvicorn app.main:app --reload
```

**Terminal 2 — tests + curl:**
```bash
pytest -v          # show 24 passing
```

Then open <http://127.0.0.1:8000/docs> and walk through the happy path:
1. Authorize as admin → show the lock icons appear on protected endpoints.
2. `POST /users/` to create `alice` as a manager.
3. Try `POST /users/` again as alice → 403, role-based denial.
4. Login as alice, `POST /tasks/execute` with `long_computation` duration 5.
5. Immediately `GET /tasks/{id}` → status `pending`. Wait 5 seconds, refresh → status `success` with the result.

Total demo: under 4 minutes.

---

## What NOT to say

- "It's just a take-home, I didn't bother with X." Even if true, frame it as a deliberate scope decision: *"I scoped X out because Y; the path to add it is Z."*
- "I copied this pattern from a tutorial." Even if true, you internalized it and applied it to this problem — own that.
- "I don't know." If genuinely stuck, *"I haven't worked with that, but my hypothesis is X — how do you handle it on your team?"* turns the question into a conversation.

---

## One-liner for each major file (in case they ask "what's in this file?")

| File | One-liner |
|---|---|
| `app/main.py` | FastAPI app factory; mounts every router. |
| `app/api/deps.py` | The dependencies that make auth + RBAC work — `get_db`, `get_current_user`, `require_roles`. |
| `app/api/routes/auth.py` | Login endpoint; OAuth2 password flow returning a JWT. |
| `app/api/routes/users.py` | User create + list, gated by admin/manager. |
| `app/api/routes/tasks.py` | Task submit + status; 202 + polling pattern. |
| `app/core/security.py` | bcrypt and JWT primitives; deliberately framework-agnostic. |
| `app/core/roles.py` | Role enum — single source of truth for what roles exist. |
| `app/services/task_service.py` | Task lifecycle and the runner registry — the Celery seam. |
| `app/services/user_service.py` | User CRUD and `authenticate_user` (returns None on either bad-username or bad-password to prevent enumeration). |
| `tests/conftest.py` | The dependency-override magic that makes tests hermetic. |

---

Good luck. The project is solid; the explanation is what closes the loop.
