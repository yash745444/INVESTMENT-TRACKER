"""Iteration 6 tests: property share bug fix, external lender, people registry, visibility, member contributions, duplicate pre-fill (via API)."""
import os
import time
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta, timezone

def _read_env(path, key):
    try:
        for line in open(path):
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

ADMIN_EMAIL = "yash.sojitra34@gmail.com"
ADMIN_PASS = "Yash@2026"
MONGO_URL = (os.environ.get("MONGO_URL")
             or _read_env("/app/backend/.env", "MONGO_URL")
             or "mongodb://localhost:27017")
DB_NAME = (os.environ.get("DB_NAME")
           or _read_env("/app/backend/.env", "DB_NAME")
           or "test_database")


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def test_user(mongo):
    """Create a Google-flow test user with session_token (per /app/auth_testing.md)."""
    email = f"test.user.{int(time.time())}@example.com"
    uid = ObjectId()
    token = f"test_session_{int(time.time())}"
    mongo.users.insert_one({
        "_id": uid, "email": email, "name": "Test User",
        "role": "user", "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "user_id": str(uid),
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"id": str(uid), "email": email, "token": token}
    mongo.users.delete_one({"_id": uid})
    mongo.user_sessions.delete_many({"session_token": token})


def _user_client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ----- BUG FIX: property partner share -----

class TestPropertyShareBug:
    def test_dashboard_property_equity_delta_uses_my_percentage(self, admin):
        base = admin.get(f"{BASE_URL}/api/dashboard").json()
        base_equity = base["net_worth"]  # delta approach

        # Create property val=1,000,000 debt=400,000, Yash 50 / Sanjay 50
        prop = admin.post(f"{BASE_URL}/api/properties", json={
            "name": "TEST_PROP_SHARE",
            "address": "", "current_value": 1_000_000, "debt": 400_000,
            "currency": "AUD", "monthly_rent": 0,
            "partners": [{"name": "Yash", "percentage": 50},
                         {"name": "Sanjay", "percentage": 50}],
        }).json()
        pid = prop["id"]

        try:
            after = admin.get(f"{BASE_URL}/api/dashboard").json()
            delta = after["net_worth"] - base_equity
            # equity added = (1,000,000 - 400,000) * 50% = 300,000
            assert abs(delta - 300_000) < 1.0, f"Expected delta 300k, got {delta}"
        finally:
            admin.delete(f"{BASE_URL}/api/properties/{pid}")

    def test_dashboard_no_partners_is_full_equity(self, admin):
        base = admin.get(f"{BASE_URL}/api/dashboard").json()["net_worth"]
        prop = admin.post(f"{BASE_URL}/api/properties", json={
            "name": "TEST_PROP_SOLO", "current_value": 500_000, "debt": 100_000,
            "currency": "AUD", "monthly_rent": 0, "partners": [],
        }).json()
        pid = prop["id"]
        try:
            after = admin.get(f"{BASE_URL}/api/dashboard").json()["net_worth"]
            delta = after - base
            assert abs(delta - 400_000) < 1.0, f"Expected delta 400k, got {delta}"
        finally:
            admin.delete(f"{BASE_URL}/api/properties/{pid}")


# ----- Shared property visibility -----

class TestSharedPropertyVisibility:
    def test_shared_property_appears_for_partner(self, admin, test_user):
        prop = admin.post(f"{BASE_URL}/api/properties", json={
            "name": "TEST_PROP_SHARED",
            "current_value": 800_000, "debt": 200_000,
            "currency": "AUD", "monthly_rent": 0,
            "partners": [{"name": "Yash", "percentage": 60},
                         {"name": "TestUser", "percentage": 40, "email": test_user["email"]}],
        }).json()
        pid = prop["id"]
        try:
            client = _user_client(test_user["token"])
            r = client.get(f"{BASE_URL}/api/properties")
            assert r.status_code == 200, r.text
            lst = r.json()
            match = [p for p in lst if p["id"] == pid]
            assert len(match) == 1
            assert match[0]["shared"] is True

            # dashboard delta for test user = 40% × (800k - 200k) = 240k
            # Baseline (test user has no other data) should equal 240k approx
            dash = client.get(f"{BASE_URL}/api/dashboard").json()
            # Could include fx noise but should be in that ballpark
            assert dash["net_worth"] >= 239_000 and dash["net_worth"] <= 241_000, \
                f"Expected ~240k, got {dash['net_worth']}"
        finally:
            admin.delete(f"{BASE_URL}/api/properties/{pid}")


# ----- External lender ledger -----

class TestExternalLender:
    def test_external_ledger_entry(self, admin):
        entry = admin.post(f"{BASE_URL}/api/ledger", json={
            "date": "2025-01-01", "type": "external",
            "from_partner": "TEST_ExtLender", "to_partner": "Company",
            "amount": 10000, "note": "TEST"
        })
        assert entry.status_code == 200, entry.text
        tid = entry.json()["id"]
        try:
            bal = admin.get(f"{BASE_URL}/api/ledger/balances").json()
            extras = bal.get("extras", {})
            assert "TEST_ExtLender" in extras, f"extras: {extras}"
            assert abs(extras["TEST_ExtLender"] - 10000) < 0.01
        finally:
            admin.delete(f"{BASE_URL}/api/ledger/{tid}")

    def test_external_rejects_invalid_type(self, admin):
        r = admin.post(f"{BASE_URL}/api/ledger", json={
            "date": "2025-01-01", "type": "bogus",
            "from_partner": "A", "to_partner": "B", "amount": 1,
        })
        assert r.status_code == 400


# ----- People registry CRUD + profile -----

class TestPeopleRegistry:
    def test_people_crud_and_profile(self, admin):
        created = admin.post(f"{BASE_URL}/api/people", json={
            "name": "TEST_Person2", "email": "test.person2@example.com",
            "visibility": {"projects": True, "properties": True, "debts": False, "loans": True},
        })
        assert created.status_code == 200, created.text
        pid = created.json()["id"]
        try:
            lst = admin.get(f"{BASE_URL}/api/people").json()
            assert any(p["id"] == pid for p in lst)

            prof = admin.get(f"{BASE_URL}/api/people/{pid}/profile")
            assert prof.status_code == 200, prof.text
            data = prof.json()
            for key in ("name", "email", "visibility", "position", "projects", "properties", "loans", "personal"):
                assert key in data, f"missing {key}"
            assert data["visibility"]["debts"] is False

            upd = admin.put(f"{BASE_URL}/api/people/{pid}", json={
                "name": "TEST_Person2", "email": "test.person2@example.com",
                "visibility": {"projects": True, "properties": True, "debts": True, "loans": True},
            })
            assert upd.status_code == 200
            assert upd.json()["visibility"]["debts"] is True
        finally:
            admin.delete(f"{BASE_URL}/api/people/{pid}")

    def test_people_admin_only(self, admin, test_user):
        client = _user_client(test_user["token"])
        r = client.get(f"{BASE_URL}/api/people")
        # Should be 403 since non-admin
        assert r.status_code in (403, 401), f"Expected 403, got {r.status_code}: {r.text}"


# ----- Visibility control on /api/partner/overview -----

class TestVisibilityControl:
    def test_visibility_toggle_affects_overview(self, admin, test_user, mongo):
        # Set partner_name = Sanjay for test user
        r = admin.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/partner",
                       json={"partner_name": "Sanjay"})
        assert r.status_code == 200, r.text

        # Create person entry Sanjay with debts=False
        p = admin.post(f"{BASE_URL}/api/people", json={
            "name": "Sanjay", "email": test_user["email"],
            "visibility": {"projects": True, "properties": True, "debts": False, "loans": True},
        }).json()
        pid = p["id"]
        try:
            client = _user_client(test_user["token"])
            r = client.get(f"{BASE_URL}/api/partner/overview")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["scope"] == "self"
            assert data["position"] is None
            assert data["personal"] == []

            # Toggle debts ON
            admin.put(f"{BASE_URL}/api/people/{pid}", json={
                "name": "Sanjay", "email": test_user["email"],
                "visibility": {"projects": True, "properties": True, "debts": True, "loans": True},
            })
            data2 = client.get(f"{BASE_URL}/api/partner/overview").json()
            assert data2["position"] is not None  # Could be 0.0 or number but not None
        finally:
            admin.delete(f"{BASE_URL}/api/people/{pid}")


