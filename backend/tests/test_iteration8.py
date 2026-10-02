"""Iteration 8 — edit endpoints for projects/costs/loans/drawdowns/ledger/personal-loans/feasibility.

Scope:
    * PUT /api/projects/{pid}            — must not wipe final_profit (frontend sends it back)
    * PUT /api/costs/{cid}               — updates and persists
    * PUT /api/loans/{lid}               — recalculates metrics, drawdowns preserved
    * PUT+DELETE /api/loans/{lid}/drawdowns/{idx}
    * PUT /api/ledger/{tid}
    * PUT /api/personal-loans/{lid}
    * PUT /api/feasibility/{fid}         — computed recalculates
"""
import os
import pytest
import requests
from datetime import datetime, date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "yash.sojitra34@gmail.com"
ADMIN_PASSWORD = "Yash@2026"
TODAY = date.today().isoformat()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def test_project(admin_session):
    """Create an isolated test project with a known final_profit, cleanup after module."""
    payload = {
        "name": f"TEST_ITER8_PROJ_{int(datetime.now().timestamp())}",
        "address": "Test st",
        "description": "iter8 edit test",
        "status": "active",
        "partners": [
            {"name": "Yash Sojitra", "percentage": 60, "email": ADMIN_EMAIL},
            {"name": "Partner B", "percentage": 40, "email": ""},
        ],
    }
    r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    # set final_profit = 500000
    pr = admin_session.post(f"{BASE_URL}/api/projects/{pid}/profit", json={"final_profit": 500000})
    assert pr.status_code == 200
    yield pid
    admin_session.delete(f"{BASE_URL}/api/projects/{pid}")


