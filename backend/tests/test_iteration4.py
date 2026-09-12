"""Backend regression tests for Iteration 4 (multi-user).

Covers:
- Email/password login + /auth/me returns role/status
- Admin endpoints (list users, set status, delete safeguard)
- Google user simulation via mongosh (pending -> 403 -> approve -> 200)
- Data isolation between users
- Project sharing via partner email
- Project owner-only mutations (delete/contrib/cost)
- Feasibility CRUD + computed metrics
- Personal debt ledger (separate from company pool)
- Regression: shares PIN unlock, dashboard
"""
import os
import time
import subprocess
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # read from frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "yash.sojitra34@gmail.com"
ADMIN_PASSWORD = "Yash@2026"
PIN = "2468"

# ---------- fixtures ----------

@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "admin"
    assert data["status"] == "approved"
    return s


@pytest.fixture(scope="session")
def test_user():
    """Create a pending google-simulated user + session via mongosh."""
    email = f"test.user.{int(time.time())}@example.com"
    js = f"""
    use('test_database');
    var uid = new ObjectId();
    var token = 'test_session_{int(time.time())}';
    db.users.insertOne({{
      _id: uid, email: '{email}', name: 'TEST User',
      role: 'user', status: 'pending',
      created_at: new Date().toISOString()
    }});
    db.user_sessions.insertOne({{
      user_id: uid.toString(), session_token: token,
      expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString(),
      created_at: new Date().toISOString()
    }});
    print('UID:' + uid.toString());
    print('TOKEN:' + token);
    """
    r = subprocess.run(["mongosh", "--quiet", "--eval", js], capture_output=True, text=True)
    out = r.stdout
    uid = [l for l in out.splitlines() if l.startswith("UID:")][0].split(":", 1)[1].strip()
    token = [l for l in out.splitlines() if l.startswith("TOKEN:")][0].split(":", 1)[1].strip()
    yield {"id": uid, "email": email, "token": token}
    # cleanup
    subprocess.run(["mongosh", "--quiet", "--eval", f"""
    use('test_database');
    db.users.deleteOne({{_id: ObjectId('{uid}')}});
    db.user_sessions.deleteMany({{user_id: '{uid}'}});
    db.projects.deleteMany({{user_id: '{uid}'}});
    db.investments.deleteMany({{user_id: '{uid}'}});
    db.feasibility.deleteMany({{user_id: '{uid}'}});
    db.ledger.deleteMany({{user_id: '{uid}'}});
    """], capture_output=True, text=True)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- auth / me ----------

class TestAuthMe:
    def test_login_returns_role_status(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "admin"
        assert d["status"] == "approved"
        assert d["email"] == ADMIN_EMAIL

    def test_me_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "admin"
        assert d["status"] == "approved"
        assert "password_hash" not in d


# ---------- pending user gating ----------

class TestPendingGating:
    def test_pending_me_works(self, test_user):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=bearer(test_user["token"]))
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_pending_dashboard_403(self, test_user):
        r = requests.get(f"{BASE_URL}/api/dashboard", headers=bearer(test_user["token"]))
        assert r.status_code == 403
        assert "pending_approval" in r.text

    def test_pending_projects_403(self, test_user):
        r = requests.get(f"{BASE_URL}/api/projects", headers=bearer(test_user["token"]))
        assert r.status_code == 403


# ---------- admin ----------

class TestAdmin:
    def test_list_users(self, admin_session, test_user):
        r = admin_session.get(f"{BASE_URL}/api/admin/users")
        assert r.status_code == 200
        users = r.json()
        assert any(u["email"] == ADMIN_EMAIL and u["role"] == "admin" for u in users)
        assert any(u["email"] == test_user["email"] for u in users)

    def test_non_admin_forbidden(self, test_user):
        # first approve them so pending gating doesn't hide the admin check
        # actually pending gating triggers 403 pending_approval first, but role check comes later
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=bearer(test_user["token"]))
        assert r.status_code == 403

    def test_admin_cannot_delete_self(self, admin_session):
        me = admin_session.get(f"{BASE_URL}/api/auth/me").json()
        r = admin_session.delete(f"{BASE_URL}/api/admin/users/{me['id']}")
        assert r.status_code == 400

    def test_approve_user(self, admin_session, test_user):
        r = admin_session.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/status",
                               json={"status": "approved"})
        assert r.status_code == 200
        # verify: user now can hit /api/dashboard
        r2 = requests.get(f"{BASE_URL}/api/dashboard", headers=bearer(test_user["token"]))
        assert r2.status_code == 200

    def test_approved_user_empty_isolated_data(self, test_user):
        # after approval, dashboard should be zeros (isolated)
        r = requests.get(f"{BASE_URL}/api/dashboard", headers=bearer(test_user["token"]))
        assert r.status_code == 200
        d = r.json()
        # projects list should be empty for isolation
        assert d["projects"]["list"] == []
        assert d["properties"]["value"] == 0
        # investments total may be 0 since none created
        assert d["investments"]["total"] == 0


