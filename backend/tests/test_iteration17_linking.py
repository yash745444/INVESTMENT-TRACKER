"""Iteration 17: linking properties & projects to users via partner email."""
import os
import sys
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

TEST_USER_EMAIL = "test_link_iter17@example.com"
TEST_USER_PASS = "LinkTest@2026"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
mongo = MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    # clear brute force
    mongo.login_attempts.delete_many({})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def test_user_id():
    mongo.users.delete_many({"email": TEST_USER_EMAIL})
    doc = {
        "email": TEST_USER_EMAIL,
        "name": "Link Test User",
        "password_hash": hash_password(TEST_USER_PASS),
        "role": "user",
        "status": "approved",
        "access": ["dashboard", "projects", "properties"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = mongo.users.insert_one(doc)
    uid = str(res.inserted_id)
    yield uid
    # cleanup user + all docs attributable to it
    mongo.users.delete_many({"email": TEST_USER_EMAIL})
    mongo.user_sessions.delete_many({"user_id": uid})


@pytest.fixture(scope="session")
def user_session(test_user_id):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASS})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def linked_property(admin_session):
    payload = {
        "name": "TEST LINK PROP ITER17",
        "address": "Test addr",
        "current_value": 400000,
        "debt": 0,
        "monthly_rent": 0,
        "currency": "AUD",
        "partners": [
            {"name": "Yash", "percentage": 60, "email": ADMIN_EMAIL},
            {"name": "Link Test User", "percentage": 40, "email": TEST_USER_EMAIL},
        ],
    }
    r = admin_session.post(f"{BASE_URL}/api/properties", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    # cleanup
    admin_session.delete(f"{BASE_URL}/api/properties/{pid}")
    mongo.properties.delete_many({"name": "TEST LINK PROP ITER17"})


@pytest.fixture(scope="session")
def linked_project(admin_session):
    payload = {
        "name": "TEST LINK PROJ ITER17",
        "land_cost": 1000000,
        "stamp_duty": 0,
        "partners": [
            {"name": "Yash", "percentage": 60, "email": ADMIN_EMAIL},
            {"name": "Link Test User", "percentage": 40, "email": TEST_USER_EMAIL},
        ],
    }
    r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    admin_session.delete(f"{BASE_URL}/api/projects/{pid}")
    mongo.projects.delete_many({"name": "TEST LINK PROJ ITER17"})


# --- 1. Property email persistence ---

class TestPropertyLinkPersistence:
    def test_property_partners_email_persisted(self, admin_session, linked_property):
        r = admin_session.get(f"{BASE_URL}/api/properties")
        assert r.status_code == 200
        props = r.json()
        p = next((x for x in props if x["id"] == linked_property), None)
        assert p is not None
        emails = {pt.get("email") for pt in p["partners"]}
        assert ADMIN_EMAIL in emails
        assert TEST_USER_EMAIL in emails  # lowercased server-side already lowercase


# --- 2. Partner property view ---

class TestPartnerPropertyView:
    def test_shared_property_visible_to_partner(self, user_session, linked_property):
        r = user_session.get(f"{BASE_URL}/api/properties")
        assert r.status_code == 200
        props = r.json()
        p = next((x for x in props if x["id"] == linked_property), None)
        assert p is not None, "linked property not visible to partner"
        assert p.get("shared") is True

    def test_partner_cannot_update_property(self, user_session, linked_property):
        r = user_session.put(f"{BASE_URL}/api/properties/{linked_property}", json={
            "name": "HACK", "address": "x", "current_value": 1, "debt": 0,
            "monthly_rent": 0, "currency": "AUD", "partners": [],
        })
        assert r.status_code == 404, f"expected 404, got {r.status_code}"

    def test_partner_cannot_delete_property(self, user_session, linked_property):
        r = user_session.delete(f"{BASE_URL}/api/properties/{linked_property}")
        assert r.status_code == 404

    def test_dashboard_property_equity_is_share(self, user_session, linked_property):
        r = user_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        # 40% of 400k = 160k; partner has no other properties
        prop_equity = data.get("property_equity") or data.get("prop_value") or data.get("properties_equity")
        # Try common key: scan for 160000 in response
        dumped = str(data)
        assert "160000" in dumped or any(
            abs(v - 160000) < 1 for v in _collect_numbers(data)
        ), f"expected 160000 in dashboard, got: {dumped[:500]}"


def _collect_numbers(obj):
    nums = []
    if isinstance(obj, dict):
        for v in obj.values():
            nums.extend(_collect_numbers(v))
    elif isinstance(obj, list):
        for v in obj:
            nums.extend(_collect_numbers(v))
    elif isinstance(obj, (int, float)):
        nums.append(float(obj))
    return nums


# --- 3. Partner project equity ---

class TestPartnerProjectEquity:
    def test_project_visible_to_partner(self, user_session, linked_project):
        r = user_session.get(f"{BASE_URL}/api/projects")
        assert r.status_code == 200
        projs = r.json()
        p = next((x for x in projs if x["id"] == linked_project), None)
        assert p is not None
        assert p.get("shared") is True

    def test_dashboard_project_position_shared(self, user_session, linked_project):
        r = user_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        projects = (data.get("projects") or {}).get("list", [])
        matched = [p for p in projects if p.get("id") == linked_project]
        assert matched, f"linked project not in dashboard projects: {data}"
        pp = matched[0]
        assert pp.get("shared") is True
        # 40% of (1,000,000 - 0 drawn) = 400,000
        assert abs(pp.get("my_equity", 0) - 400000) < 1, f"my_equity={pp.get('my_equity')}"
        assert pp.get("my_percentage") == 40

    def test_partner_cannot_update_project(self, user_session, linked_project):
        r = user_session.put(f"{BASE_URL}/api/projects/{linked_project}", json={
            "name": "HACK", "land_cost": 1, "stamp_duty": 0, "partners": [],
        })
        assert r.status_code == 403

    def test_partner_cannot_delete_project(self, user_session, linked_project):
        r = user_session.delete(f"{BASE_URL}/api/projects/{linked_project}")
        assert r.status_code == 403

    def test_partner_can_add_own_contribution(self, user_session, linked_project):
        r = user_session.post(f"{BASE_URL}/api/projects/{linked_project}/contributions", json={
            "date": "2025-01-15", "amount": 1000, "partner": "Link Test User", "description": "test"
        })
        assert r.status_code == 200, r.text

    def test_partner_cannot_add_other_contribution(self, user_session, linked_project):
        r = user_session.post(f"{BASE_URL}/api/projects/{linked_project}/contributions", json={
            "date": "2025-01-15", "amount": 1000, "partner": "Yash", "description": "test"
        })
        assert r.status_code == 403


# --- 4. Owner regression ---

class TestOwnerRegression:
    def test_owner_dashboard_ok(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200

    def test_owner_sees_property_without_shared(self, admin_session, linked_property):
        r = admin_session.get(f"{BASE_URL}/api/properties")
        p = next((x for x in r.json() if x["id"] == linked_property), None)
        assert p is not None
        assert p.get("shared") is False

    def test_unlink_removes_from_partner_view(self, admin_session, user_session, linked_property):
        # Remove partner email, keep only admin
        r = admin_session.put(f"{BASE_URL}/api/properties/{linked_property}", json={
            "name": "TEST LINK PROP ITER17",
            "address": "Test addr",
            "current_value": 400000,
            "debt": 0,
            "monthly_rent": 0,
            "currency": "AUD",
            "partners": [{"name": "Yash", "percentage": 100, "email": ADMIN_EMAIL}],
        })
        assert r.status_code == 200
        # Partner view
        r2 = user_session.get(f"{BASE_URL}/api/properties")
        assert r2.status_code == 200
        ids = [p["id"] for p in r2.json()]
        assert linked_property not in ids
        # Restore link so other tests not disturbed (but ordering may not matter now)
        admin_session.put(f"{BASE_URL}/api/properties/{linked_property}", json={
            "name": "TEST LINK PROP ITER17",
            "address": "Test addr",
            "current_value": 400000,
            "debt": 0,
            "monthly_rent": 0,
            "currency": "AUD",
            "partners": [
                {"name": "Yash", "percentage": 60, "email": ADMIN_EMAIL},
                {"name": "Link Test User", "percentage": 40, "email": TEST_USER_EMAIL},
            ],
        })


# --- 5. People endpoint ---

class TestPeopleAccess:
    def test_admin_can_list_people(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/people")
        assert r.status_code == 200

    def test_non_admin_people_forbidden(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/people")
        assert r.status_code in (403, 401)
