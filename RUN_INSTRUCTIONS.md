# How to Run the GateKeeper Project

Step-by-step instructions to get the project running on a fresh machine.

---

## Prerequisites

You need:

- - **Python 3.10, 3.11, or 3.12.** (Python 3.13 and 3.14 are not currently supported — one of our dependencies, `passlib`, relies on the stdlib `crypt` module which was removed in Python 3.13.) Check your version with `python --version`.
- **pip** (comes with Python).
- A terminal (Command Prompt / PowerShell on Windows, or any Unix shell).

You do NOT need: Docker, Redis, Postgres, or any other service. The project runs out of the box on SQLite.

---

## Step 1 — Unzip the project

```bash
unzip gatekeeper.zip
cd gatekeeper
```

---

## Step 2 — Create and activate a virtual environment

This isolates the project's dependencies from your system Python.

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

You should see `(.venv)` at the start of your prompt now.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This takes about 30–60 seconds. Installs FastAPI, SQLAlchemy, Pydantic, JWT and bcrypt libraries, pytest, and httpx.

---

## Step 4 — (Optional) Configure via .env

The defaults work for local development, so this step is optional.

```bash
# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Edit `.env` to override the JWT secret or change the default admin credentials. For an interview demo, the defaults are fine.

---

## Step 5 — Seed the database

This creates the SQLite file (`gatekeeper.db`) and a default admin user.

```bash
python -m app.seed
```

Expected output:
```
Created admin user id=1 username='admin' role='admin'.
Login with username 'admin' and password 'admin123'.
```

If you re-run this, it will say "already exists — nothing to do." That's fine — the script is idempotent.

---

## Step 6 — Start the API server

```bash
uvicorn app.main:app --reload
```

Expected output:
```
INFO:     Will watch for changes in these directories: [...]
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

Leave this terminal running.

---

## Step 7 — Try the API

### Option A: Swagger UI (easiest for a demo)

Open <http://127.0.0.1:8000/docs> in your browser.

1. Click the **Authorize** button at the top right.
2. Enter `admin` / `admin123` and click Authorize.
3. Now every endpoint can be tried directly from the browser.

Try these in order:
- `GET /health` — returns `{"status": "ok"}` (no auth needed).
- `POST /users/` — create a user with role `manager`. (Admin only.)
- `GET /users/` — list users. (Admin or manager only.)
- Then re-authorize as the manager you just created and try `POST /tasks/execute` with body `{"task_type": "echo", "payload": {"hello": "world"}}`.
- Copy the returned `task_id` and try `GET /tasks/{task_id}`.

### Option B: Postman

1. Open Postman.
2. Click **Import** → select `postman_collection.json` from the project root.
3. The collection includes pre-configured requests in the recommended order. Run "Login as Admin" first — it auto-saves the token to a collection variable that the other requests use.

### Option C: curl

```bash
# Health (public)
curl http://127.0.0.1:8000/health

# Login as admin and capture the token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -d "username=admin&password=admin123" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create a manager
curl -X POST http://127.0.0.1:8000/users/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "alicepass", "role": "manager"}'

# List users
curl -X GET http://127.0.0.1:8000/users/ \
  -H "Authorization: Bearer $TOKEN"

# Login as alice (the manager) and capture her token
MGR=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -d "username=alice&password=alicepass" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Submit a task
curl -X POST http://127.0.0.1:8000/tasks/execute \
  -H "Authorization: Bearer $MGR" \
  -H "Content-Type: application/json" \
  -d '{"task_type": "long_computation", "payload": {"duration": 3, "numbers": [10, 20, 30]}}'

# Poll for the result (replace TASK_ID with the id from the previous response)
curl -X GET http://127.0.0.1:8000/tasks/TASK_ID \
  -H "Authorization: Bearer $MGR"
```

---

## Step 8 — Run the tests

In a separate terminal (with the venv activated):

```bash
pytest -v
```

Expected: 24 tests, all passing, in ~30 seconds.

Run a single test file:
```bash
pytest tests/test_users.py -v
```

Run with coverage (optional, install first: `pip install pytest-cov`):
```bash
pytest --cov=app --cov-report=term-missing
```

---

## Troubleshooting

**`uvicorn: command not found`**
The venv isn't activated. Re-run the activate command from Step 2. You can also use `python -m uvicorn app.main:app --reload`.

**`ModuleNotFoundError: No module named 'app'`**
You're not running from the project root. `cd` into the `gatekeeper` directory first.

**`bcrypt.__about__` warning**
Harmless. It's a known passlib-bcrypt compatibility warning; it doesn't affect behavior.

**Port 8000 already in use**
Pick a different port:
```bash
uvicorn app.main:app --reload --port 8001
```

**Want to wipe the database and start fresh**
```bash
rm gatekeeper.db          # macOS/Linux
del gatekeeper.db         # Windows
python -m app.seed
```

---

## What to show during the demo

A 5-minute happy-path demo:

1. **`GET /health`** — public, no auth. Proves the service is up.
2. **`POST /auth/login`** as admin — show the JWT in the response.
3. Decode the JWT at <https://jwt.io> to show the `sub` and `role` claims.
4. **`POST /users/`** to create a manager.
5. **`GET /users/`** to show the new user, password hash NOT in the response.
6. Try **`POST /users/`** as the manager — get a 403. Show RBAC works.
7. Login as the manager.
8. **`POST /tasks/execute`** with `long_computation` and `duration: 5`. Note the response is instant — the API didn't block.
9. **`GET /tasks/{id}`** immediately — status is `pending` or `running`.
10. Wait 5 seconds, **`GET /tasks/{id}`** again — status is `success`, result populated.
11. **`pytest`** — show 24 tests, all passing.

That's the full feature surface in five minutes.