# ---------- data isolation ----------

class TestIsolation:
    def test_investment_isolation(self, admin_session, test_user):
        # get admin baseline
        admin_before = admin_session.get(f"{BASE_URL}/api/investments").json()
        admin_count_before = len(admin_before)
        # test user creates investment
        payload = {"type": "other", "name": "TEST_ISO_INV", "currency": "AUD", "amount": 12345}
        r = requests.post(f"{BASE_URL}/api/investments", json=payload,
                          headers=bearer(test_user["token"]))
        assert r.status_code == 200
        iid = r.json()["id"]
        # admin does NOT see it
        admin_after = admin_session.get(f"{BASE_URL}/api/investments").json()
        names = [i.get("name") for i in admin_after]
        assert "TEST_ISO_INV" not in names
        assert len(admin_after) == admin_count_before
        # test user does see it
        tu_list = requests.get(f"{BASE_URL}/api/investments",
                               headers=bearer(test_user["token"])).json()
        assert any(i["name"] == "TEST_ISO_INV" for i in tu_list)
        # cleanup
        requests.delete(f"{BASE_URL}/api/investments/{iid}", headers=bearer(test_user["token"]))


# ---------- project sharing + owner-only ----------

class TestProjectSharing:
    def test_shared_project_flow(self, admin_session, test_user):
        # admin creates a TEST project with test_user email as partner
        payload = {
            "name": "TEST_SHARED_PROJECT",
            "address": "1 Test St",
            "status": "active",
            "partners": [
                {"name": "Yash", "percentage": 50, "email": ADMIN_EMAIL},
                {"name": "Sanjay", "percentage": 50, "email": test_user["email"]},
            ],
        }
        r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        # test_user sees it in /projects with shared=True
        r2 = requests.get(f"{BASE_URL}/api/projects", headers=bearer(test_user["token"]))
        assert r2.status_code == 200
        matches = [p for p in r2.json() if p["id"] == pid]
        assert len(matches) == 1
        assert matches[0]["shared"] is True

        # test_user cannot POST contribution to shared project
        r3 = requests.post(f"{BASE_URL}/api/projects/{pid}/contributions",
                           json={"date": "2026-01-01", "partner": "Sanjay", "amount": 100},
                           headers=bearer(test_user["token"]))
        assert r3.status_code == 403

        # test_user cannot POST cost
        r4 = requests.post(f"{BASE_URL}/api/projects/{pid}/costs",
                           json={"date": "2026-01-01", "category": "misc", "amount": 100},
                           headers=bearer(test_user["token"]))
        assert r4.status_code == 403

        # test_user cannot delete owner's project
        r5 = requests.delete(f"{BASE_URL}/api/projects/{pid}",
                             headers=bearer(test_user["token"]))
        assert r5.status_code == 403

        # owner can delete
        r6 = admin_session.delete(f"{BASE_URL}/api/projects/{pid}")
        assert r6.status_code == 200

        # gone
        r7 = admin_session.get(f"{BASE_URL}/api/projects")
        assert not any(p["id"] == pid for p in r7.json())


# ---------- feasibility ----------

