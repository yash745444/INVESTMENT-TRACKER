"""Iteration 9 — Company split contributions + Project current_value field.

Scope:
    * POST /api/projects/{pid}/contributions/split — owner-only, 400 if no partners,
      exact rounding (33.33/33.33/33.34 of 100000 => 33330/33330/33340)
    * Project current_value round-trips through POST /api/projects, PUT /api/projects/{pid},
      GET /api/projects, GET /api/projects/{pid}
    * PUT /api/projects/{pid} with current_value does not wipe final_profit or partners
    * Regression: non-owner (unauthenticated) blocked from split
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
def three_way_project(admin_session):
    """Project with 33.33/33.33/33.34 split for exact-sum rounding test."""
    payload = {
        "name": f"TEST_ITER9_SPLIT_{int(datetime.now().timestamp())}",
        "address": "n/a", "description": "", "status": "active",
        "current_value": 1234567.89,
        "partners": [
            {"name": "A", "percentage": 33.33, "email": ""},
            {"name": "B", "percentage": 33.33, "email": ""},
            {"name": "C", "percentage": 33.34, "email": ""},
        ],
    }
    r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    admin_session.delete(f"{BASE_URL}/api/projects/{pid}")


@pytest.fixture(scope="module")
def empty_partner_project(admin_session):
    payload = {
        "name": f"TEST_ITER9_NOPARTNERS_{int(datetime.now().timestamp())}",
        "status": "active", "partners": [],
    }
    r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    admin_session.delete(f"{BASE_URL}/api/projects/{pid}")


# ---------- COMPANY SPLIT ----------
class TestCompanySplit:
    def test_split_exact_rounding(self, admin_session, three_way_project):
        pid = three_way_project
        r = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions/split", json={
            "date": TODAY, "amount": 100000, "description": "TEST_split"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["inserted"] == 3
        assert abs(body["total"] - 100000) < 0.01

        # Verify individual contribution rows
        gr = admin_session.get(f"{BASE_URL}/api/projects/{pid}/contributions")
        assert gr.status_code == 200
        rows = [c for c in gr.json() if "TEST_split" in (c.get("description") or "")]
        amounts = sorted([c["amount"] for c in rows])
        assert amounts == [33330.0, 33330.0, 33340.0], f"Got {amounts}"
        # exact sum preserved
        assert abs(sum(amounts) - 100000) < 0.01
        # description tagged
        assert all("(company split" in r["description"] for r in rows)
        # cleanup rows
        for row in rows:
            admin_session.delete(f"{BASE_URL}/api/contributions/{row['id']}")

    def test_split_rejects_no_partners(self, admin_session, empty_partner_project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{empty_partner_project}/contributions/split",
                               json={"date": TODAY, "amount": 1000, "description": "x"})
        assert r.status_code == 400

    def test_split_requires_auth(self, three_way_project):
        anon = requests.Session()
        r = anon.post(f"{BASE_URL}/api/projects/{three_way_project}/contributions/split",
                      json={"date": TODAY, "amount": 1000, "description": "x"})
        assert r.status_code in (401, 403)


# ---------- CURRENT VALUE ----------
class TestProjectCurrentValue:
    def test_current_value_in_list_and_detail(self, admin_session, three_way_project):
        pid = three_way_project
        # GET list
        rl = admin_session.get(f"{BASE_URL}/api/projects")
        assert rl.status_code == 200
        proj = next((p for p in rl.json() if p["id"] == pid), None)
        assert proj is not None
        assert abs(proj.get("current_value", 0) - 1234567.89) < 0.01
        # GET single
        rs = admin_session.get(f"{BASE_URL}/api/projects/{pid}")
        assert rs.status_code == 200
        assert abs(rs.json().get("current_value", 0) - 1234567.89) < 0.01

    def test_edit_current_value_preserves_final_profit_and_partners(self, admin_session, three_way_project):
        pid = three_way_project
        # set final_profit
        pr = admin_session.post(f"{BASE_URL}/api/projects/{pid}/profit", json={"final_profit": 777000})
        assert pr.status_code == 200
        # PUT updates current_value but keeps partners & final_profit
        payload = {
            "name": "TEST_ITER9_SPLIT_RENAMED",
            "status": "active",
            "current_value": 2500000,
            "final_profit": 777000,
            "partners": [
                {"name": "A", "percentage": 33.33, "email": ""},
                {"name": "B", "percentage": 33.33, "email": ""},
                {"name": "C", "percentage": 33.34, "email": ""},
            ],
        }
        r = admin_session.put(f"{BASE_URL}/api/projects/{pid}", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert abs(body["current_value"] - 2500000) < 0.01
        assert body["final_profit"] == 777000
        pcts = sorted(p["percentage"] for p in body["partners"])
        assert pcts == [33.33, 33.33, 33.34]
        # GET verifies persistence
        g = admin_session.get(f"{BASE_URL}/api/projects/{pid}").json()
        assert abs(g["current_value"] - 2500000) < 0.01
        assert g["final_profit"] == 777000
