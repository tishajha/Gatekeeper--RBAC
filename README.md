# GateKeeper RBAC Execution Platform

A production-grade backend service providing JWT-based authentication, role-based access control over protected APIs, and asynchronous background task execution.

Built with **FastAPI**, **SQLAlchemy 2.0**, **Pydantic v2**, and **Python 3.10+**.

---

## Table of contents

1. [Quick start](#quick-start)
2. [Project layout](#project-layout)
3. [API reference](#api-reference)
4. [Permission matrix](#permission-matrix)
5. [Running tests](#running-tests)


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

## License

For interview / take-home purposes.
