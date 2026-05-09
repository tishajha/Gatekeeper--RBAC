"""Tests for the health endpoint and authentication flow."""
from tests.conftest import auth_header, login_as


def test_health_is_public(client):
    """Health check should always return 200 with no auth."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_succeeds_with_valid_credentials(client, seed_users):
    response = client.post(
        "/auth/login",
        data={"username": "admin_user", "password": "password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 20  # sanity-check it's a real JWT


def test_login_fails_with_wrong_password(client, seed_users):
    response = client.post(
        "/auth/login",
        data={"username": "admin_user", "password": "wrong"},
    )
    assert response.status_code == 401


def test_login_fails_with_unknown_user(client, seed_users):
    response = client.post(
        "/auth/login",
        data={"username": "nope", "password": "password123"},
    )
    assert response.status_code == 401


def test_protected_endpoint_rejects_missing_token(client, seed_users):
    response = client.get("/users/")
    assert response.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client, seed_users):
    response = client.get("/users/", headers=auth_header("not.a.real.jwt"))
    assert response.status_code == 401


def test_token_grants_access(client, seed_users):
    """Logging in and using the returned token should let admin in."""
    token = login_as(client, "admin_user")
    response = client.get("/users/", headers=auth_header(token))
    assert response.status_code == 200
