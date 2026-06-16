"""Auth: register, login, refresh, logout (blacklist), /me, invalid/expired credentials."""

from datetime import timedelta

import pytest
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


def test_register_creates_customer(api):
    resp = api.post(
        "/api/auth/register/",
        {"email": "new@example.com", "password": "StrongPass123"},
        format="json",
    )
    assert resp.status_code == 201
    user = User.objects.get(email="new@example.com")
    assert user.role == Role.CUSTOMER
    # password is hashed, never stored plaintext
    assert user.password != "StrongPass123"
    assert user.check_password("StrongPass123")


def test_register_rejects_weak_password(api):
    resp = api.post(
        "/api/auth/register/",
        {"email": "weak@example.com", "password": "123"},
        format="json",
    )
    assert resp.status_code == 400
    assert "password" in resp.data


def test_register_rejects_duplicate_email(api, make_user):
    make_user(email="dupe@example.com")
    resp = api.post(
        "/api/auth/register/",
        {"email": "dupe@example.com", "password": "StrongPass123"},
        format="json",
    )
    assert resp.status_code == 400


def test_login_returns_tokens_and_profile(api, make_user):
    make_user(email="login@example.com", password="StrongPass123")
    resp = api.post(
        "/api/auth/login/",
        {"email": "login@example.com", "password": "StrongPass123"},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    assert resp.data["user"]["email"] == "login@example.com"


def test_login_invalid_credentials(api, make_user):
    make_user(email="login2@example.com", password="StrongPass123")
    resp = api.post(
        "/api/auth/login/",
        {"email": "login2@example.com", "password": "wrong"},
        format="json",
    )
    assert resp.status_code == 401


def test_refresh_issues_new_access(api, make_user):
    make_user(email="ref@example.com", password="StrongPass123")
    login = api.post(
        "/api/auth/login/",
        {"email": "ref@example.com", "password": "StrongPass123"},
        format="json",
    )
    resp = api.post("/api/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data


def test_me_requires_auth(api):
    assert api.get("/api/me/").status_code == 401


def test_me_returns_profile(api, make_user):
    user = make_user(email="me@example.com")
    api.force_authenticate(user=user)
    resp = api.get("/api/me/")
    assert resp.status_code == 200
    assert resp.data["email"] == "me@example.com"
    assert resp.data["role"] == Role.CUSTOMER


def test_logout_blacklists_refresh(api, make_user):
    make_user(email="out@example.com", password="StrongPass123")
    login = api.post(
        "/api/auth/login/",
        {"email": "out@example.com", "password": "StrongPass123"},
        format="json",
    )
    refresh = login.data["refresh"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    out = api.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    assert out.status_code == 205

    # blacklisted refresh can no longer mint access tokens
    again = api.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert again.status_code == 401


def test_expired_access_token_rejected(api, make_user):
    user = make_user(email="exp@example.com")
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=timedelta(seconds=-1))  # already expired
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get("/api/me/").status_code == 401