# ---------------- PROJECT EDIT ----------------
class TestProjectEdit:
    def test_edit_project_preserves_final_profit(self, admin_session, test_project):
        pid = test_project
        # Simulate what the frontend sends — includes final_profit from state
        payload = {
            "name": f"TEST_ITER8_PROJ_RENAMED_{int(datetime.now().timestamp())}",
            "address": "Test st",
            "description": "renamed",
            "status": "active",
            "partners": [
                {"name": "Yash Sojitra", "percentage": 70, "email": ADMIN_EMAIL},
                {"name": "Partner B", "percentage": 30, "email": ""},
            ],
            "final_profit": 500000,
        }
        r = admin_session.put(f"{BASE_URL}/api/projects/{pid}", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"].startswith("TEST_ITER8_PROJ_RENAMED_")
        assert body["final_profit"] == 500000
        # verify partner pct changes
        pcts = {p["name"]: p["percentage"] for p in body["partners"]}
        assert pcts["Yash Sojitra"] == 70
        assert pcts["Partner B"] == 30

        # GET to verify persistence
        g = admin_session.get(f"{BASE_URL}/api/projects/{pid}")
        assert g.status_code == 200
        assert g.json()["final_profit"] == 500000

    def test_edit_project_rejects_bad_percentages(self, admin_session, test_project):
        pid = test_project
        payload = {
            "name": "x",
            "status": "active",
            "partners": [
                {"name": "A", "percentage": 60, "email": ""},
                {"name": "B", "percentage": 30, "email": ""},
            ],
            "final_profit": 500000,
        }
        r = admin_session.put(f"{BASE_URL}/api/projects/{pid}", json=payload)
        assert r.status_code == 400


# ---------------- COST EDIT ----------------
class TestCostEdit:
    def test_create_edit_delete_cost(self, admin_session, test_project):
        pid = test_project
        # create
        r = admin_session.post(f"{BASE_URL}/api/projects/{pid}/costs", json={
            "date": TODAY, "category": "Site Works", "description": "TEST_cost",
            "amount": 1000, "paid_by": "Owner"})
        assert r.status_code == 200
        cid = r.json()["id"]
        # edit
        r2 = admin_session.put(f"{BASE_URL}/api/costs/{cid}", json={
            "date": TODAY, "category": "Permits", "description": "TEST_cost_edited",
            "amount": 2500, "paid_by": "Partner"})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["amount"] == 2500
        assert body["category"] == "Permits"
        assert body["description"] == "TEST_cost_edited"
        # GET
        gr = admin_session.get(f"{BASE_URL}/api/projects/{pid}/costs")
        found = [c for c in gr.json() if c["id"] == cid][0]
        assert found["amount"] == 2500
        # cleanup
        admin_session.delete(f"{BASE_URL}/api/costs/{cid}")


# ---------------- LOAN EDIT ----------------
class TestLoanEdit:
    @pytest.fixture
    def loan_id(self, admin_session, test_project):
        pid = test_project
        payload = {
            "name": "TEST_LOAN", "lender": "Bank X", "type": "interest_only",
            "annual_rate": 6, "term_months": 24, "start_date": TODAY,
            "drawdowns": [{"date": TODAY, "amount": 100000, "description": "d1"}],
        }
        r = admin_session.post(f"{BASE_URL}/api/projects/{pid}/loans", json=payload)
        assert r.status_code == 200, r.text
        lid = r.json()["id"]
        yield lid
        admin_session.delete(f"{BASE_URL}/api/loans/{lid}")

    def test_edit_loan_rate_recalculates_and_preserves_drawdowns(self, admin_session, loan_id):
        lid = loan_id
        # edit rate 6 -> 12
        r = admin_session.put(f"{BASE_URL}/api/loans/{lid}", json={
            "name": "TEST_LOAN", "lender": "Bank X", "type": "interest_only",
            "annual_rate": 12, "term_months": 24, "start_date": TODAY,
            "drawdowns": [],  # even sending [] should NOT wipe
        })
        assert r.status_code == 200, r.text
        body = r.json()
        # drawdowns preserved
        assert len(body.get("drawdowns", [])) == 1
        assert body["drawdowns"][0]["amount"] == 100000
        # monthly = 100000 * 12/100 / 12 = 1000
        assert abs(body["metrics"]["monthly_payment"] - 1000) < 0.5
        assert abs(body["metrics"]["drawn"] - 100000) < 0.5

    def test_edit_drawdown_and_delete(self, admin_session, loan_id):
        lid = loan_id
        # update drawdown idx 0: 100000 -> 200000
        r = admin_session.put(f"{BASE_URL}/api/loans/{lid}/drawdowns/0", json={
            "date": TODAY, "amount": 200000, "description": "edited"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["drawdowns"][0]["amount"] == 200000
        # metrics recalc: at 6% rate (fixture default) monthly = 200000 * 0.06/12 = 1000
        assert abs(body["metrics"]["monthly_payment"] - 1000) < 1.0
        assert abs(body["metrics"]["drawn"] - 200000) < 0.5

        # delete drawdown
        dr = admin_session.delete(f"{BASE_URL}/api/loans/{lid}/drawdowns/0")
        assert dr.status_code == 200
        # verify
        gr = admin_session.get(f"{BASE_URL}/api/projects/{admin_session.get(f'{BASE_URL}/api/projects').json()[0]['id'] if False else ''}/loans")
        # simpler verify via list_loans by scanning
        # Instead fetch the loan via projects/{pid}/loans
        # we need pid though - look up via loan? we can just POST a new drawdown and check length
        # Just verify via adding then schedule
        sch = admin_session.get(f"{BASE_URL}/api/loans/{lid}/schedule?months=1")
        assert sch.status_code == 200
        assert sch.json()["metrics"]["drawn"] == 0

    def test_update_drawdown_bad_index(self, admin_session, loan_id):
        r = admin_session.put(f"{BASE_URL}/api/loans/{loan_id}/drawdowns/99", json={
            "date": TODAY, "amount": 1, "description": ""})
        assert r.status_code == 404


# ---------------- LEDGER EDIT ----------------
class TestLedgerEdit:
    def test_edit_ledger_transaction(self, admin_session):
        # create
        r = admin_session.post(f"{BASE_URL}/api/ledger", json={
            "date": TODAY, "type": "paid_on_behalf",
            "from_partner": "Yash Sojitra", "to_partner": "Partner B",
            "amount": 100, "note": "TEST_txn"})
        assert r.status_code == 200
        tid = r.json()["id"]
        # edit
        r2 = admin_session.put(f"{BASE_URL}/api/ledger/{tid}", json={
            "date": TODAY, "type": "paid_on_behalf",
            "from_partner": "Yash Sojitra", "to_partner": "Partner B",
            "amount": 777, "note": "TEST_txn_edited"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["amount"] == 777
        assert r2.json()["note"] == "TEST_txn_edited"
        # cleanup
        admin_session.delete(f"{BASE_URL}/api/ledger/{tid}")

    def test_edit_ledger_rejects_same_partner(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/ledger", json={
            "date": TODAY, "type": "settlement",
            "from_partner": "X", "to_partner": "Y",
            "amount": 10, "note": "TEST_bad"})
        tid = r.json()["id"]
        r2 = admin_session.put(f"{BASE_URL}/api/ledger/{tid}", json={
            "date": TODAY, "type": "settlement",
            "from_partner": "X", "to_partner": "X",
            "amount": 10, "note": ""})
        assert r2.status_code == 400
        admin_session.delete(f"{BASE_URL}/api/ledger/{tid}")


# ---------------- PERSONAL LOAN EDIT ----------------
class TestPersonalLoanEdit:
    def test_edit_interest_personal_loan_updates_accrual(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/personal-loans", json={
            "lender": "TEST_PL_lender", "amount": 10000,
            "date": "2024-01-01", "type": "interest",
            "annual_rate": 5, "notes": ""})
        assert r.status_code == 200
        lid = r.json()["id"]
        orig_accrued = r.json()["computed"]["accrued_interest"]
        # edit amount to 50000 and rate to 10
        r2 = admin_session.put(f"{BASE_URL}/api/personal-loans/{lid}", json={
            "lender": "TEST_PL_lender", "amount": 50000,
            "date": "2024-01-01", "type": "interest",
            "annual_rate": 10, "notes": "edited"})
        assert r2.status_code == 200, r2.text
        new = r2.json()
        assert new["amount"] == 50000
        assert new["annual_rate"] == 10
        assert new["computed"]["accrued_interest"] > orig_accrued
        admin_session.delete(f"{BASE_URL}/api/personal-loans/{lid}")

    def test_edit_profit_share_personal_loan(self, admin_session, test_project):
        pid = test_project
        r = admin_session.post(f"{BASE_URL}/api/personal-loans", json={
            "lender": "TEST_PL_ps", "amount": 10000,
            "date": TODAY, "type": "profit_share",
            "project_id": pid, "basis_amount": 50000, "notes": ""})
        assert r.status_code == 200, r.text
        lid = r.json()["id"]
        # project has final_profit=500000, share = 10000/50000 = 0.2 => return = 100000
        assert abs(r.json()["computed"]["return_amount"] - 100000) < 1
        # edit basis_amount to 100000 => share 0.1 => return 50000
        r2 = admin_session.put(f"{BASE_URL}/api/personal-loans/{lid}", json={
            "lender": "TEST_PL_ps", "amount": 10000,
            "date": TODAY, "type": "profit_share",
            "project_id": pid, "basis_amount": 100000, "notes": ""})
        assert r2.status_code == 200, r2.text
        assert abs(r2.json()["computed"]["return_amount"] - 50000) < 1
        admin_session.delete(f"{BASE_URL}/api/personal-loans/{lid}")


# ---------------- FEASIBILITY EDIT ----------------
class TestFeasibilityEdit:
    def test_edit_feasibility_recomputes(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/feasibility", json={
            "name": "TEST_FS", "project_type": "single_dwelling",
            "land_cost": 100000, "construction_cost": 200000,
            "contingency_pct": 10, "expected_revenue": 500000,
            "loan_amount": 0})
        assert r.status_code == 200
        fid = r.json()["id"]
        orig_total = r.json()["computed"]["total_cost"]
        # edit land_cost up by 50000
        r2 = admin_session.put(f"{BASE_URL}/api/feasibility/{fid}", json={
            "name": "TEST_FS_edited", "project_type": "single_dwelling",
            "land_cost": 150000, "construction_cost": 200000,
            "contingency_pct": 10, "expected_revenue": 500000,
            "loan_amount": 0})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["name"] == "TEST_FS_edited"
        assert abs(body["computed"]["total_cost"] - (orig_total + 50000)) < 1
        assert "feasible" in body["computed"]
        admin_session.delete(f"{BASE_URL}/api/feasibility/{fid}")


# ---------------- NOT-FOUND / AUTH ----------------
class TestEditNotFound:
    def test_update_cost_not_found(self, admin_session):
        # non-existent valid-looking ObjectId
        r = admin_session.put(f"{BASE_URL}/api/costs/000000000000000000000000", json={
            "date": TODAY, "category": "x", "description": "", "amount": 1, "paid_by": ""})
        assert r.status_code in (403, 404)

    def test_update_loan_drawdown_oob(self, admin_session):
        r = admin_session.put(f"{BASE_URL}/api/loans/000000000000000000000000/drawdowns/0", json={
            "date": TODAY, "amount": 1, "description": ""})
        assert r.status_code in (403, 404)
