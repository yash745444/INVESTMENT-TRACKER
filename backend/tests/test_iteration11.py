"""Iteration 11 — Record Payment per-partner + Settle-All batch endpoint.

Covers:
  * POST /api/batches/{bid}/settle-all — creates one contribution per unpaid partner
  * 400 when batch is already fully paid
  * 403 when non-owner (no auth)
  * MAISON 7 seeded state: 3 batches (Batch1 closed $670k, Batch2 closed $50k, Batch3 open $1.5M)
  * Record payment via POST /api/projects/{pid}/contributions linked to batch_id
  * Partial payment flips chip to PARTIAL; full to PAID
  * Edit/unlink contribution reduces batch paid; re-link restores
  * delete-batch guard still 400s on linked batches
"""
import os
import pytest
import requests
from datetime import datetime, date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "yash.sojitra34@gmail.com"
ADMIN_PASSWORD = "Yash@2026"
MAISON7_PID = "6abded14ba052cd1f3f8dd4c"
TODAY = date.today().isoformat()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture
def scratch_project(admin_session):
    payload = {
        "name": f"TEST_ITER11_{int(datetime.now().timestamp()*1000)}",
        "address": "scratch", "status": "active",
        "partners": [
            {"name": "Alice", "percentage": 60, "email": ""},
            {"name": "Bob", "percentage": 40, "email": ""},
        ],
    }
    r = admin_session.post(f"{BASE_URL}/api/projects", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    admin_session.delete(f"{BASE_URL}/api/projects/{pid}")


@pytest.fixture
def scratch_batch(admin_session, scratch_project):
    r = admin_session.post(f"{BASE_URL}/api/projects/{scratch_project}/batches", json={
        "name": "SB1", "target_amount": 100000, "note": ""
    })
    assert r.status_code == 200, r.text
    return scratch_project, r.json()["id"]


class TestMaison7SeededState:
    """Validate seed state on MAISON 7 — read-only."""

    def test_three_batches_exist(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/projects/{MAISON7_PID}/batches")
        assert r.status_code == 200, r.text
        batches = r.json()
        assert len(batches) >= 3, f"Expected >=3 batches, got {len(batches)}"
        by_name = {b["name"]: b for b in batches}
        # Allow any naming — but at least match the 3 seed totals
        totals = sorted([b["target_amount"] for b in batches])
        assert 670000 in totals
        assert 50000 in totals
        assert 1500000 in totals

    def test_closed_batches_fully_paid(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/projects/{MAISON7_PID}/batches")
        batches = r.json()
        for b in batches:
            if b["target_amount"] in (670000, 50000):
                assert b["status"] == "closed", f"{b['name']} not closed"
                assert b["progress"]["remaining_total"] <= 0.5, b["progress"]
                assert b["progress"]["fully_paid"] is True

    def test_open_15m_batch_zero_paid(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/projects/{MAISON7_PID}/batches")
        batches = r.json()
        b15 = next(b for b in batches if b["target_amount"] == 1500000)
        assert b15["status"] == "open"
        assert b15["progress"]["paid_total"] == 0
        assert b15["progress"]["remaining_total"] == 1500000

    def test_contributions_total_720k(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/projects/{MAISON7_PID}/contributions")
        assert r.status_code == 200
        rows = r.json()
        total = round(sum(c["amount"] for c in rows), 2)
        assert total == 720000, f"Expected $720,000 contributions total, got {total}"
        assert len(rows) >= 18, f"Expected >=18 contribution rows, got {len(rows)}"


class TestSettleAll:
    def test_settle_all_creates_one_contrib_per_unpaid_partner(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        r = admin_session.post(f"{BASE_URL}/api/batches/{bid}/settle-all",
                               json={"description": "SETTLE_TEST"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["inserted"] == 2
        assert body["total"] == 100000

        # Verify contributions created and linked to batch
        rc = admin_session.get(f"{BASE_URL}/api/projects/{pid}/contributions")
        rows = [c for c in rc.json() if c.get("batch_id") == bid]
        assert len(rows) == 2
        by_name = {c["partner"]: c for c in rows}
        assert by_name["Alice"]["amount"] == 60000
        assert by_name["Bob"]["amount"] == 40000

        # Batch should now be fully paid
        rb = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        b = next(x for x in rb.json() if x["id"] == bid)
        assert b["progress"]["fully_paid"] is True
        assert b["progress"]["remaining_total"] <= 0.5

    def test_settle_all_on_fully_paid_batch_400(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        # Fully settle first
        r1 = admin_session.post(f"{BASE_URL}/api/batches/{bid}/settle-all", json={})
        assert r1.status_code == 200
        # Second call must 400
        r2 = admin_session.post(f"{BASE_URL}/api/batches/{bid}/settle-all", json={})
        assert r2.status_code == 400
        assert "already fully paid" in r2.text.lower()

    def test_settle_all_after_partial_pays_only_remaining(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        # Alice pays $30k partial (expected 60k)
        rp = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
            "date": TODAY, "partner": "Alice", "amount": 30000,
            "description": "partial", "batch_id": bid
        })
        assert rp.status_code == 200
        # Settle all remaining: Alice $30k + Bob $40k = $70k
        rs = admin_session.post(f"{BASE_URL}/api/batches/{bid}/settle-all", json={})
        assert rs.status_code == 200
        body = rs.json()
        assert body["inserted"] == 2
        assert body["total"] == 70000

    def test_settle_all_requires_auth(self, scratch_batch):
        _, bid = scratch_batch
        r = requests.post(f"{BASE_URL}/api/batches/{bid}/settle-all", json={})
        assert r.status_code in (401, 403)

    def test_settle_all_invalid_batch_id_404_or_400(self, admin_session):
        # Valid ObjectId format but nonexistent
        r = admin_session.post(f"{BASE_URL}/api/batches/000000000000000000000000/settle-all", json={})
        assert r.status_code in (400, 404)


class TestRecordPaymentFlow:
    def test_partial_then_full_payment_flow(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        # Alice expected: 60% * 100k = 60k. Pay half = 30k
        r1 = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
            "date": TODAY, "partner": "Alice", "amount": 30000,
            "description": "half", "batch_id": bid
        })
        assert r1.status_code == 200
        rb = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        b = next(x for x in rb.json() if x["id"] == bid)
        alice = next(p for p in b["progress"]["partners"] if p["name"] == "Alice")
        assert alice["paid"] == 30000
        assert alice["remaining"] == 30000
        assert b["progress"]["fully_paid"] is False

        # Pay remainder 30k
        r2 = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
            "date": TODAY, "partner": "Alice", "amount": 30000,
            "description": "rest", "batch_id": bid
        })
        assert r2.status_code == 200
        rb2 = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        b2 = next(x for x in rb2.json() if x["id"] == bid)
        alice2 = next(p for p in b2["progress"]["partners"] if p["name"] == "Alice")
        assert alice2["paid"] == 60000
        assert alice2["remaining"] == 0

    def test_edit_unlink_contribution_reduces_batch_paid(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        r1 = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
            "date": TODAY, "partner": "Alice", "amount": 20000,
            "description": "link", "batch_id": bid
        })
        cid = r1.json()["id"]
        rb1 = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        paid1 = next(x for x in rb1.json() if x["id"] == bid)["progress"]["paid_total"]
        assert paid1 == 20000

        # Unlink (set batch_id null)
        ru = admin_session.put(f"{BASE_URL}/api/contributions/{cid}", json={
            "date": TODAY, "partner": "Alice", "amount": 20000,
            "description": "link", "batch_id": None
        })
        assert ru.status_code == 200
        rb2 = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        paid2 = next(x for x in rb2.json() if x["id"] == bid)["progress"]["paid_total"]
        assert paid2 == 0

        # Re-link
        rr = admin_session.put(f"{BASE_URL}/api/contributions/{cid}", json={
            "date": TODAY, "partner": "Alice", "amount": 20000,
            "description": "relink", "batch_id": bid
        })
        assert rr.status_code == 200
        rb3 = admin_session.get(f"{BASE_URL}/api/projects/{pid}/batches")
        paid3 = next(x for x in rb3.json() if x["id"] == bid)["progress"]["paid_total"]
        assert paid3 == 20000

    def test_delete_batch_guard_still_400s_when_linked(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        r1 = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions", json={
            "date": TODAY, "partner": "Alice", "amount": 5000,
            "description": "guard", "batch_id": bid
        })
        assert r1.status_code == 200
        rd = admin_session.delete(f"{BASE_URL}/api/batches/{bid}")
        assert rd.status_code == 400
        assert "linked contribution" in rd.text.lower()


class TestRegression:
    def test_contribution_without_batch_still_works(self, admin_session, scratch_project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{scratch_project}/contributions", json={
            "date": TODAY, "partner": "Alice", "amount": 1000,
            "description": "no-batch"
        })
        assert r.status_code == 200
        assert r.json().get("batch_id") in (None, "")

    def test_split_contribution_with_batch(self, admin_session, scratch_batch):
        pid, bid = scratch_batch
        r = admin_session.post(f"{BASE_URL}/api/projects/{pid}/contributions/split", json={
            "date": TODAY, "amount": 10000, "description": "split-batch",
            "batch_id": bid
        })
        assert r.status_code == 200, r.text