# ----- Member contributions on shared project -----

class TestMemberContributions:
    def test_member_can_add_only_under_own_partner_name(self, admin, test_user, mongo):
        # Set partner name
        admin.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/partner",
                   json={"partner_name": "TestPartner"})

        # Create shared project
        proj = admin.post(f"{BASE_URL}/api/projects", json={
            "name": "TEST_SharedProj",
            "partners": [{"name": "Yash", "percentage": 50},
                         {"name": "TestPartner", "percentage": 50,
                          "email": test_user["email"]}],
        }).json()
        pid = proj["id"]
        try:
            client = _user_client(test_user["token"])
            # own name: ok
            ok = client.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
                "date": "2025-01-01", "partner": "TestPartner",
                "amount": 5000, "description": "TEST"
            })
            assert ok.status_code == 200, ok.text
            cid = ok.json()["id"]

            # other name: 403
            bad = client.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
                "date": "2025-01-01", "partner": "Yash",
                "amount": 5000, "description": "TEST_BAD"
            })
            assert bad.status_code == 403

            # cannot delete (not own contribution record user_id)
            # Actually contribution has user_id = project owner's id. So delete by member returns 403.
            dr = client.delete(f"{BASE_URL}/api/contributions/{cid}")
            assert dr.status_code == 403
        finally:
            admin.delete(f"{BASE_URL}/api/projects/{pid}")  # cascades contributions


# ----- Privacy: member's private data invisible to admin -----

class TestPrivacy:
    def test_member_investment_hidden_from_admin(self, admin, test_user):
        client = _user_client(test_user["token"])
        inv = client.post(f"{BASE_URL}/api/investments", json={
            "type": "other", "name": "TEST_PRIVATE_INV", "amount": 1234,
            "currency": "AUD", "date": "2025-01-01",
        })
        assert inv.status_code == 200, inv.text
        iid = inv.json()["id"]
        try:
            admin_list = admin.get(f"{BASE_URL}/api/investments").json()
            assert not any(i["id"] == iid for i in admin_list), "Admin saw member's investment"
            admin_pl = admin.get(f"{BASE_URL}/api/personal-loans").json()
            # Just a sanity check
            assert isinstance(admin_pl, list)
        finally:
            client.delete(f"{BASE_URL}/api/investments/{iid}")


# ----- Regression -----

class TestRegression:
    def test_login_me(self, admin):
        r = admin.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_dashboard_shape(self, admin):
        d = admin.get(f"{BASE_URL}/api/dashboard").json()
        for k in ("net_worth", "net_worth_without_debts", "debts"):
            assert k in d
        for k in ("property_debt", "project_loans", "personal_loans", "total"):
            assert k in d["debts"]

    def test_shares_pin(self, admin):
        r = admin.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "2468"})
        assert r.status_code == 200
        r2 = admin.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "9999"})
        assert r2.status_code == 403

    def test_partner_overview_admin_scope_all(self, admin):
        r = admin.get(f"{BASE_URL}/api/partner/overview").json()
        assert r["scope"] == "all"
        assert len(r["profiles"]) >= 4
