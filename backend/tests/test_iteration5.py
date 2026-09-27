"""Iteration 5 backend tests: personal loans, project profit, partner overview,
admin partner-link, feasibility v2, dashboard with debts, MAISON 7 equity math."""
import os
import time
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EMAIL = "yash.sojitra34@gmail.com"
PASSWORD = "Yash@2026"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def maison7_id(s):
    r = s.get(f"{BASE_URL}/api/projects", timeout=10)
    assert r.status_code == 200
    for p in r.json():
        if "MAISON 7" in p.get("name", "").upper() or "MAISON7" in p.get("name", "").upper():
            return p["id"]
    pytest.skip("MAISON 7 project not found in DB")


# -------- Personal loans (interest) --------

class TestPersonalLoansInterest:
    def test_add_and_compute_interest_loan(self, s):
        payload = {"lender": "TEST_L1", "amount": 50000, "date": "2025-09-27",
                   "type": "interest", "annual_rate": 8}
        r = s.post(f"{BASE_URL}/api/personal-loans", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        c = d["computed"]
        assert c["accrued_interest"] > 0
        assert c["total_owed"] == pytest.approx(50000 + c["accrued_interest"], rel=0.01)
        # accrued uses full-precision years; c["years"] is rounded to 2dp — allow tolerance
        expected = 50000 * 0.08 * c["years"]
        assert c["accrued_interest"] == pytest.approx(expected, abs=50)
        # cleanup
        s.delete(f"{BASE_URL}/api/personal-loans/{d['id']}", timeout=10)

    def test_invalid_type(self, s):
        r = s.post(f"{BASE_URL}/api/personal-loans",
                   json={"lender": "x", "amount": 1, "date": "2025-01-01", "type": "bad"}, timeout=10)
        assert r.status_code == 400

    def test_profit_share_requires_project_or_basis(self, s):
        r = s.post(f"{BASE_URL}/api/personal-loans",
                   json={"lender": "x", "amount": 100, "date": "2025-01-01",
                         "type": "profit_share"}, timeout=10)
        assert r.status_code == 400


# -------- Personal loans (profit share) with MAISON 7 --------

class TestProfitShareFlow:
    def test_full_flow(self, s, maison7_id):
        # Set final profit to 200000
        r = s.post(f"{BASE_URL}/api/projects/{maison7_id}/profit",
                   json={"final_profit": 200000}, timeout=10)
        assert r.status_code == 200

        # Add profit-share loan: 100k / 450k basis
        payload = {"lender": "TEST_L2", "amount": 100000, "date": "2025-01-01",
                   "type": "profit_share", "project_id": maison7_id, "basis_amount": 450000}
        r2 = s.post(f"{BASE_URL}/api/personal-loans", json=payload, timeout=10)
        assert r2.status_code == 200, r2.text
        loan = r2.json()
        c = loan["computed"]
        assert c["basis"] == 450000
        assert c["share_pct"] == pytest.approx(22.22, abs=0.02)
        assert c["project_profit"] == 200000
        assert c["return_amount"] == pytest.approx(44444.44, abs=0.5)
        assert c["total_owed"] == pytest.approx(144444.44, abs=1)

        # Dashboard personal_loans debt line reflects this
        d = s.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
        assert d["debts"]["personal_loans"] >= 144000

        # Cleanup: reset profit to 0, delete loan
        s.delete(f"{BASE_URL}/api/personal-loans/{loan['id']}", timeout=10)
        s.post(f"{BASE_URL}/api/projects/{maison7_id}/profit",
               json={"final_profit": 0}, timeout=10)


# -------- Feasibility v2 --------

class TestFeasibilityV2:
    def test_compute_feasible(self, s):
        payload = {
            "name": "TEST_FS_SUB", "project_type": "subdivision",
            "land_cost": 600000, "stamp_duty": 30000, "construction_cost": 900000,
            "contingency_pct": 10, "loan_amount": 1000000, "expected_revenue": 2200000
        }
        r = s.post(f"{BASE_URL}/api/feasibility", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        c = d["computed"]
        # TDC = 600 + 30 + 900 + 90 (contingency 10% of 900) = 1620k
        assert c["total_cost"] == pytest.approx(1620000, abs=1)
        # cash_in = 1620 - 1000 = 620k
        assert c["cash_in"] == pytest.approx(620000, abs=1)
        # profit = 2200 - 1620 = 580k
        assert c["profit"] == pytest.approx(580000, abs=1)
        # roi_cash = 580/620 * 100 ≈ 93.5%
        assert c["roi_cash_pct"] == pytest.approx(93.5, abs=0.2)
        assert c["feasible"] is True
        assert d["project_type"] == "subdivision"
        s.delete(f"{BASE_URL}/api/feasibility/{d['id']}", timeout=10)

    def test_not_feasible_low_revenue(self, s):
        payload = {
            "name": "TEST_FS_LOW", "project_type": "subdivision",
            "land_cost": 600000, "stamp_duty": 30000, "construction_cost": 900000,
            "contingency_pct": 10, "loan_amount": 1000000, "expected_revenue": 1000000
        }
        r = s.post(f"{BASE_URL}/api/feasibility", json=payload, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["computed"]["feasible"] is False
        s.delete(f"{BASE_URL}/api/feasibility/{d['id']}", timeout=10)

    def test_feasible_borderline_roi_50(self, s):
        # profit > 0 but roi_cash < 50 must be Not Feasible
        payload = {
            "name": "TEST_FS_BORDER", "project_type": "duplex",
            "land_cost": 500000, "construction_cost": 500000,
            "contingency_pct": 0, "loan_amount": 500000, "expected_revenue": 1200000
        }
        # TDC 1000k, cash 500k, profit 200k, roi_cash 40% → not feasible
        r = s.post(f"{BASE_URL}/api/feasibility", json=payload, timeout=10)
        d = r.json()
        assert d["computed"]["roi_cash_pct"] == pytest.approx(40.0, abs=0.1)
        assert d["computed"]["feasible"] is False
        s.delete(f"{BASE_URL}/api/feasibility/{d['id']}", timeout=10)


# -------- Dashboard: without-debts + debts breakdown + my_equity --------

class TestDashboardDebtsAndEquity:
    def test_dashboard_shape(self, s):
        r = s.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "net_worth" in d and "net_worth_without_debts" in d
        assert d["net_worth_without_debts"] >= d["net_worth"]  # gross >= net
        assert "debts" in d and set(["property_debt", "project_loans", "personal_loans", "total"]).issubset(d["debts"].keys())
        # projects list has my_equity + my_loan_share
        proj_list = d["projects"]["list"]
        assert len(proj_list) > 0
        for p in proj_list:
            assert "my_equity" in p and "my_loan_share" in p and "final_profit" in p

    def test_maison7_my_equity_math(self, s, maison7_id):
        # Get pre-state
        pre = s.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
        pre_proj = next(p for p in pre["projects"]["list"] if p["id"] == maison7_id)
        my_pct = pre_proj["my_percentage"]
        pre_equity = pre_proj["my_equity"]

        # Add a TEST contribution 100k and TEST cost 40k
        rc = s.post(f"{BASE_URL}/api/projects/{maison7_id}/contributions",
                    json={"date": "2026-01-05", "partner": "Yash", "amount": 100000,
                          "description": "TEST_equity_contrib"}, timeout=10)
        assert rc.status_code == 200
        cid = rc.json()["id"]
        rk = s.post(f"{BASE_URL}/api/projects/{maison7_id}/costs",
                    json={"date": "2026-01-05", "category": "Test", "description": "TEST_equity_cost",
                          "amount": 40000, "paid_by": "Yash"}, timeout=10)
        assert rk.status_code == 200
        kid = rk.json()["id"]

        # Expected delta = my_pct% * (100k - 40k) = my_pct% * 60k
        post = s.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
        post_proj = next(p for p in post["projects"]["list"] if p["id"] == maison7_id)
        expected_delta = my_pct / 100 * 60000
        assert post_proj["my_equity"] - pre_equity == pytest.approx(expected_delta, abs=1)

        # cleanup
        s.delete(f"{BASE_URL}/api/contributions/{cid}", timeout=10)
        s.delete(f"{BASE_URL}/api/costs/{kid}", timeout=10)

    def test_property_equity_by_percentage(self, s):
        # Add property with 50/50 partners → my equity = (val-debt) * 50%
        pre = s.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
        pre_eq = pre["properties"]["equity"]

        r = s.post(f"{BASE_URL}/api/properties", json={
            "name": "TEST_PROP_EQ", "address": "1 Test St", "purchase_date": "2020-01-01",
            "purchase_price": 900000, "current_value": 1000000, "monthly_rent": 0,
            "debt": 400000, "currency": "AUD",
            "partners": [{"name": "Yash", "percentage": 50}, {"name": "Sanjay", "percentage": 50}],
        }, timeout=10)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        post = s.get(f"{BASE_URL}/api/dashboard", timeout=15).json()
        # Yash equity delta should be (1M - 400k) * 50% = 300k (NOT 600k)
        delta = post["properties"]["equity"] - pre_eq
        assert delta == pytest.approx(300000, abs=1), f"got delta={delta}"

        s.delete(f"{BASE_URL}/api/properties/{pid}", timeout=10)


# -------- Partner overview (admin) --------

class TestPartnerOverviewAdmin:
    def test_admin_scope_all_four_profiles(self, s):
        r = s.get(f"{BASE_URL}/api/partner/overview", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["scope"] == "all"
        names = {p["name"] for p in d["profiles"]}
        assert {"Yash", "Sanjay", "Pranay", "Max"}.issubset(names)
        sanjay = next(p for p in d["profiles"] if p["name"] == "Sanjay")
        assert "position" in sanjay and "projects" in sanjay and "personal" in sanjay


# -------- Partner overview (self view via mongosh-simulated google user) --------

class TestPartnerOverviewSelf:
    @pytest.fixture(scope="class")
    def linked_partner_session(self, s):
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        # Create test user + session
        user_id = ObjectId()
        session_token = f"test_session_{int(time.time()*1000)}"
        email = f"test.user.{int(time.time()*1000)}@example.com"
        db.users.insert_one({
            "_id": user_id, "email": email, "name": "Test Sanjay Partner",
            "role": "user", "status": "approved", "partner_name": "Sanjay",
            "created_at": "2026-01-01T00:00:00+00:00",
        })
        db.user_sessions.insert_one({
            "user_id": str(user_id), "session_token": session_token,
            "expires_at": "2030-01-01T00:00:00+00:00", "created_at": "2026-01-01T00:00:00+00:00",
        })
        yield session_token
        # cleanup
        db.users.delete_one({"_id": user_id})
        db.user_sessions.delete_one({"session_token": session_token})
        client.close()

    def test_self_scope(self, linked_partner_session):
        r = requests.get(f"{BASE_URL}/api/partner/overview",
                         headers={"Authorization": f"Bearer {linked_partner_session}"}, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scope"] == "self"
        assert d["me"] == "Sanjay"
        assert "projects" in d and "personal" in d and "position" in d
        # No 'profiles' key (that's admin only)
        assert "profiles" not in d

    def test_admin_link_partner_endpoint(self, s):
        # Confirm endpoint exists — link a nonexistent user should 404
        r = s.post(f"{BASE_URL}/api/admin/users/{ObjectId()}/partner",
                   json={"partner_name": "Sanjay"}, timeout=10)
        assert r.status_code == 404


# -------- Regression --------

class TestRegression:
    def test_dashboard_loads(self, s):
        r = s.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert r.status_code == 200
        assert r.json()["rates"]["base"] == "AUD"

    def test_shares_unlock(self, s):
        r = s.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "2468"}, timeout=10)
        assert r.status_code == 200

    def test_shares_unlock_wrong(self, s):
        r = s.post(f"{BASE_URL}/api/shares/unlock", json={"pin": "0000"}, timeout=10)
        assert r.status_code == 403

    def test_admin_users_list(self, s):
        r = s.get(f"{BASE_URL}/api/admin/users", timeout=10)
        assert r.status_code == 200
        assert any(u["email"] == EMAIL for u in r.json())
