"""Tests covering task submission, status retrieval, and RBAC on tasks."""
from tests.conftest import auth_header, login_as


def test_manager_can_submit_task(client, seed_users):
    token = login_as(client, "manager_user")
    response = client.post(
        "/tasks/execute",
        json={"task_type": "echo", "payload": {"hello": "world"}},
        headers=auth_header(token),
    )
    assert response.status_code == 202
    body = response.json()
    assert "task_id" in body
    # Status starts as PENDING; the BackgroundTask fires after the response.
    assert body["status"] in {"pending", "success"}


def test_admin_cannot_submit_task(client, seed_users):
    """Per spec, only managers can execute tasks. Admin should be 403."""
    token = login_as(client, "admin_user")
    response = client.post(
        "/tasks/execute",
        json={"task_type": "echo", "payload": {}},
        headers=auth_header(token),
    )
    assert response.status_code == 403


def test_viewer_cannot_submit_task(client, seed_users):
    token = login_as(client, "viewer_user")
    response = client.post(
        "/tasks/execute",
        json={"task_type": "echo", "payload": {}},
        headers=auth_header(token),
    )
    assert response.status_code == 403


def test_unknown_task_type_returns_400(client, seed_users):
    token = login_as(client, "manager_user")
    response = client.post(
        "/tasks/execute",
        json={"task_type": "does_not_exist", "payload": {}},
        headers=auth_header(token),
    )
    assert response.status_code == 400


def test_task_status_endpoint_returns_result(client, seed_users):
    """Submit an echo task, then poll for its result.

    BackgroundTasks fire after the TestClient context manager closes the
    underlying response. The `client` fixture uses a single context for
    the whole test, so we explicitly wait briefly to let the runner thread
    finish before polling.
    """
    import time

    manager_token = login_as(client, "manager_user")
    submit = client.post(
        "/tasks/execute",
        json={"task_type": "echo", "payload": {"k": "v"}},
        headers=auth_header(manager_token),
    )
    assert submit.status_code == 202
    task_id = submit.json()["task_id"]

    # Give the background task a moment to flush. The echo task is
    # near-instant; 1s is comfortably enough headroom.
    deadline = time.time() + 5
    body: dict = {}
    while time.time() < deadline:
        status_resp = client.get(
            f"/tasks/{task_id}", headers=auth_header(manager_token)
        )
        assert status_resp.status_code == 200
        body = status_resp.json()
        if body["status"] in {"success", "failed"}:
            break
        time.sleep(0.1)

    assert body["status"] == "success", body
    assert body["result"] == {"echoed": {"k": "v"}}
    assert body["error"] is None


def test_task_status_accessible_to_any_authenticated_user(client, seed_users):
    """Per spec, GET /tasks/{id} is open to all authenticated users."""
    manager_token = login_as(client, "manager_user")
    submit = client.post(
        "/tasks/execute",
        json={"task_type": "echo", "payload": {}},
        headers=auth_header(manager_token),
    )
    task_id = submit.json()["task_id"]

    # A viewer (lowest role) should still be able to read the status.
    viewer_token = login_as(client, "viewer_user")
    response = client.get(
        f"/tasks/{task_id}", headers=auth_header(viewer_token)
    )
    assert response.status_code == 200


def test_task_status_requires_authentication(client, seed_users):
    response = client.get("/tasks/some-id")
    assert response.status_code == 401


def test_task_status_returns_404_for_missing_task(client, seed_users):
    token = login_as(client, "viewer_user")
    response = client.get(
        "/tasks/00000000-0000-0000-0000-000000000000",
        headers=auth_header(token),
    )
    assert response.status_code == 404