class TestFeasibility:
    def test_feasible_case(self, admin_session):
        payload = {"name": "TEST_FS_OK", "land_cost": 500000, "construction_cost": 1000000,
                   "contingency_pct": 10, "expected_revenue": 2000000}
        r = admin_session.post(f"{BASE_URL}/api/feasibility", json=payload)
        assert r.status_code == 200
        d = r.json()
        c = d["computed"]
        assert c["total_cost"] == 1600000
        assert c["profit"] == 400000
        assert c["margin_pct"] == 20.0
        assert c["feasible"] is True
        # delete
        admin_session.delete(f"{BASE_URL}/api/feasibility/{d['id']}")

    def test_not_feasible_case(self, admin_session):
        payload = {"name": "TEST_FS_BAD", "land_cost": 500000, "construction_cost": 1000000,
                   "contingency_pct": 10, "expected_revenue": 1000000}
        r = admin_session.post(f"{BASE_URL}/api/feasibility", json=payload)
        assert r.status_code == 200
        c = r.json()["computed"]
        assert c["profit"] < 0
        assert c["feasible"] is False
        admin_session.delete(f"{BASE_URL}/api/feasibility/{r.json()['id']}")

    def test_list_and_delete_persistence(self, admin_session):
        payload = {"name": "TEST_FS_LIST", "land_cost": 100, "construction_cost": 100,
                   "contingency_pct": 0, "expected_revenue": 500}
        r = admin_session.post(f"{BASE_URL}/api/feasibility", json=payload)
        fid = r.json()["id"]
        lst = admin_session.get(f"{BASE_URL}/api/feasibility").json()
        assert any(f["id"] == fid for f in lst)
        admin_session.delete(f"{BASE_URL}/api/feasibility/{fid}")
        lst2 = admin_session.get(f"{BASE_URL}/api/feasibility").json()
        assert not any(f["id"] == fid for f in lst2)


# ---------- personal debts ----------

class TestPersonalDebts:
    def test_personal_ledger(self, admin_session):
        # cleanup any prior TEST personal entries
        before = admin_session.get(f"{BASE_URL}/api/ledger").json()
        pre_personal_ids = [t["id"] for t in before if t.get("type") == "personal" and "TEST" in (t.get("note", ""))]
        for tid in pre_personal_ids:
            admin_session.delete(f"{BASE_URL}/api/ledger/{tid}")

        # capture company balances baseline
        bal_before = admin_session.get(f"{BASE_URL}/api/ledger/balances").json()

        # add "I paid for them" Sanjay 2000 -> from=Yash to=Sanjay (Sanjay owes Yash)
        r = admin_session.post(f"{BASE_URL}/api/ledger", json={
            "date": "2026-01-01", "type": "personal",
            "from_partner": "Yash", "to_partner": "Sanjay",
            "amount": 2000, "note": "TEST_PERSONAL_1"})
        assert r.status_code == 200
        id1 = r.json()["id"]

        per = admin_session.get(f"{BASE_URL}/api/ledger/personal").json()
        pair = next((p for p in per["pairs"] if p["debtor"] == "Sanjay" and p["creditor"] == "Yash"), None)
        assert pair and pair["amount"] == 2000

        # add "They paid for me" 500 -> from=Sanjay to=Yash
        r2 = admin_session.post(f"{BASE_URL}/api/ledger", json={
            "date": "2026-01-02", "type": "personal",
            "from_partner": "Sanjay", "to_partner": "Yash",
            "amount": 500, "note": "TEST_PERSONAL_2"})
        id2 = r2.json()["id"]

        per2 = admin_session.get(f"{BASE_URL}/api/ledger/personal").json()
        pair2 = next((p for p in per2["pairs"] if p["debtor"] == "Sanjay" and p["creditor"] == "Yash"), None)
        assert pair2 and pair2["amount"] == 1500

        # company balances unchanged
        bal_after = admin_session.get(f"{BASE_URL}/api/ledger/balances").json()
        assert bal_after["totals"] == bal_before["totals"]

        # report includes personal
        rep = admin_session.get(f"{BASE_URL}/api/ledger/report").json()
        assert "personal" in rep and "personal_transactions" in rep
        assert len(rep["personal_transactions"]) >= 2

        # delete personal entries
        r3 = admin_session.delete(f"{BASE_URL}/api/ledger/{id1}")
        assert r3.status_code == 200
        admin_session.delete(f"{BASE_URL}/api/ledger/{id2}")


# ---------- regression ----------

class TestRegression:
    def test_dashboard(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        assert "net_worth" in d
        # Yash should have MAISON 7
        names = [p["name"] for p in d["projects"]["list"]]
        assert "MAISON 7" in names or len(names) >= 1

    def test_shares_unlock(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/shares/unlock", json={"pin": PIN})
        assert r.status_code == 200

    def test_shares_wrong_pin(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "0000"})
        assert r.status_code == 403
