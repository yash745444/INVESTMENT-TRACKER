"""Backend API tests for Yash Wealth Command Center."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://investment-tracker-66.preview.emergentagent.com").rstrip("/")
EMAIL = "yash.sojitra34@gmail.com"
PASSWORD = "Yash@2026"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ---------------- auth ----------------

class TestAuth:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_login_wrong_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": EMAIL, "password": "wrongpass"}, timeout=10)
        assert r.status_code in (401, 429)

    def test_login_success_sets_cookie(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == EMAIL
        assert "id" in data
        # cookie should be set
        assert "access_token" in s.cookies.get_dict() or any(c.name == "access_token" for c in s.cookies)

    def test_me_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 401

    def test_me_authed(self, session):
        r = session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == EMAIL


# ---------------- rates ----------------

class TestRates:
    def test_rates(self, session):
        r = session.get(f"{BASE_URL}/api/rates", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["base"] == "AUD"
        assert set(["AUD", "USD", "INR"]).issubset(d["rates"].keys())
        assert d["rates"]["AUD"] == 1.0
        assert d["rates"]["USD"] > 0
        assert d["rates"]["INR"] > 0


# ---------------- projects, contributions, costs, loans ----------------

@pytest.fixture(scope="session")
def project_id(session):
    payload = {
        "name": "TEST_32-34_Cadman",
        "address": "32-34 Cadman",
        "description": "test project",
        "status": "active",
        "partners": [
            {"name": "Yash", "percentage": 25},
            {"name": "Sanjay", "percentage": 25},
            {"name": "Pranay", "percentage": 25},
            {"name": "Max", "percentage": 25},
        ],
    }
    r = session.post(f"{BASE_URL}/api/projects", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    session.delete(f"{BASE_URL}/api/projects/{pid}", timeout=10)


class TestProjects:
    def test_percentage_validation(self, session):
        bad = {"name": "TEST_bad", "partners": [{"name": "Yash", "percentage": 60},
                                                {"name": "Sanjay", "percentage": 30}]}
        r = session.post(f"{BASE_URL}/api/projects", json=bad, timeout=10)
        assert r.status_code == 400

    def test_project_created(self, session, project_id):
        r = session.get(f"{BASE_URL}/api/projects/{project_id}", timeout=10)
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_32-34_Cadman"

    def test_list_projects(self, session, project_id):
        r = session.get(f"{BASE_URL}/api/projects", timeout=10)
        assert r.status_code == 200
        assert any(p["id"] == project_id for p in r.json())

    def test_add_contribution(self, session, project_id):
        r = session.post(f"{BASE_URL}/api/projects/{project_id}/contributions",
                         json={"date": "2026-01-05", "partner": "Yash", "amount": 10000, "description": "seed"},
                         timeout=10)
        assert r.status_code == 200
        r2 = session.get(f"{BASE_URL}/api/projects/{project_id}/contributions", timeout=10)
        assert r2.status_code == 200
        assert any(c["amount"] == 10000 for c in r2.json())

    def test_add_cost(self, session, project_id):
        r = session.post(f"{BASE_URL}/api/projects/{project_id}/costs",
                         json={"date": "2026-01-06", "category": "Construction",
                               "description": "concrete", "amount": 5000, "paid_by": "Yash"}, timeout=10)
        assert r.status_code == 200
        r2 = session.get(f"{BASE_URL}/api/projects/{project_id}/costs", timeout=10)
        assert r2.status_code == 200
        assert any(c["amount"] == 5000 for c in r2.json())


class TestLoans:
    def test_interest_only_loan_and_drawdown(self, session, project_id):
        payload = {
            "name": "TEST_IO_Loan", "lender": "Bank", "type": "interest_only",
            "annual_rate": 6.0, "term_months": 24, "start_date": "2026-01-01",
            "drawdowns": [{"date": "2026-01-01", "amount": 100000, "description": "d1"}],
        }
        r = session.post(f"{BASE_URL}/api/projects/{project_id}/loans", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        loan = r.json()
        lid = loan["id"]
        # monthly = 100000 * 0.06/12 = 500
        assert abs(loan["metrics"]["monthly_payment"] - 500.0) < 1

        # Add another drawdown => 150000 outstanding, monthly = 750
        r2 = session.post(f"{BASE_URL}/api/loans/{lid}/drawdowns",
                          json={"date": "2026-01-15", "amount": 50000, "description": "d2"}, timeout=10)
        assert r2.status_code == 200
        assert abs(r2.json()["metrics"]["monthly_payment"] - 750.0) < 1

        # Schedule
        r3 = session.get(f"{BASE_URL}/api/loans/{lid}/schedule?months=12", timeout=10)
        assert r3.status_code == 200
        s = r3.json()
        assert len(s["schedule"]) == 12
        assert s["schedule"][0]["principal"] == 0  # interest-only
        assert s["schedule"][0]["interest"] > 0

        session.delete(f"{BASE_URL}/api/loans/{lid}", timeout=10)

    def test_amortizing_loan(self, session, project_id):
        payload = {
            "name": "TEST_AM_Loan", "type": "amortizing",
            "annual_rate": 6.0, "term_months": 60, "start_date": "2026-01-01",
            "drawdowns": [{"date": "2026-01-01", "amount": 100000, "description": ""}],
        }
        r = session.post(f"{BASE_URL}/api/projects/{project_id}/loans", json=payload, timeout=10)
        assert r.status_code == 200
        loan = r.json()
        assert loan["metrics"]["monthly_payment"] > 0
        lid = loan["id"]
        r3 = session.get(f"{BASE_URL}/api/loans/{lid}/schedule?months=6", timeout=10)
        assert r3.status_code == 200
        rows = r3.json()["schedule"]
        assert rows[0]["principal"] > 0 and rows[0]["interest"] > 0
        session.delete(f"{BASE_URL}/api/loans/{lid}", timeout=10)

    def test_invalid_loan_type(self, session, project_id):
        r = session.post(f"{BASE_URL}/api/projects/{project_id}/loans",
                         json={"name": "x", "type": "bad", "annual_rate": 5,
                               "term_months": 12, "start_date": "2026-01-01"}, timeout=10)
        assert r.status_code == 400


# ---------------- ledger ----------------

class TestLedger:
    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, session):
        # Wipe TEST_ ledger before running
        r = session.get(f"{BASE_URL}/api/ledger", timeout=10)
        if r.status_code == 200:
            for t in r.json():
                if (t.get("note") or "").startswith("TEST_"):
                    session.delete(f"{BASE_URL}/api/ledger/{t['id']}", timeout=10)
        yield
        r = session.get(f"{BASE_URL}/api/ledger", timeout=10)
        if r.status_code == 200:
            for t in r.json():
                if (t.get("note") or "").startswith("TEST_"):
                    session.delete(f"{BASE_URL}/api/ledger/{t['id']}", timeout=10)

    def test_pairwise_and_settlement(self, session):
        r = session.post(f"{BASE_URL}/api/ledger", json={
            "date": "2026-01-05", "type": "paid_on_behalf",
            "from_partner": "Yash", "to_partner": "Sanjay",
            "amount": 5000, "note": "TEST_paid"
        }, timeout=10)
        assert r.status_code == 200

        r2 = session.get(f"{BASE_URL}/api/ledger/balances", timeout=10)
        assert r2.status_code == 200
        pairs = r2.json()["pairs"]
        yash_sanjay = next(p for p in pairs if {p["a"], p["b"]} == {"Yash", "Sanjay"})
        assert yash_sanjay["amount"] == 5000.0
        assert "Sanjay owes Yash" in yash_sanjay["owes"]

        # settlement Sanjay -> Yash $2000
        r3 = session.post(f"{BASE_URL}/api/ledger", json={
            "date": "2026-01-06", "type": "settlement",
            "from_partner": "Sanjay", "to_partner": "Yash",
            "amount": 2000, "note": "TEST_settle"
        }, timeout=10)
        assert r3.status_code == 200

        r4 = session.get(f"{BASE_URL}/api/ledger/balances", timeout=10)
        pairs = r4.json()["pairs"]
        yash_sanjay = next(p for p in pairs if {p["a"], p["b"]} == {"Yash", "Sanjay"})
        assert abs(yash_sanjay["amount"] - 3000.0) < 0.01
        assert "Sanjay owes Yash" in yash_sanjay["owes"]

        totals = r4.json()["totals"]
        assert abs(totals["Yash"] - 3000.0) < 0.01
        assert abs(totals["Sanjay"] + 3000.0) < 0.01

    def test_same_partner_rejected(self, session):
        r = session.post(f"{BASE_URL}/api/ledger", json={
            "date": "2026-01-05", "type": "paid_on_behalf",
            "from_partner": "Yash", "to_partner": "Yash",
            "amount": 100, "note": "TEST_x"
        }, timeout=10)
        assert r.status_code == 400

    def test_report(self, session):
        r = session.get(f"{BASE_URL}/api/ledger/report", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "transactions" in d and "balances" in d and "partners" in d


# ---------------- investments ----------------

class TestInvestments:
    def test_investment_crud_and_dashboard(self, session):
        r = session.post(f"{BASE_URL}/api/investments", json={
            "type": "shares", "name": "TEST_USDShares", "currency": "USD",
            "amount": 10000, "date": "2026-01-01", "notes": ""
        }, timeout=10)
        assert r.status_code == 200
        iid = r.json()["id"]

        r2 = session.post(f"{BASE_URL}/api/investments", json={
            "type": "term_insurance", "name": "TEST_INRTI", "currency": "INR",
            "amount": 500000
        }, timeout=10)
        assert r2.status_code == 200
        iid2 = r2.json()["id"]

        # Dashboard reflects investments in AUD (>0)
        d = session.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert d.status_code == 200
        data = d.json()
        assert data["investments"]["total"] > 0
        # USD 10000 in AUD should be > 10000 (since USD stronger than AUD normally)
        # not strict — just sanity check
        session.delete(f"{BASE_URL}/api/investments/{iid}", timeout=10)
        session.delete(f"{BASE_URL}/api/investments/{iid2}", timeout=10)


# ---------------- properties ----------------

class TestProperties:
    def test_property_equity(self, session):
        r = session.post(f"{BASE_URL}/api/properties", json={
            "name": "TEST_Home", "address": "1 St", "purchase_date": "2020-01-01",
            "purchase_price": 800000, "current_value": 1000000, "monthly_rent": 3000,
            "debt": 400000, "currency": "AUD"
        }, timeout=10)
        assert r.status_code == 200
        pid = r.json()["id"]

        d = session.get(f"{BASE_URL}/api/dashboard", timeout=15)
        data = d.json()
        assert data["properties"]["value"] >= 1000000
        assert data["properties"]["equity"] >= 600000
        session.delete(f"{BASE_URL}/api/properties/{pid}", timeout=10)


# ---------------- dashboard ----------------

class TestDashboard:
    def test_dashboard_shape(self, session):
        r = session.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("net_worth", "investments", "properties", "projects", "ledger_net", "rates"):
            assert k in d
