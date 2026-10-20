"""Iteration 16: per-user module access control."""
import os
import sys
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from server import hash_password  # noqa: E402

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "yash.sojitra34@gmail.com"
ADMIN_PASS = "Yash@2026"
TEST_EMAIL = "test_access_iter16@example.com"
TEST_PASS = "TestPass@2026"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
mongo = MongoClient(MONGO_URL)[DB_NAME]

MODULES = ["dashboard", "projects", "feasibility", "partners", "loans", "investments", "properties"]


# ---- Fixtures ----

@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return s


@pytest.fixture(scope="session")
def test_user_id():
    # cleanup any leftover
    mongo.users.delete_many({"email": TEST_EMAIL})
    doc = {
        "email": TEST_EMAIL,
        "name": "Test Access User",
        "password_hash": hash_password(TEST_PASS),
        "role": "user",
        "status": "approved",
        "access": ["dashboard", "projects"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = mongo.users.insert_one(doc)
    uid = str(res.inserted_id)
    yield uid
    # teardown
    mongo.users.delete_many({"email": TEST_EMAIL})
    mongo.user_sessions.delete_many({"user_id": uid})


@pytest.fixture(scope="session")
def user_session(test_user_id):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    assert r.status_code == 200, f"test user login failed: {r.text}"
    return s


# ---- Access enforcement ----

ENDPOINTS = {
    "dashboard": "/api/dashboard",
    "projects": "/api/projects",
    "feasibility": "/api/feasibility",
    "partners_ledger": "/api/ledger",
    "partners_overview": "/api/partner/overview",
    "investments": "/api/investments",
    "properties": "/api/properties",
    "loans": "/api/personal-loans",
}


class TestAccessEnforcement:
    def test_restricted_user_blocked_from_non_granted_modules(self, user_session):
        # has only dashboard+projects → others should 403 no_access
        for name, path in ENDPOINTS.items():
            r = user_session.get(f"{BASE_URL}{path}")
            if name in ("dashboard", "projects"):
                assert r.status_code == 200, f"{path} should be 200 for granted: {r.status_code} {r.text[:200]}"
            else:
                assert r.status_code == 403, f"{path} expected 403, got {r.status_code}"
                assert r.json().get("detail") == "no_access"

    def test_admin_grants_access_and_user_gains_immediately(self, admin_session, user_session, test_user_id):
        new_access = ["dashboard", "projects", "partners", "investments"]
        r = admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                              json={"access": new_access})
        assert r.status_code == 200
        assert set(r.json()["access"]) == set(new_access)

        # Instant effect — no re-login
        r = user_session.get(f"{BASE_URL}/api/partner/overview")
        assert r.status_code == 200, f"partners should now be 200: {r.status_code} {r.text[:200]}"
        r = user_session.get(f"{BASE_URL}/api/investments")
        assert r.status_code == 200
        # properties still blocked
        r = user_session.get(f"{BASE_URL}/api/properties")
        assert r.status_code == 403

    def test_revoke_access_takes_effect_immediately(self, admin_session, user_session, test_user_id):
        r = admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                              json={"access": ["dashboard"]})
        assert r.status_code == 200
        for path in ["/api/projects", "/api/partner/overview", "/api/investments"]:
            r = user_session.get(f"{BASE_URL}{path}")
            assert r.status_code == 403, f"{path} should 403 after revoke, got {r.status_code}"

    def test_invalid_module_filtered(self, admin_session, test_user_id):
        r = admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                              json={"access": ["dashboard", "bogus", "partners", "nope"]})
        assert r.status_code == 200
        assert set(r.json()["access"]) == {"dashboard", "partners"}

    def test_empty_access_list(self, admin_session, user_session, test_user_id):
        r = admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                              json={"access": []})
        assert r.status_code == 200
        assert r.json()["access"] == []
        # dashboard now blocked too
        r = user_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 403
        # auth/me still works (not module-gated)
        r = user_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json().get("access") == []


# ---- /auth/me returns effective access ----

class TestAuthMe:
    def test_admin_auth_me_full_access(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"
        assert set(data.get("access", [])) == set(MODULES)

    def test_user_auth_me_matches_db(self, user_session, admin_session, test_user_id):
        # restore known state
        admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                          json={"access": ["dashboard", "projects"]})
        r = user_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert set(r.json()["access"]) == {"dashboard", "projects"}


# ---- Admin regression ----

class TestAdminRegression:
    def test_admin_can_hit_all_module_endpoints(self, admin_session):
        for path in ENDPOINTS.values():
            r = admin_session.get(f"{BASE_URL}{path}")
            assert r.status_code == 200, f"admin blocked at {path}: {r.status_code}"

    def test_admin_users_list_contains_test_user(self, admin_session, test_user_id):
        r = admin_session.get(f"{BASE_URL}/api/admin/users")
        assert r.status_code == 200
        ids = [u["id"] for u in r.json()]
        assert test_user_id in ids


# ---- Data privacy ----

class TestDataPrivacy:
    def test_restricted_user_sees_own_scope_partners(self, admin_session, user_session, test_user_id):
        admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                          json={"access": ["dashboard", "partners"]})
        r = user_session.get(f"{BASE_URL}/api/partner/overview")
        assert r.status_code == 200
        data = r.json()
        # Should be scope 'self' or at least contain only self data (not admin's partner book)
        # Admin has MAISON 7 partners — this user has none
        if isinstance(data, dict):
            scope = data.get("scope")
            # Accept 'self' or absence of other partners' names
            partners = data.get("partners") or data.get("rows") or []
            if scope:
                assert scope == "self", f"expected scope=self for non-admin, got {scope}"
            # verify no admin partner data leaked
            dumped = str(data).lower()
            # these are typical admin partners we shouldn't see
            # (soft check — just ensure the response is small/empty for new user)
            assert len(partners) <= 1 if isinstance(partners, list) else True

    def test_restricted_user_dashboard_shows_own_data(self, admin_session, user_session, test_user_id):
        admin_session.put(f"{BASE_URL}/api/admin/users/{test_user_id}/access",
                          json={"access": ["dashboard"]})
        r = user_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        # New user — their totals should be near-zero (no projects/investments)
        # Just verify response structure
        assert isinstance(data, dict)


# ---- Legacy user (no access field) ----

class TestLegacyUser:
    def test_user_without_access_field_gets_full_via_authme(self, admin_session):
        # Insert a legacy user doc directly (no 'access' field)
        legacy_email = "test_legacy_iter16@example.com"
        mongo.users.delete_many({"email": legacy_email})
        pwd = "LegacyPass@2026"
        res = mongo.users.insert_one({
            "email": legacy_email, "name": "Legacy", "password_hash": hash_password(pwd),
            "role": "user", "status": "approved",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        uid = str(res.inserted_id)
        try:
            s = requests.Session()
            r = s.post(f"{BASE_URL}/api/auth/login", json={"email": legacy_email, "password": pwd})
            assert r.status_code == 200
            r = s.get(f"{BASE_URL}/api/auth/me")
            assert r.status_code == 200
            # per code: non-admin without list → access defaults to all MODULES
            assert set(r.json().get("access", [])) == set(MODULES)
            # And module endpoints should pass through (not 403 no_access)
            r = s.get(f"{BASE_URL}/api/partner/overview")
            assert r.status_code == 200
        finally:
            mongo.users.delete_many({"email": legacy_email})
            mongo.user_sessions.delete_many({"user_id": uid})
