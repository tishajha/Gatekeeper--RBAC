"""Tests covering the user endpoints and the RBAC dependency."""
from tests.conftest import auth_header, login_as


def test_admin_can_create_user(client, seed_users):
    token = login_as(client, "admin_user")
    response = client.post(
        "/users/",
        json={"username": "new_user", "password": "secret123", "role": "viewer"},
        headers=auth_header(token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "new_user"
    assert body["role"] == "viewer"
    # Critical: response must NOT leak the password hash.
    assert "password" not in body
    assert "hashed_password" not in body


def test_create_user_rejects_duplicate_username(client, seed_users):
    token = login_as(client, "admin_user")
    response = client.post(
        "/users/",
        json={"username": "admin_user", "password": "secret123", "role": "viewer"},
        headers=auth_header(token),
    )
    assert response.status_code == 409


def test_manager_cannot_create_user(client, seed_users):
    """Only admins should be allowed to create users."""
    token = login_as(client, "manager_user")
    response = client.post(
        "/users/",
        json={"username": "blocked", "password": "secret123", "role": "viewer"},
        headers=auth_header(token),
    )
    assert response.status_code == 403


def test_viewer_cannot_create_user(client, seed_users):
    token = login_as(client, "viewer_user")
    response = client.post(
        "/users/",
        json={"username": "blocked", "password": "secret123", "role": "viewer"},
        headers=auth_header(token),
    )
    assert response.status_code == 403


def test_admin_can_list_users(client, seed_users):
    token = login_as(client, "admin_user")
    response = client.get("/users/", headers=auth_header(token))
    assert response.status_code == 200
    assert len(response.json()) == 4  # one user per role


def test_manager_can_list_users(client, seed_users):
    token = login_as(client, "manager_user")
    response = client.get("/users/", headers=auth_header(token))
    assert response.status_code == 200


def test_operator_cannot_list_users(client, seed_users):
    """Operator is below manager — should be forbidden."""
    token = login_as(client, "operator_user")
    response = client.get("/users/", headers=auth_header(token))
    assert response.status_code == 403


def test_viewer_cannot_list_users(client, seed_users):
    token = login_as(client, "viewer_user")
    response = client.get("/users/", headers=auth_header(token))
    assert response.status_code == 403


def test_create_user_validates_short_password(client, seed_users):
    """Password length is enforced by the Pydantic schema -> 422."""
    token = login_as(client, "admin_user")
    response = client.post(
        "/users/",
        json={"username": "short_pw", "password": "x", "role": "viewer"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
