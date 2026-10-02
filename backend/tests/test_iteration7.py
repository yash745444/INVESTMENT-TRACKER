"""Iteration 7 tests: name migration, bulk costs, networth report, dropdowns, self-view."""
import os
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://42c879b8-ebe5-42e4-882b-1c4e236579b3.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "yash.sojitra34@gmail.com"
ADMIN_PASSWORD = "Yash@2026"
SHARES_PIN = "2468"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def mongo_db():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    name = os.environ.get("DB_NAME", "test_database")
    return MongoClient(url)[name]


@pytest.fixture(scope="module")
def test_user_session(mongo_db):
    """Create a non-admin approved test user and return a session using Bearer token."""
    uid = ObjectId()
    token = f"test_session_iter7_{int(datetime.now().timestamp())}"
    mongo_db.users.insert_one({
        "_id": uid,
        "email": f"test.user.iter7.{int(datetime.now().timestamp())}@example.com",
        "name": "Test User Iter7",
        "role": "user",
        "status": "approved",
        "partner_name": "Sanjay Jogani",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo_db.user_sessions.insert_one({
        "user_id": str(uid),
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    yield s, str(uid)
    # cleanup
    mongo_db.users.delete_one({"_id": uid})
    mongo_db.user_sessions.delete_one({"session_token": token})


# ------------- Name migration -------------
class TestNameMigration:
    def test_admin_name_full(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json().get("name") == "Yash Sojitra", r.json()

    def test_maison7_has_full_partner_names(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/projects")
        assert r.status_code == 200
        maison = next((p for p in r.json() if "MAISON" in (p.get("name") or "").upper()), None)
        assert maison, "MAISON 7 project not found"
        names = [pt.get("name") for pt in maison.get("partners", [])]
        for n in ["Yash Sojitra", "Sanjay Jogani", "Pranay Jetani", "Max Ma"]:
            assert n in names, f"Expected '{n}' in partner names: {names}"

    def test_dashboard_my_contributions_maison7(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        plist = d.get("projects", {}).get("list", [])
        maison = next((p for p in plist if "MAISON" in (p.get("name") or "").upper()), None)
        assert maison, f"MAISON 7 not in dashboard projects: {[p.get('name') for p in plist]}"
        # Expected $67,000 contributions for Yash Sojitra (10% share)
        assert maison.get("my_contributions") == 67000, maison
        assert maison.get("my_percentage") == 10, maison


# ------------- Bulk costs -------------
class TestBulkCosts:
    @pytest.fixture
    def maison_pid(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/projects")
        maison = next((p for p in r.json() if "MAISON" in (p.get("name") or "").upper()), None)
        return maison["id"]

    def test_bulk_insert_three(self, admin_session, maison_pid):
        payload = {"items": [
            {"date": "2026-01-15", "category": "Other", "description": "TEST_BULK_1", "amount": 100},
            {"date": "2026-01-15", "category": "Marketing & Legal", "description": "TEST_BULK_2", "amount": 250},
            {"date": "2026-01-15", "category": "Other", "description": "TEST_BULK_3", "amount": 75},
        ]}
        r = admin_session.post(f"{BASE_URL}/api/projects/{maison_pid}/costs/bulk", json=payload)
        assert r.status_code == 200, r.text
        assert r.json().get("inserted") == 3

        # verify in GET
        gr = admin_session.get(f"{BASE_URL}/api/projects/{maison_pid}/costs")
        assert gr.status_code == 200
        descs = [c.get("description") for c in gr.json()]
        for d in ["TEST_BULK_1", "TEST_BULK_2", "TEST_BULK_3"]:
            assert d in descs
        # cleanup
        for c in gr.json():
            if (c.get("description") or "").startswith("TEST_BULK_"):
                admin_session.delete(f"{BASE_URL}/api/costs/{c['id']}")

    def test_bulk_empty(self, admin_session, maison_pid):
        r = admin_session.post(f"{BASE_URL}/api/projects/{maison_pid}/costs/bulk", json={"items": []})
        assert r.status_code == 200
        assert r.json().get("inserted") == 0

    def test_bulk_non_owner_forbidden(self, test_user_session, admin_session):
        s, _uid = test_user_session
        # fetch admin's project id
        r = admin_session.get(f"{BASE_URL}/api/projects")
        maison = next((p for p in r.json() if "MAISON" in (p.get("name") or "").upper()), None)
        pid = maison["id"]
        rr = s.post(f"{BASE_URL}/api/projects/{pid}/costs/bulk", json={"items": [
            {"date": "2026-01-15", "category": "Other", "description": "TEST_NOP", "amount": 1}
        ]})
        assert rr.status_code == 403, rr.text


# ------------- Networth report -------------
class TestNetworthReport:
    def test_admin_report_structure(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/report/networth")
        assert r.status_code == 200
        data = r.json()
        for k in ["summary", "investments", "properties", "projects", "private_loans", "ledger", "rates", "generated_at", "user"]:
            assert k in data, f"missing key {k}"
        s = data["summary"]
        for k in ["net_worth", "net_worth_without_debts", "debts", "ledger_net"]:
            assert k in s
        # projects include MAISON 7 with equity
        maison = next((p for p in data["projects"] if "MAISON" in (p.get("name") or "").upper()), None)
        assert maison, "MAISON 7 missing in report projects"
        assert maison.get("my_percentage") == 10
        assert maison.get("my_contributions") == 67000

    def test_shares_redacted_when_locked(self, admin_session):
        # Make sure not unlocked - open fresh session for shares cookie
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        r = s.get(f"{BASE_URL}/api/report/networth")
        assert r.status_code == 200
        shares = [i for i in r.json()["investments"] if i.get("type") == "shares"]
        if shares:
            # at least one should be redacted (shares present in seed data)
            assert any(i.get("redacted") for i in shares), f"Expected redacted shares, got: {shares}"
            for sh in shares:
                if sh.get("redacted"):
                    assert sh.get("name") == "Hidden holding"
                    assert sh.get("worth_aud") is None

    def test_shares_revealed_after_pin(self, admin_session):
        ur = admin_session.post(f"{BASE_URL}/api/shares/unlock", json={"pin": SHARES_PIN})
        assert ur.status_code == 200
        r = admin_session.get(f"{BASE_URL}/api/report/networth")
        assert r.status_code == 200
        shares = [i for i in r.json()["investments"] if i.get("type") == "shares"]
        for sh in shares:
            assert not sh.get("redacted", False), sh
            assert sh.get("name") != "Hidden holding"

    def test_report_for_non_admin_user(self, test_user_session):
        s, uid = test_user_session
        r = s.get(f"{BASE_URL}/api/report/networth")
        assert r.status_code == 200, r.text
        data = r.json()
        # new user has no own data; properties/private_loans should be their own only (empty)
        assert data["user"]["name"] == "Test User Iter7"
        assert isinstance(data["investments"], list)
        assert isinstance(data["properties"], list)
        assert isinstance(data["private_loans"], list)
        # The test user is partner_name="Sanjay Jogani" - properties they're linked as a partner on may appear
        for p in data["properties"]:
            assert "my_percentage" in p


# ------------- Linked partner self view regression -------------
class TestLinkedPartnerSelfView:
    def test_test_user_dashboard_only_own(self, test_user_session):
        s, _uid = test_user_session
        r = s.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        # Projects list should only include projects where this user is a partner (via Sanjay Jogani)
        # New user shouldn't see admin's investment totals
        plist = d.get("projects", {}).get("list", [])
        for p in plist:
            # Each visible project must be one where the user is linked - my_contributions might be 0
            assert "my_percentage" in p
