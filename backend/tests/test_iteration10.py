"""Iteration 10 — Contribution Batches (capital calls).

Covers:
  * POST /api/projects/{pid}/batches (owner-only, 400 for target<=0)
  * GET  /api/projects/{pid}/batches (progress math: expected = target*pct/100,
     remaining = expected - paid, fully_paid flag)
  * POST /api/batches/{bid}/close + /reopen
  * DELETE /api/batches/{bid} guard (400 when linked)
  * ContributionIn + SplitContributionIn accept batch_id (invalid -> 400)
  * Project deletion cascades contribution_batches
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
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture
def project(admin_session):
    payload = {
        "name": f"TEST_ITER10_BATCH_{int(datetime.now().timestamp()*1000)}",
        "address": "n/a", "status": "active",
        "partners": [
            {"name": "P1", "percentage": 50, "email": ""},
            {"name": "P2", "percentage": 50, "email": ""},
        ],
    }
    r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    admin_session.delete(f"{BASE_URL}/api/projects/{pid}")


class TestBatchCRUD:
    def test_create_batch_sets_open_status_and_progress(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches", json={
            "name": "Batch 1", "target_amount": 100000, "note": "first"
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["name"] == "Batch 1"
        assert b["target_amount"] == 100000
        assert b["status"] == "open"
        assert "progress" in b
        # per-partner expected = 50% * 100k = 50000, paid=0
        parts = b["progress"]["partners"]
        assert len(parts) == 2
        for p in parts:
            assert abs(p["expected"] - 50000) < 0.01
            assert p["paid"] == 0
            assert abs(p["remaining"] - 50000) < 0.01

    def test_create_batch_rejects_zero_target(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches", json={
            "name": "bad", "target_amount": 0
        })
        assert r.status_code == 400

    def test_create_batch_rejects_negative_target(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches", json={
            "name": "bad", "target_amount": -5
        })
        assert r.status_code == 400

    def test_list_batches_sorted_oldest_first(self, admin_session, project):
        for i in range(3):
            r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches",
                                   json={"name": f"B{i}", "target_amount": 1000})
            assert r.status_code == 200
        rl = admin_session.get(f"{BASE_URL}/api/projects/{project}/batches")
        assert rl.status_code == 200
        names = [b["name"] for b in rl.json()]
        assert names == ["B0", "B1", "B2"]

    def test_non_owner_cannot_create_batch(self, project):
        anon = requests.Session()
        r = anon.post(f"{BASE_URL}/api/projects/{project}/batches",
                      json={"name": "x", "target_amount": 1000})
        assert r.status_code in (401, 403)


class TestBatchProgressMath:
    def test_partial_then_full_payment_flips_flags(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches",
                               json={"name": "B", "target_amount": 100000})
        bid = r.json()["id"]
        # P1 pays 25k (half of expected 50k) -> partial
        c1 = admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions", json={
            "partner": "P1", "amount": 25000, "date": TODAY,
            "description": "TEST half", "batch_id": bid})
        assert c1.status_code == 200, c1.text
        # fetch
        prog = admin_session.get(f"{BASE_URL}/api/projects/{project}/batches").json()
        b = next(x for x in prog if x["id"] == bid)
        p1 = next(p for p in b["progress"]["partners"] if p["name"] == "P1")
        assert abs(p1["paid"] - 25000) < 0.01
        assert abs(p1["remaining"] - 25000) < 0.01
        assert p1["fully_paid"] is False if "fully_paid" in p1 else (p1["remaining"] > 0)
        assert b["progress"]["fully_paid"] is False
        # P1 tops up another 25k -> fully_paid
        admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions", json={
            "partner": "P1", "amount": 25000, "date": TODAY,
            "description": "TEST top", "batch_id": bid})
        # P2 pays 50k -> whole batch fully_paid
        admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions", json={
            "partner": "P2", "amount": 50000, "date": TODAY,
            "description": "TEST p2", "batch_id": bid})
        prog2 = admin_session.get(f"{BASE_URL}/api/projects/{project}/batches").json()
        b2 = next(x for x in prog2 if x["id"] == bid)
        assert b2["progress"]["fully_paid"] is True
        assert abs(b2["progress"]["paid_total"] - 100000) < 0.01
        for p in b2["progress"]["partners"]:
            assert abs(p["remaining"]) < 0.01

    def test_invalid_batch_id_rejected_on_contribution(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions", json={
            "partner": "P1", "amount": 100, "date": TODAY,
            "description": "x", "batch_id": "507f1f77bcf86cd799439011"})
        assert r.status_code == 400

    def test_split_links_to_batch(self, admin_session, project):
        br = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches",
                                json={"name": "SplitBatch", "target_amount": 100000})
        bid = br.json()["id"]
        sr = admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions/split",
                                json={"date": TODAY, "amount": 100000,
                                      "description": "TEST_split10", "batch_id": bid})
        assert sr.status_code == 200, sr.text
        prog = admin_session.get(f"{BASE_URL}/api/projects/{project}/batches").json()
        b = next(x for x in prog if x["id"] == bid)
        assert b["progress"]["fully_paid"] is True
        assert abs(b["progress"]["paid_total"] - 100000) < 0.01

    def test_invalid_batch_id_rejected_on_split(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions/split",
                               json={"date": TODAY, "amount": 1000,
                                     "description": "x",
                                     "batch_id": "507f1f77bcf86cd799439011"})
        assert r.status_code == 400


class TestBatchLifecycle:
    def test_close_and_reopen(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches",
                               json={"name": "LC", "target_amount": 100})
        bid = r.json()["id"]
        c = admin_session.post(f"{BASE_URL}/api/batches/{bid}/close")
        assert c.status_code == 200
        assert c.json()["status"] == "closed"
        o = admin_session.post(f"{BASE_URL}/api/batches/{bid}/reopen")
        assert o.status_code == 200
        assert o.json()["status"] == "open"

    def test_delete_guard_when_linked(self, admin_session, project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches",
                               json={"name": "DG", "target_amount": 1000})
        bid = r.json()["id"]
        cr = admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions", json={
            "partner": "P1", "amount": 100, "date": TODAY,
            "description": "link", "batch_id": bid})
        assert cr.status_code == 200
        cid = cr.json()["id"]
        dr = admin_session.delete(f"{BASE_URL}/api/batches/{bid}")
        assert dr.status_code == 400
        assert "linked" in dr.text.lower()
        # unlink by deleting contribution
        admin_session.delete(f"{BASE_URL}/api/contributions/{cid}")
        dr2 = admin_session.delete(f"{BASE_URL}/api/batches/{bid}")
        assert dr2.status_code == 200

    def test_project_delete_cascades_batches(self, admin_session):
        payload = {
            "name": f"TEST_ITER10_CASCADE_{int(datetime.now().timestamp()*1000)}",
            "status": "active",
            "partners": [{"name": "X", "percentage": 100, "email": ""}],
        }
        pr = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
        pid = pr.json()["id"]
        br = admin_session.post(f"{BASE_URL}/api/projects/{pid}/batches",
                                json={"name": "C", "target_amount": 1000})
        assert br.status_code == 200
        bid = br.json()["id"]
        d = admin_session.delete(f"{BASE_URL}/api/projects/{pid}")
        assert d.status_code == 200
        # listing batches of a deleted project -> 404 on project
        lb = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        assert lb.status_code == 404
        # closing the orphaned batch should 404 too
        cb = admin_session.post(f"{BASE_URL}/api/batches/{bid}/close")
        assert cb.status_code == 404


class TestEditContributionBatchLink:
    def test_edit_assigns_and_unassigns_batch(self, admin_session, project):
        br = admin_session.post(f"{BASE_URL}/api/projects/{project}/batches",
                                json={"name": "EB", "target_amount": 100000})
        bid = br.json()["id"]
        # create contribution without batch
        cr = admin_session.post(f"{BASE_URL}/api/projects/{project}/contributions", json={
            "partner": "P1", "amount": 10000, "date": TODAY,
            "description": "edit-test"})
        assert cr.status_code == 200
        cid = cr.json()["id"]
        # link via PUT
        up = admin_session.put(f"{BASE_URL}/api/contributions/{cid}", json={
            "partner": "P1", "amount": 10000, "date": TODAY,
            "description": "edit-test", "batch_id": bid})
        assert up.status_code == 200, up.text
        prog = admin_session.get(f"{BASE_URL}/api/projects/{project}/batches").json()
        b = next(x for x in prog if x["id"] == bid)
        assert abs(b["progress"]["paid_total"] - 10000) < 0.01
        # invalid batch on PUT -> 400
        bad = admin_session.put(f"{BASE_URL}/api/contributions/{cid}", json={
            "partner": "P1", "amount": 10000, "date": TODAY,
            "description": "edit-test",
            "batch_id": "507f1f77bcf86cd799439011"})
        assert bad.status_code == 400
        # unlink via PUT (batch_id = null)
        un = admin_session.put(f"{BASE_URL}/api/contributions/{cid}", json={
            "partner": "P1", "amount": 10000, "date": TODAY,
            "description": "edit-test", "batch_id": None})
        assert un.status_code == 200
        prog2 = admin_session.get(f"{BASE_URL}/api/projects/{project}/batches").json()
        b2 = next(x for x in prog2 if x["id"] == bid)
        assert abs(b2["progress"]["paid_total"]) < 0.01
