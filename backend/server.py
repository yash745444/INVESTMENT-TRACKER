from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import logging
import secrets
import bcrypt
import jwt
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import math
import yfinance as yf

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Yash Wealth Command Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

JWT_ALGORITHM = "HS256"
PARTNERS = ["Yash Sojitra", "Sanjay Jogani", "Pranay Jetani", "Max Ma"]
CURRENCIES = ["AUD", "USD", "INR"]
FX_PROVIDER_URL = "https://open.er-api.com/v6/latest/AUD"
FX_REFRESH_SECONDS = int(os.environ.get("FX_REFRESH_SECONDS", "43200"))


# ---------------- helpers ----------------

def doc_out(doc):
    if not doc:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


def now_utc():
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": now_utc() + timedelta(minutes=60), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": now_utc() + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, user_id: str, email: str):
    response.set_cookie("access_token", create_access_token(user_id, email),
                        httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user_id),
                        httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request):
    user = None
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    bearer = auth[7:] if auth.startswith("Bearer ") else None
    if not token and bearer:
        token = bearer
    if token:
        try:
            payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
            if payload.get("type") == "access":
                user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        except jwt.InvalidTokenError:
            user = None
    if not user:
        st = request.cookies.get("session_token") or bearer
        if st:
            sess = await db.user_sessions.find_one({"session_token": st})
            if sess:
                exp = sess.get("expires_at")
                if isinstance(exp, str):
                    exp = datetime.fromisoformat(exp)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp > now_utc():
                    user = await db.users.find_one({"_id": ObjectId(sess["user_id"])})
    if not user:
        raise HTTPException(401, "Not authenticated")
    user["id"] = str(user.pop("_id"))
    user.pop("password_hash", None)
    if user.get("status", "approved") != "approved" and request.url.path not in (
            "/api/auth/me", "/api/auth/logout", "/api/auth/refresh"):
        raise HTTPException(403, "pending_approval")
    return user


# ---------------- FX rates ----------------

class RateService:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def refresh(self) -> bool:
        async with self.lock:
            try:
                async with httpx.AsyncClient(timeout=10) as http:
                    resp = await http.get(FX_PROVIDER_URL)
                    resp.raise_for_status()
                    payload = resp.json()
                if payload.get("result") != "success":
                    raise ValueError("provider error")
                src = payload.get("rates", {})
                rates = {c: float(src[c]) for c in CURRENCIES}
                if any(v <= 0 for v in rates.values()):
                    raise ValueError("invalid rates")
                await db.fx_rates.replace_one({"_id": "AUD"}, {
                    "_id": "AUD", "base": "AUD", "rates": rates,
                    "fetched_at": now_utc().isoformat(),
                    "provider_updated_at": payload.get("time_last_update_unix"),
                }, upsert=True)
                log.info("FX rates refreshed: %s", rates)
                return True
            except Exception as e:
                log.warning("FX refresh failed: %s", e)
                return False

    async def get(self) -> dict:
        doc = await db.fx_rates.find_one({"_id": "AUD"})
        if not doc:
            if not await self.refresh():
                return {"base": "AUD", "rates": {"AUD": 1.0, "USD": 0.65, "INR": 55.0},
                        "fetched_at": None, "stale": True}
            doc = await db.fx_rates.find_one({"_id": "AUD"})
        fetched = datetime.fromisoformat(doc["fetched_at"])
        stale = (now_utc() - fetched).total_seconds() > FX_REFRESH_SECONDS * 2
        return {"base": "AUD", "rates": doc["rates"], "fetched_at": doc["fetched_at"],
                "stale": stale, "provider": "https://www.exchangerate-api.com/"}


rate_service = RateService()


async def fx_loop():
    while True:
        await asyncio.sleep(FX_REFRESH_SECONDS)
        await rate_service.refresh()


async def get_rates() -> dict:
    data = await rate_service.get()
    return data["rates"]


def to_aud(amount: float, currency: str, rates: dict) -> float:
    r = rates.get(currency, 1.0)
    return amount / r if r else amount


# ---------------- schemas ----------------

class LoginIn(BaseModel):
    email: str
    password: str


class ProjectIn(BaseModel):
    name: str
    address: Optional[str] = ""
    description: Optional[str] = ""
    status: Optional[str] = "active"
    partners: List[dict] = []  # [{name, percentage, email?}]
    final_profit: float = 0  # owner's share of project profit when finished
    current_value: float = 0  # estimated current project value (as at)
    land_cost: float = 0  # land purchase price
    stamp_duty: float = 0  # transfer/stamp duty on land (auto-calc in UI, overridable)


class ContributionIn(BaseModel):
    date: str
    partner: str
    amount: float
    description: Optional[str] = ""
    batch_id: Optional[str] = None


class CostIn(BaseModel):
    date: str
    category: str
    description: Optional[str] = ""
    amount: float
    paid_by: Optional[str] = ""


class LoanIn(BaseModel):
    name: str
    lender: Optional[str] = ""
    type: str  # interest_only | amortizing
    annual_rate: float
    term_months: int
    start_date: str
    drawdowns: List[dict] = []  # [{date, amount, description}]


class DrawdownIn(BaseModel):
    date: str
    amount: float
    description: Optional[str] = ""


class LedgerIn(BaseModel):
    date: str
    type: str  # paid_on_behalf | settlement | personal
    from_partner: str  # payer (paid_on_behalf/personal) / sender (settlement)
    to_partner: str    # beneficiary (paid_on_behalf/personal) / receiver (settlement)
    amount: float
    project_id: Optional[str] = None
    project_name: Optional[str] = ""
    note: Optional[str] = ""


class FeasibilityIn(BaseModel):
    name: str
    project_type: str = "single_dwelling"  # single_dwelling | duplex | multi_dwelling | subdivision
    land_cost: float = 0
    stamp_duty: float = 0
    acquisition_legal: float = 0
    council_permits: float = 0
    design_architect: float = 0
    engineering: float = 0
    surveying: float = 0
    project_management: float = 0
    demolition: float = 0
    site_works: float = 0
    construction_cost: float = 0
    contingency_pct: float = 10
    holding_costs: float = 0
    finance_interest: float = 0
    bond: float = 0
    marketing: float = 0
    agent_fees: float = 0
    legal: float = 0
    other_costs: float = 0
    loan_amount: float = 0
    expected_revenue: float = 0


class PersonalLoanIn(BaseModel):
    lender: str
    amount: float
    date: str
    type: str  # interest | profit_share
    annual_rate: Optional[float] = 0       # interest type only
    project_id: Optional[str] = None       # profit_share type
    basis_amount: Optional[float] = 0      # profit_share override; defaults to my contributions in project
    notes: Optional[str] = ""


class ProfitIn(BaseModel):
    final_profit: float


class PartnerLinkIn(BaseModel):
    partner_name: str


class GoogleSessionIn(BaseModel):
    session_id: str


class StatusIn(BaseModel):
    status: str


class InvestmentIn(BaseModel):
    type: str  # shares | term_insurance | other
    name: str
    currency: str = "AUD"
    amount: float = 0
    date: Optional[str] = ""
    notes: Optional[str] = ""
    symbol: Optional[str] = ""
    quantity: Optional[float] = 0
    leverage: Optional[float] = 1
    current_price: Optional[float] = 0
    price_currency: Optional[str] = ""
    buy_price: Optional[float] = 0


class PropertyIn(BaseModel):
    name: str
    address: Optional[str] = ""
    purchase_date: Optional[str] = ""
    purchase_price: float = 0
    current_value: float = 0
    monthly_rent: float = 0
    debt: float = 0
    currency: str = "AUD"
    partners: List[dict] = []  # [{name, percentage}]
    notes: Optional[str] = ""


# ---------------- auth routes ----------------

@app.post("/api/auth/login")
async def login(data: LoginIn, request: Request, response: Response):
    email = data.email.lower().strip()
    identifier = f"{request.client.host}:{email}"
    attempts = await db.login_attempts.find_one({"identifier": identifier})
    if attempts and attempts.get("count", 0) >= 5:
        locked = attempts.get("locked_until")
        if locked and datetime.fromisoformat(locked) > now_utc():
            raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1},
             "$set": {"locked_until": (now_utc() + timedelta(minutes=15)).isoformat()}},
            upsert=True)
        raise HTTPException(401, "Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    set_auth_cookies(response, str(user["_id"]), email)
    return {"id": str(user["_id"]), "email": email, "name": user.get("name", ""),
            "picture": user.get("picture", ""), "role": user.get("role", "user"),
            "status": user.get("status", "approved")}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    st = request.cookies.get("session_token")
    if st:
        await db.user_sessions.delete_many({"session_token": st})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("shares_unlock", path="/")
    return {"ok": True}


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@app.post("/api/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(401, "User not found")
    response.set_cookie("access_token", create_access_token(str(user["_id"]), user["email"]),
                        httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    return {"ok": True}


# ---------------- rates ----------------

@app.get("/api/rates")
async def rates(user=Depends(get_current_user)):
    return await rate_service.get()


# ---------------- projects ----------------

@app.get("/api/projects")
async def list_projects(user=Depends(get_current_user)):
    out = []
    query = {"$or": [{"user_id": user["id"]}, {"partners.email": user["email"]}]}
    async for p in db.projects.find(query).sort("created_at", -1):
        pid = str(p["_id"])
        owner_id = p.get("user_id")
        p = doc_out(p)
        p["shared"] = owner_id != user["id"]
        contrib = 0.0
        async for c in db.contributions.find({"project_id": pid}):
            contrib += c["amount"]
        cost = 0.0
        async for c in db.costs.find({"project_id": pid}):
            cost += c["amount"]
        drawn, outstanding, monthly = 0.0, 0.0, 0.0
        async for l in db.loans.find({"project_id": pid}):
            m = loan_metrics(l)
            drawn += m["drawn"]
            outstanding += m["outstanding"]
            monthly += m["monthly_payment"]
        project_cost = p.get("land_cost", 0) + p.get("stamp_duty", 0) + cost
        equity = project_cost - drawn if project_cost > 0 else contrib
        p["totals"] = {"contributions": contrib, "costs": cost, "drawn": drawn,
                       "outstanding": outstanding, "monthly_repayment": monthly,
                       "project_cost": project_cost, "equity": equity}
        out.append(p)
    return out


@app.post("/api/projects")
async def create_project(data: ProjectIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    total_pct = sum(p.get("percentage", 0) for p in doc["partners"])
    if doc["partners"] and abs(total_pct - 100) > 0.01:
        raise HTTPException(400, f"Partner percentages must sum to 100 (currently {total_pct})")
    for pt in doc["partners"]:
        if pt.get("email"):
            pt["email"] = pt["email"].lower().strip()
    doc["user_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    res = await db.projects.insert_one(doc)
    return doc_out(await db.projects.find_one({"_id": res.inserted_id}))


@app.get("/api/projects/{pid}")
async def get_project(pid: str, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    owner_id = p.get("user_id")
    p = doc_out(p)
    p["shared"] = owner_id != user["id"]
    return p


@app.put("/api/projects/{pid}")
async def update_project(pid: str, data: ProjectIn, user=Depends(get_current_user)):
    existing = await db.projects.find_one({"_id": ObjectId(pid)})
    if not existing or existing.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can edit")
    doc = data.model_dump()
    total_pct = sum(p.get("percentage", 0) for p in doc["partners"])
    if doc["partners"] and abs(total_pct - 100) > 0.01:
        raise HTTPException(400, f"Partner percentages must sum to 100 (currently {total_pct})")
    for pt in doc["partners"]:
        if pt.get("email"):
            pt["email"] = pt["email"].lower().strip()
    await db.projects.update_one({"_id": ObjectId(pid)}, {"$set": doc})
    return doc_out(await db.projects.find_one({"_id": ObjectId(pid)}))


@app.delete("/api/projects/{pid}")
async def delete_project(pid: str, user=Depends(get_current_user)):
    existing = await db.projects.find_one({"_id": ObjectId(pid)})
    if not existing or existing.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can delete")
    await db.projects.delete_one({"_id": ObjectId(pid)})
    for coll in ("contributions", "costs", "loans", "contribution_batches"):
        await db[coll].delete_many({"project_id": pid})
    return {"ok": True}


# ---------------- contributions / costs ----------------

async def get_project_access(pid: str, user: dict):
    p = await db.projects.find_one({"_id": ObjectId(pid)})
    if not p:
        raise HTTPException(404, "Project not found")
    if p.get("user_id") == user["id"] or any(
            pt.get("email") == user["email"] for pt in p.get("partners", [])):
        return p
    raise HTTPException(403, "No access to this project")


async def get_loan_checked(lid: str, user: dict, write: bool = False):
    l = await db.loans.find_one({"_id": ObjectId(lid)})
    if not l:
        raise HTTPException(404, "Loan not found")
    p = await get_project_access(l["project_id"], user)
    if write and p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can modify loans")
    return l


async def crud_list(coll, pid):
    out = []
    async for d in db[coll].find({"project_id": pid}).sort("date", -1):
        out.append(doc_out(d))
    return out


@app.get("/api/projects/{pid}/contributions")
async def list_contributions(pid: str, user=Depends(get_current_user)):
    await get_project_access(pid, user)
    return await crud_list("contributions", pid)


@app.post("/api/projects/{pid}/contributions")
async def add_contribution(pid: str, data: ContributionIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        my_partner = next((pt for pt in p.get("partners", []) if pt.get("email") == user["email"]), None)
        if not my_partner or data.partner != my_partner.get("name"):
            raise HTTPException(403, "You can only add contributions under your own partner name")
    if data.batch_id:
        b = await db.contribution_batches.find_one({"_id": ObjectId(data.batch_id), "project_id": pid})
        if not b:
            raise HTTPException(400, "Invalid batch")
    doc = data.model_dump(); doc["project_id"] = pid; doc["user_id"] = p["user_id"]
    if not doc.get("batch_id"):
        doc.pop("batch_id", None)
    res = await db.contributions.insert_one(doc)
    return doc_out(await db.contributions.find_one({"_id": res.inserted_id}))


class SplitContributionIn(BaseModel):
    date: str
    amount: float
    description: Optional[str] = ""
    batch_id: Optional[str] = None


@app.post("/api/projects/{pid}/contributions/split")
async def add_contribution_split(pid: str, data: SplitContributionIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can add company contributions")
    partners = [pt for pt in p.get("partners", []) if pt.get("percentage", 0) > 0]
    if not partners:
        raise HTTPException(400, "Project has no partners with ownership percentages")
    if data.batch_id:
        b = await db.contribution_batches.find_one({"_id": ObjectId(data.batch_id), "project_id": pid})
        if not b:
            raise HTTPException(400, "Invalid batch")
    docs = []
    allocated = 0.0
    for i, pt in enumerate(partners):
        amt = round(data.amount * pt["percentage"] / 100, 2)
        if i == len(partners) - 1:
            amt = round(data.amount - allocated, 2)  # remainder to last partner so total stays exact
        allocated += amt
        d = {"date": data.date, "partner": pt["name"], "amount": amt,
             "description": f"{data.description or 'Company contribution'} (company split {pt['percentage']}%)",
             "project_id": pid, "user_id": p["user_id"]}
        if data.batch_id:
            d["batch_id"] = data.batch_id
        docs.append(d)
    await db.contributions.insert_many(docs)
    return {"inserted": len(docs), "total": round(allocated, 2)}


# ---------------- contribution batches (capital calls) ----------------

class BatchIn(BaseModel):
    name: str
    target_amount: float
    note: Optional[str] = ""


async def get_batch_checked(bid: str, user: dict, write: bool = False):
    try:
        b = await db.contribution_batches.find_one({"_id": ObjectId(bid)})
    except Exception:
        b = None
    if not b:
        raise HTTPException(404, "Batch not found")
    p = await get_project_access(b["project_id"], user)
    if write and p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can manage batches")
    return b


async def batch_progress(batch_id: str, target: float, project: dict) -> dict:
    paid_by = {}
    async for c in db.contributions.find({"batch_id": batch_id}):
        paid_by[c["partner"]] = paid_by.get(c["partner"], 0.0) + c["amount"]
    partners = []
    paid_total = 0.0
    expected_total = 0.0
    for pt in project.get("partners", []):
        pct = pt.get("percentage", 0)
        exp = round(target * pct / 100, 2)
        paid = round(paid_by.get(pt["name"], 0.0), 2)
        partners.append({"name": pt["name"], "percentage": pct, "expected": exp,
                         "paid": paid, "remaining": round(exp - paid, 2)})
        paid_total += paid
        expected_total += exp
    return {"partners": partners, "paid_total": round(paid_total, 2),
            "expected_total": round(expected_total, 2),
            "remaining_total": round(expected_total - paid_total, 2),
            "fully_paid": all(pp["remaining"] <= 0.005 for pp in partners)}


@app.get("/api/projects/{pid}/batches")
async def list_batches(pid: str, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    out = []
    async for b in db.contribution_batches.find({"project_id": pid}).sort("created_at", 1):
        b = doc_out(b)
        b["progress"] = await batch_progress(b["id"], b["target_amount"], p)
        out.append(b)
    return out


@app.post("/api/projects/{pid}/batches")
async def add_batch(pid: str, data: BatchIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can create batches")
    if data.target_amount <= 0:
        raise HTTPException(400, "Target amount must be positive")
    doc = data.model_dump()
    doc["project_id"] = pid
    doc["user_id"] = p["user_id"]
    doc["status"] = "open"
    doc["created_at"] = now_utc().isoformat()
    res = await db.contribution_batches.insert_one(doc)
    b = doc_out(await db.contribution_batches.find_one({"_id": res.inserted_id}))
    b["progress"] = await batch_progress(b["id"], b["target_amount"], p)
    return b


@app.post("/api/batches/{bid}/close")
async def close_batch(bid: str, user=Depends(get_current_user)):
    await get_batch_checked(bid, user, write=True)
    await db.contribution_batches.update_one({"_id": ObjectId(bid)},
        {"$set": {"status": "closed", "closed_at": now_utc().isoformat()}})
    return doc_out(await db.contribution_batches.find_one({"_id": ObjectId(bid)}))


@app.post("/api/batches/{bid}/reopen")
async def reopen_batch(bid: str, user=Depends(get_current_user)):
    await get_batch_checked(bid, user, write=True)
    await db.contribution_batches.update_one({"_id": ObjectId(bid)},
        {"$set": {"status": "open"}, "$unset": {"closed_at": ""}})
    return doc_out(await db.contribution_batches.find_one({"_id": ObjectId(bid)}))


class SettleAllIn(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = ""


@app.post("/api/batches/{bid}/settle-all")
async def settle_batch(bid: str, data: SettleAllIn, user=Depends(get_current_user)):
    b = await get_batch_checked(bid, user, write=True)
    p = await db.projects.find_one({"_id": ObjectId(b["project_id"])})
    pr = await batch_progress(bid, b.get("target_amount", 0), p)
    if pr["remaining_total"] <= 0.005:
        raise HTTPException(400, "Batch is already fully paid")
    date = data.date or now_utc().date().isoformat()
    docs = []
    for pp in pr["partners"]:
        if pp["remaining"] > 0.005:
            docs.append({"date": date, "partner": pp["name"], "amount": pp["remaining"],
                         "description": data.description or f"{b['name']} — share payment",
                         "project_id": b["project_id"], "user_id": b["user_id"], "batch_id": bid})
    if docs:
        await db.contributions.insert_many(docs)
    return {"inserted": len(docs), "total": round(sum(d["amount"] for d in docs), 2)}


@app.delete("/api/batches/{bid}")
async def delete_batch(bid: str, user=Depends(get_current_user)):
    await get_batch_checked(bid, user, write=True)
    linked = await db.contributions.count_documents({"batch_id": bid})
    if linked:
        raise HTTPException(400, f"Batch has {linked} linked contribution(s) — remove them first")
    await db.contribution_batches.delete_one({"_id": ObjectId(bid)})
    return {"ok": True}


@app.put("/api/contributions/{cid}")
async def update_contribution(cid: str, data: ContributionIn, user=Depends(get_current_user)):
    c = await db.contributions.find_one({"_id": ObjectId(cid)})
    if not c or c.get("user_id") != user["id"]:
        raise HTTPException(403, "Not allowed")
    if data.batch_id:
        b = await db.contribution_batches.find_one({"_id": ObjectId(data.batch_id), "project_id": c["project_id"]})
        if not b:
            raise HTTPException(400, "Invalid batch")
    doc = data.model_dump()
    if not doc.get("batch_id"):
        doc["batch_id"] = None
    await db.contributions.update_one({"_id": ObjectId(cid)}, {"$set": doc})
    return doc_out(await db.contributions.find_one({"_id": ObjectId(cid)}))


@app.delete("/api/contributions/{cid}")
async def delete_contribution(cid: str, user=Depends(get_current_user)):
    c = await db.contributions.find_one({"_id": ObjectId(cid)})
    if not c or c.get("user_id") != user["id"]:
        raise HTTPException(403, "Not allowed")
    await db.contributions.delete_one({"_id": ObjectId(cid)})
    return {"ok": True}


@app.get("/api/projects/{pid}/costs")
async def list_costs(pid: str, user=Depends(get_current_user)):
    await get_project_access(pid, user)
    return await crud_list("costs", pid)


@app.post("/api/projects/{pid}/costs")
async def add_cost(pid: str, data: CostIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can add records")
    doc = data.model_dump(); doc["project_id"] = pid; doc["user_id"] = p["user_id"]
    res = await db.costs.insert_one(doc)
    return doc_out(await db.costs.find_one({"_id": res.inserted_id}))


@app.put("/api/costs/{cid}")
async def update_cost(cid: str, data: CostIn, user=Depends(get_current_user)):
    c = await db.costs.find_one({"_id": ObjectId(cid)})
    if not c or c.get("user_id") != user["id"]:
        raise HTTPException(403, "Not allowed")
    await db.costs.update_one({"_id": ObjectId(cid)}, {"$set": data.model_dump()})
    return doc_out(await db.costs.find_one({"_id": ObjectId(cid)}))


@app.delete("/api/costs/{cid}")
async def delete_cost(cid: str, user=Depends(get_current_user)):
    c = await db.costs.find_one({"_id": ObjectId(cid)})
    if not c or c.get("user_id") != user["id"]:
        raise HTTPException(403, "Not allowed")
    await db.costs.delete_one({"_id": ObjectId(cid)})
    return {"ok": True}


class BulkCostsIn(BaseModel):
    items: List[CostIn]


@app.post("/api/projects/{pid}/costs/bulk")
async def add_costs_bulk(pid: str, data: BulkCostsIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can add records")
    docs = []
    for item in data.items:
        d = item.model_dump()
        d["project_id"] = pid
        d["user_id"] = p["user_id"]
        docs.append(d)
    if docs:
        await db.costs.insert_many(docs)
    return {"inserted": len(docs)}


# ---------------- loans ----------------

def months_between(start: datetime, end: datetime) -> int:
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def loan_metrics(loan: dict) -> dict:
    drawn = sum(d.get("amount", 0) for d in loan.get("drawdowns", []))
    r = loan.get("annual_rate", 0) / 100 / 12
    term = max(1, loan.get("term_months", 1))
    try:
        start = datetime.fromisoformat(str(loan["start_date"])).replace(tzinfo=timezone.utc)
    except Exception:
        start = now_utc()
    elapsed = min(months_between(start, now_utc()), term)
    remaining = max(term - elapsed, 1)
    if loan.get("type") == "interest_only":
        outstanding = drawn
        monthly = drawn * r
    else:
        if r > 0 and elapsed < term:
            outstanding = drawn * ((1 + r) ** term - (1 + r) ** elapsed) / ((1 + r) ** term - 1) if term else drawn
        else:
            outstanding = drawn if elapsed < term else 0.0
        monthly = outstanding * r / (1 - (1 + r) ** -remaining) if r > 0 else outstanding / remaining
    return {"drawn": drawn, "outstanding": max(0.0, outstanding),
            "monthly_payment": max(0.0, monthly),
            "elapsed_months": elapsed, "remaining_months": remaining}


@app.get("/api/projects/{pid}/loans")
async def list_loans(pid: str, user=Depends(get_current_user)):
    await get_project_access(pid, user)
    out = []
    async for l in db.loans.find({"project_id": pid}):
        l = doc_out(l)
        l["metrics"] = loan_metrics(l)
        out.append(l)
    return out


@app.post("/api/projects/{pid}/loans")
async def add_loan(pid: str, data: LoanIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can add loans")
    if data.type not in ("interest_only", "amortizing"):
        raise HTTPException(400, "type must be interest_only or amortizing")
    doc = data.model_dump(); doc["project_id"] = pid; doc["user_id"] = p["user_id"]
    res = await db.loans.insert_one(doc)
    l = doc_out(await db.loans.find_one({"_id": res.inserted_id}))
    l["metrics"] = loan_metrics(l)
    return l


@app.put("/api/loans/{lid}")
async def update_loan(lid: str, data: LoanIn, user=Depends(get_current_user)):
    await get_loan_checked(lid, user, write=True)
    doc = data.model_dump()
    doc.pop("drawdowns", None)  # drawdowns managed via dedicated endpoints; never wiped by edits
    await db.loans.update_one({"_id": ObjectId(lid)}, {"$set": doc})
    l = doc_out(await db.loans.find_one({"_id": ObjectId(lid)}))
    l["metrics"] = loan_metrics(l)
    return l


@app.delete("/api/loans/{lid}")
async def delete_loan(lid: str, user=Depends(get_current_user)):
    await get_loan_checked(lid, user, write=True)
    await db.loans.delete_one({"_id": ObjectId(lid)})
    return {"ok": True}


@app.post("/api/loans/{lid}/drawdowns")
async def add_drawdown(lid: str, data: DrawdownIn, user=Depends(get_current_user)):
    await get_loan_checked(lid, user, write=True)
    await db.loans.update_one({"_id": ObjectId(lid)},
                              {"$push": {"drawdowns": data.model_dump()}})
    l = doc_out(await db.loans.find_one({"_id": ObjectId(lid)}))
    l["metrics"] = loan_metrics(l)
    return l


@app.put("/api/loans/{lid}/drawdowns/{idx}")
async def update_drawdown(lid: str, idx: int, data: DrawdownIn, user=Depends(get_current_user)):
    l = await get_loan_checked(lid, user, write=True)
    dds = l.get("drawdowns", [])
    if idx < 0 or idx >= len(dds):
        raise HTTPException(404, "Drawdown not found")
    dds[idx] = data.model_dump()
    await db.loans.update_one({"_id": ObjectId(lid)}, {"$set": {"drawdowns": dds}})
    out = doc_out(await db.loans.find_one({"_id": ObjectId(lid)}))
    out["metrics"] = loan_metrics(out)
    return out


@app.delete("/api/loans/{lid}/drawdowns/{idx}")
async def delete_drawdown(lid: str, idx: int, user=Depends(get_current_user)):
    l = await get_loan_checked(lid, user, write=True)
    dds = l.get("drawdowns", [])
    if idx < 0 or idx >= len(dds):
        raise HTTPException(404, "Drawdown not found")
    dds.pop(idx)
    await db.loans.update_one({"_id": ObjectId(lid)}, {"$set": {"drawdowns": dds}})
    return {"ok": True}


@app.get("/api/loans/{lid}/schedule")
async def loan_schedule(lid: str, months: int = 12, user=Depends(get_current_user)):
    loan = await get_loan_checked(lid, user)
    m = loan_metrics(loan)
    r = loan.get("annual_rate", 0) / 100 / 12
    balance = m["outstanding"]
    monthly = m["monthly_payment"]
    rows = []
    for i in range(1, months + 1):
        interest = balance * r
        principal = 0.0 if loan["type"] == "interest_only" else max(0.0, monthly - interest)
        balance = max(0.0, balance - principal)
        rows.append({"month": i, "payment": round(monthly, 2), "interest": round(interest, 2),
                     "principal": round(principal, 2), "balance": round(balance, 2)})
    return {"metrics": m, "schedule": rows}


# ---------------- partner ledger ----------------

@app.get("/api/ledger")
async def list_ledger(user=Depends(get_current_user)):
    out = []
    async for d in db.ledger.find({"user_id": user["id"]}).sort("date", -1):
        out.append(doc_out(d))
    return out


@app.post("/api/ledger")
async def add_ledger(data: LedgerIn, user=Depends(get_current_user)):
    if data.from_partner == data.to_partner:
        raise HTTPException(400, "Partners must be different")
    if data.type not in ("paid_on_behalf", "settlement", "personal", "external"):
        raise HTTPException(400, "Invalid transaction type")
    doc = data.model_dump()
    doc["user_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    res = await db.ledger.insert_one(doc)
    return doc_out(await db.ledger.find_one({"_id": res.inserted_id}))


@app.put("/api/ledger/{tid}")
async def update_ledger(tid: str, data: LedgerIn, user=Depends(get_current_user)):
    t = await db.ledger.find_one({"_id": ObjectId(tid)})
    if not t or t.get("user_id") != user["id"]:
        raise HTTPException(403, "Not allowed")
    if data.from_partner == data.to_partner:
        raise HTTPException(400, "Partners must be different")
    if data.type not in ("paid_on_behalf", "settlement", "personal", "external"):
        raise HTTPException(400, "Invalid transaction type")
    await db.ledger.update_one({"_id": ObjectId(tid)}, {"$set": data.model_dump()})
    return doc_out(await db.ledger.find_one({"_id": ObjectId(tid)}))


@app.delete("/api/ledger/{tid}")
async def delete_ledger(tid: str, user=Depends(get_current_user)):
    t = await db.ledger.find_one({"_id": ObjectId(tid)})
    if not t or t.get("user_id") != user["id"]:
        raise HTTPException(403, "Not allowed")
    await db.ledger.delete_one({"_id": ObjectId(tid)})
    return {"ok": True}


def pairwise_balances(txns) -> dict:
    net = {}
    for t in txns:
        a, b = t["from_partner"], t["to_partner"]
        amt = t["amount"]
        # positive net[a][b] means b owes a
        if t["type"] in ("paid_on_behalf", "personal", "external"):
            net.setdefault(a, {}).setdefault(b, 0.0)
            net[a][b] += amt
        else:  # settlement: money actually moved from a to b, reducing what b owes a
            net.setdefault(b, {}).setdefault(a, 0.0)
            net[b][a] -= amt
    return net


async def _ledger_balances_for(user_id: str) -> dict:
    txns = [t async for t in db.ledger.find({"user_id": user_id, "type": {"$ne": "personal"}})]
    net = pairwise_balances(txns)
    pairs = []
    seen = set()
    for a in PARTNERS:
        for b in PARTNERS:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            ab = net.get(a, {}).get(b, 0.0)
            ba = net.get(b, {}).get(a, 0.0)
            n = ab - ba
            if abs(n) < 0.005:
                pairs.append({"a": a, "b": b, "amount": 0.0, "owes": None})
            elif n > 0:
                pairs.append({"a": a, "b": b, "amount": round(n, 2), "owes": f"{b} owes {a}"})
            else:
                pairs.append({"a": a, "b": b, "amount": round(-n, 2), "owes": f"{a} owes {b}"})
    names = set(PARTNERS)
    for t in txns:
        names.add(t["from_partner"]); names.add(t["to_partner"])
    totals = {}
    for n in names:
        totals[n] = round(
            sum(net.get(n, {}).values()) - sum(net.get(o, {}).get(n, 0.0) for o in names if o != n), 2)
    return {"pairs": pairs, "totals": totals,
            "extras": {k: v for k, v in totals.items() if k not in PARTNERS}}


async def _personal_pairs_for(user_id: str) -> list:
    txns = [t async for t in db.ledger.find({"user_id": user_id, "type": "personal"})]
    net = pairwise_balances(txns)
    names = set()
    for t in txns:
        names.add(t["from_partner"]); names.add(t["to_partner"])
    pairs = []
    seen = set()
    for a in names:
        for b in names:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            n = net.get(a, {}).get(b, 0.0) - net.get(b, {}).get(a, 0.0)
            if abs(n) > 0.005:
                debtor, creditor = (b, a) if n > 0 else (a, b)
                pairs.append({"debtor": debtor, "creditor": creditor, "amount": round(abs(n), 2)})
    return pairs


@app.get("/api/ledger/balances")
async def ledger_balances(user=Depends(get_current_user)):
    return await _ledger_balances_for(user["id"])


@app.get("/api/ledger/personal")
async def personal_balances(user=Depends(get_current_user)):
    return {"pairs": await _personal_pairs_for(user["id"]), "me": user.get("name", "")}


@app.get("/api/ledger/report")
async def ledger_report(user=Depends(get_current_user)):
    txns = [doc_out(t) async for t in db.ledger.find({"user_id": user["id"], "type": {"$ne": "personal"}}).sort("date", 1)]
    personal = [doc_out(t) async for t in db.ledger.find({"user_id": user["id"], "type": "personal"}).sort("date", 1)]
    bal = await _ledger_balances_for(user["id"])
    per_pairs = await _personal_pairs_for(user["id"])
    return {"transactions": txns, "personal_transactions": personal, "balances": bal,
            "personal": {"pairs": per_pairs, "me": user.get("name", "")}, "partners": PARTNERS,
            "generated_at": now_utc().isoformat()}


# ---------------- investments ----------------

@app.get("/api/investments")
async def list_investments(request: Request, user=Depends(get_current_user)):
    visible = shares_visible(request)
    out = []
    async for d in db.investments.find({"user_id": user["id"]}).sort("created_at", -1):
        d = doc_out(d)
        if d.get("type") in ("shares", "crypto") and not visible:
            out.append({"id": d["id"], "type": d.get("type"), "name": "Hidden holding", "symbol": "",
                        "quantity": 0, "leverage": 1, "current_price": 0, "price_currency": "",
                        "currency": "AUD", "amount": 0, "date": "", "notes": "", "redacted": True})
        else:
            out.append(d)
    return out


@app.post("/api/investments")
async def add_investment(data: InvestmentIn, user=Depends(get_current_user)):
    doc = data.model_dump(); doc["user_id"] = user["id"]; doc["created_at"] = now_utc().isoformat()
    res = await db.investments.insert_one(doc)
    return doc_out(await db.investments.find_one({"_id": res.inserted_id}))


@app.put("/api/investments/{iid}")
async def update_investment(iid: str, data: InvestmentIn, user=Depends(get_current_user)):
    res = await db.investments.update_one({"_id": ObjectId(iid), "user_id": user["id"]}, {"$set": data.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Investment not found")
    return doc_out(await db.investments.find_one({"_id": ObjectId(iid)}))


@app.delete("/api/investments/{iid}")
async def delete_investment(iid: str, user=Depends(get_current_user)):
    res = await db.investments.delete_one({"_id": ObjectId(iid), "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Investment not found")
    return {"ok": True}


# ---------------- properties ----------------

@app.get("/api/properties")
async def list_properties(user=Depends(get_current_user)):
    out = []
    async for d in db.properties.find(
            {"$or": [{"user_id": user["id"]}, {"partners.email": user["email"]}]}).sort("created_at", -1):
        shared = d.get("user_id") != user["id"]
        d = doc_out(d)
        d["shared"] = shared
        out.append(d)
    return out


@app.post("/api/properties")
async def add_property(data: PropertyIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    for pt in doc.get("partners", []):
        if pt.get("email"):
            pt["email"] = pt["email"].lower().strip()
    doc["user_id"] = user["id"]; doc["created_at"] = now_utc().isoformat()
    res = await db.properties.insert_one(doc)
    return doc_out(await db.properties.find_one({"_id": res.inserted_id}))


@app.put("/api/properties/{pid}")
async def update_property(pid: str, data: PropertyIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    for pt in doc.get("partners", []):
        if pt.get("email"):
            pt["email"] = pt["email"].lower().strip()
    res = await db.properties.update_one({"_id": ObjectId(pid), "user_id": user["id"]}, {"$set": doc})
    if not res.matched_count:
        raise HTTPException(404, "Property not found")
    return doc_out(await db.properties.find_one({"_id": ObjectId(pid)}))


@app.delete("/api/properties/{pid}")
async def delete_property(pid: str, user=Depends(get_current_user)):
    res = await db.properties.delete_one({"_id": ObjectId(pid), "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Property not found")
    return {"ok": True}


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


# ---------------- personal loans (private lenders) ----------------

async def personal_loan_metrics(loan: dict, user: dict) -> dict:
    amount = loan.get("amount", 0)
    if loan.get("type") == "profit_share":
        my_name = user.get("partner_name") or user.get("name") or "Yash"
        basis = loan.get("basis_amount") or 0
        profit = 0.0
        project_name = loan.get("project_name", "")
        if loan.get("project_id"):
            try:
                proj = await db.projects.find_one({"_id": ObjectId(loan["project_id"])})
            except Exception:
                proj = None
            if proj:
                profit = proj.get("final_profit", 0) or 0
                project_name = proj.get("name", project_name)
                if not basis:
                    async for c in db.contributions.find({"project_id": loan["project_id"], "partner": my_name}):
                        basis += c["amount"]
        share = amount / basis if basis > 0 else 0
        ret = profit * share
        return {"basis": round(basis, 2), "share_pct": round(share * 100, 2),
                "project_profit": round(profit, 2), "return_amount": round(ret, 2),
                "total_owed": round(amount + ret, 2), "project_name": project_name}
    years = 0.0
    try:
        start = datetime.fromisoformat(str(loan["date"])).replace(tzinfo=timezone.utc)
        years = max(0.0, (now_utc() - start).days / 365.25)
    except Exception:
        pass
    accrued = amount * (loan.get("annual_rate", 0) or 0) / 100 * years
    return {"years": round(years, 2), "accrued_interest": round(accrued, 2),
            "return_amount": round(accrued, 2), "total_owed": round(amount + accrued, 2)}


@app.get("/api/personal-loans")
async def list_personal_loans(user=Depends(get_current_user)):
    out = []
    async for d in db.personal_loans.find({"user_id": user["id"]}).sort("created_at", -1):
        d = doc_out(d)
        d["computed"] = await personal_loan_metrics(d, user)
        out.append(d)
    return out


@app.post("/api/personal-loans")
async def add_personal_loan(data: PersonalLoanIn, user=Depends(get_current_user)):
    if data.type not in ("interest", "profit_share"):
        raise HTTPException(400, "type must be interest or profit_share")
    if data.type == "profit_share" and not (data.project_id or data.basis_amount):
        raise HTTPException(400, "Profit-share loans need a linked project or a basis amount")
    doc = data.model_dump()
    if data.project_id:
        proj = await db.projects.find_one({"_id": ObjectId(data.project_id)})
        if proj:
            doc["project_name"] = proj.get("name", "")
    doc["user_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    res = await db.personal_loans.insert_one(doc)
    d = doc_out(await db.personal_loans.find_one({"_id": res.inserted_id}))
    d["computed"] = await personal_loan_metrics(d, user)
    return d


@app.put("/api/personal-loans/{lid}")
async def update_personal_loan(lid: str, data: PersonalLoanIn, user=Depends(get_current_user)):
    existing = await db.personal_loans.find_one({"_id": ObjectId(lid), "user_id": user["id"]})
    if not existing:
        raise HTTPException(404, "Loan not found")
    if data.type not in ("interest", "profit_share"):
        raise HTTPException(400, "type must be interest or profit_share")
    if data.type == "profit_share" and not (data.project_id or data.basis_amount):
        raise HTTPException(400, "Profit-share loans need a linked project or a basis amount")
    doc = data.model_dump()
    doc["project_name"] = ""
    if data.project_id:
        proj = await db.projects.find_one({"_id": ObjectId(data.project_id)})
        if proj:
            doc["project_name"] = proj.get("name", "")
    await db.personal_loans.update_one({"_id": ObjectId(lid)}, {"$set": doc})
    d = doc_out(await db.personal_loans.find_one({"_id": ObjectId(lid)}))
    d["computed"] = await personal_loan_metrics(d, user)
    return d


@app.delete("/api/personal-loans/{lid}")
async def delete_personal_loan(lid: str, user=Depends(get_current_user)):
    res = await db.personal_loans.delete_one({"_id": ObjectId(lid), "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Loan not found")
    return {"ok": True}


@app.post("/api/projects/{pid}/profit")
async def set_project_profit(pid: str, data: ProfitIn, user=Depends(get_current_user)):
    p = await get_project_access(pid, user)
    if p.get("user_id") != user["id"]:
        raise HTTPException(403, "Only the project owner can set the outcome")
    await db.projects.update_one({"_id": ObjectId(pid)}, {"$set": {"final_profit": data.final_profit}})
    return {"ok": True, "final_profit": data.final_profit}


# ---------------- partner profiles ----------------

@app.post("/api/admin/users/{uid}/partner")
async def admin_link_partner(uid: str, data: PartnerLinkIn, user=Depends(require_admin)):
    res = await db.users.update_one({"_id": ObjectId(uid)},
                                    {"$set": {"partner_name": data.partner_name.strip()}})
    if not res.matched_count:
        raise HTTPException(404, "User not found")
    return {"ok": True}


async def _partner_projects(books_uid: str, name: str) -> list:
    projects = []
    async for p in db.projects.find({"user_id": books_uid, "partners.name": name}):
        pid = str(p["_id"])
        pct = next((pt.get("percentage", 0) for pt in p.get("partners", []) if pt.get("name") == name), 0)
        contrib = 0.0
        async for c in db.contributions.find({"project_id": pid, "partner": name}):
            contrib += c["amount"]
        projects.append({"id": pid, "name": p["name"], "percentage": pct,
                         "contributed": round(contrib, 2)})
    return projects


# ---------------- people (individual profiles) ----------------

class PersonIn(BaseModel):
    name: str
    email: Optional[str] = ""
    visibility: dict = {"projects": True, "properties": True, "debts": True, "loans": True}


@app.get("/api/people")
async def list_people(user=Depends(require_admin)):
    return [doc_out(d) async for d in db.people.find({"user_id": user["id"]}).sort("name", 1)]


@app.post("/api/people")
async def add_person(data: PersonIn, user=Depends(require_admin)):
    doc = data.model_dump()
    doc["name"] = doc["name"].strip()
    doc["email"] = (doc.get("email") or "").lower().strip()
    doc["user_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    res = await db.people.insert_one(doc)
    return doc_out(await db.people.find_one({"_id": res.inserted_id}))


@app.put("/api/people/{pid}")
async def update_person(pid: str, data: PersonIn, user=Depends(require_admin)):
    doc = data.model_dump()
    doc["name"] = doc["name"].strip()
    doc["email"] = (doc.get("email") or "").lower().strip()
    res = await db.people.update_one({"_id": ObjectId(pid), "user_id": user["id"]}, {"$set": doc})
    if not res.matched_count:
        raise HTTPException(404, "Person not found")
    return doc_out(await db.people.find_one({"_id": ObjectId(pid)}))


@app.delete("/api/people/{pid}")
async def delete_person(pid: str, user=Depends(require_admin)):
    res = await db.people.delete_one({"_id": ObjectId(pid), "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Person not found")
    return {"ok": True}


@app.get("/api/people/{pid}/profile")
async def person_profile(pid: str, user=Depends(require_admin)):
    person = await db.people.find_one({"_id": ObjectId(pid), "user_id": user["id"]})
    if not person:
        raise HTTPException(404, "Person not found")
    assoc = await _person_assoc(user["id"], person["name"], user)
    return {"name": person["name"], "email": person.get("email", ""),
            "visibility": person.get("visibility", {}), **assoc}


async def _person_assoc(books_uid: str, name: str, user: dict) -> dict:
    bal = await _ledger_balances_for(books_uid)
    personal = await _personal_pairs_for(books_uid)
    projects = await _partner_projects(books_uid, name)
    props = []
    async for pr in db.properties.find({"user_id": books_uid, "partners.name": name}):
        pct = next((pt.get("percentage", 0) for pt in pr.get("partners", []) if pt.get("name") == name), 0)
        props.append({"id": str(pr["_id"]), "name": pr.get("name", ""), "percentage": pct,
                      "equity_share": round((pr.get("current_value", 0) - pr.get("debt", 0)) * pct / 100, 2)})
    loans = []
    async for l in db.personal_loans.find({"user_id": books_uid, "lender": name}):
        d = doc_out(l)
        d["computed"] = await personal_loan_metrics(d, user)
        loans.append(d)
    return {"position": bal["totals"].get(name, 0),
            "personal": [x for x in personal if name in (x["debtor"], x["creditor"])],
            "projects": projects, "properties": props, "loans": loans}


@app.get("/api/partner/overview")
async def partner_overview(user=Depends(get_current_user)):
    if user.get("role") == "admin":
        names = list(PARTNERS)
        async for pe in db.people.find({"user_id": user["id"]}):
            if pe["name"].lower() not in [n.lower() for n in names]:
                names.append(pe["name"])
        profiles = []
        for name in names:
            profiles.append({"name": name, **(await _person_assoc(user["id"], name, user))})
        return {"scope": "all", "profiles": profiles}
    me = user.get("partner_name") or user.get("name")
    admin = await db.users.find_one({"role": "admin"})
    if not admin:
        raise HTTPException(404, "No company admin found")
    books_uid = str(admin["_id"])
    assoc = await _person_assoc(books_uid, me, user)
    person = await db.people.find_one({"user_id": books_uid, "name": me})
    vis = (person or {}).get("visibility") or {"projects": True, "properties": True, "debts": True, "loans": True}
    return {"scope": "self", "me": me, "visibility": vis,
            "position": assoc["position"] if vis.get("debts", True) else None,
            "personal": assoc["personal"] if vis.get("debts", True) else [],
            "projects": assoc["projects"] if vis.get("projects", True) else [],
            "properties": assoc["properties"] if vis.get("properties", True) else [],
            "loans": assoc["loans"] if vis.get("loans", True) else []}


# ---------------- market data (yfinance) ----------------

def market_search_sync(query: str):
    results = []
    for q in yf.Search(query, max_results=8, news_count=0).quotes:
        if q.get("quoteType") not in (None, "EQUITY"):
            continue
        sym = q.get("symbol")
        if not sym:
            continue
        results.append({"symbol": sym.upper(),
                        "name": q.get("longname") or q.get("shortname") or sym,
                        "exchange": q.get("exchange") or ""})
    return results[:8]


def market_quote_sync(ticker: str):
    t = yf.Ticker(ticker)
    hist = t.history(period="5d", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("no data")
    row = hist.dropna(subset=["Close"]).iloc[-1]
    price = float(row["Close"])
    if not math.isfinite(price):
        raise ValueError("invalid price")
    currency, name = "", ""
    try:
        currency = t.fast_info.get("currency") or ""
    except Exception:
        pass
    try:
        name = t.info.get("shortName") or ""
    except Exception:
        pass
    return {"symbol": ticker, "price": price, "currency": currency, "name": name,
            "fetched_at": now_utc().isoformat()}


@app.get("/api/market/search")
async def market_search(q: str, user=Depends(get_current_user)):
    key = q.strip().lower()
    cached = await db.market_search.find_one({"_id": key})
    if cached and (now_utc() - datetime.fromisoformat(cached["fetched_at"])).total_seconds() < 300:
        return {"results": cached["results"]}
    try:
        results = await asyncio.to_thread(market_search_sync, q)
    except Exception:
        raise HTTPException(502, "Market search unavailable")
    await db.market_search.replace_one({"_id": key},
        {"_id": key, "results": results, "fetched_at": now_utc().isoformat()}, upsert=True)
    return {"results": results}


@app.get("/api/market/quote/{ticker}")
async def market_quote(ticker: str, user=Depends(get_current_user)):
    ticker = ticker.strip().upper()
    if not ticker or len(ticker) > 32 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^=" for c in ticker):
        raise HTTPException(400, "Invalid ticker")
    cached = await db.market_quotes.find_one({"_id": ticker})
    if cached and (now_utc() - datetime.fromisoformat(cached["fetched_at"])).total_seconds() < 300:
        return doc_out(cached)
    try:
        result = await asyncio.to_thread(market_quote_sync, ticker)
    except ValueError:
        raise HTTPException(404, "Quote not found")
    except Exception:
        if cached:
            return doc_out(cached)
        raise HTTPException(502, "Quote provider unavailable")
    await db.market_quotes.replace_one({"_id": ticker}, {"_id": ticker, **result}, upsert=True)
    return result


# ---------------- etoro sync ----------------

ETORO_BASE = "https://public-api.etoro.com/api/v1"


async def etoro_get(path: str, params: dict = None) -> dict:
    import uuid
    import random
    api_key = os.environ.get("ETORO_API_KEY")
    user_key = os.environ.get("ETORO_USER_KEY")
    if not api_key or not user_key:
        raise HTTPException(503, "eToro API keys not configured")
    headers = {"x-api-key": api_key, "x-user-key": user_key,
               "x-request-id": str(uuid.uuid4()), "Accept": "application/json"}
    async with httpx.AsyncClient(base_url=ETORO_BASE, timeout=20) as client:
        for attempt in range(4):
            r = await client.get(path, params=params, headers=headers)
            if r.status_code == 429:
                retry = float(r.headers.get("Retry-After", min(2 ** attempt, 30)))
                await asyncio.sleep(retry + random.random())
                continue
            if r.status_code in (401, 403):
                raise HTTPException(502, f"eToro rejected the API keys ({r.status_code}) — check key permissions/environment")
            if r.status_code != 200:
                raise HTTPException(502, f"eToro API error {r.status_code}: {r.text[:200]}")
            return r.json()
    raise HTTPException(502, "eToro rate limit exceeded — try again in a minute")


async def etoro_instrument_meta(ids: list) -> dict:
    if not ids:
        return {}
    cached = {}
    async for d in db.etoro_instruments.find({"_id": {"$in": ids}}):
        cached[d["_id"]] = {"symbol": d.get("symbol"), "name": d.get("name"), "asset_type": d.get("asset_type")}
    missing = [i for i in ids if i not in cached]
    if missing:
        try:
            data = await etoro_get("/market-data/instruments", {"instrumentIds": ",".join(map(str, missing))})
        except HTTPException:
            data = {}
        for it in (data.get("instrumentDisplayDatas") or data.get("instruments") or data.get("items") or []):
            iid = it.get("instrumentID") or it.get("instrumentId")
            if iid is None:
                continue
            iid = int(iid)
            tid = it.get("instrumentTypeID")
            tname = str(it.get("instrumentTypeName") or it.get("type") or "").lower()
            asset = ("crypto" if tid == 10 or "crypto" in tname
                     else "stock" if tid == 5 or "stock" in tname or "etf" in tname
                     else "unknown")
            symbol = it.get("symbolFull") or it.get("internalSymbolFull") or it.get("symbol") or str(iid)
            name = it.get("instrumentDisplayName") or it.get("displayName") or symbol
            cached[iid] = {"symbol": symbol, "name": name, "asset_type": asset}
            await db.etoro_instruments.update_one({"_id": iid},
                {"$set": {"symbol": symbol, "name": name, "asset_type": asset,
                          "fetched_at": now_utc().isoformat()}}, upsert=True)
    return cached


@app.post("/api/integrations/etoro/sync")
async def etoro_sync(user=Depends(get_current_user)):
    portfolio = await etoro_get("/trading/info/portfolio")
    pnl_data = await etoro_get("/trading/info/real/pnl")
    pnl_by_id = {}
    for pp in ((pnl_data.get("clientPortfolio") or pnl_data).get("positions", []) or []):
        ppid = pp.get("positionID") or pp.get("positionId")
        upl = pp.get("unrealizedPnL") or {}
        if ppid is not None and upl.get("pnL") is not None:
            pnl_by_id[str(ppid)] = upl["pnL"]
    raw = (portfolio.get("clientPortfolio") or portfolio).get("positions", []) or []
    ids = sorted({int(p.get("instrumentID") or p.get("instrumentId")) for p in raw
                  if (p.get("instrumentID") or p.get("instrumentId")) is not None})
    rates_by_id = {}
    for i in range(0, len(ids), 100):
        rd = await etoro_get("/market-data/instruments/rates",
                             {"instrumentIds": ",".join(map(str, ids[i:i + 100]))})
        for x in rd.get("rates", []):
            iid = x.get("instrumentID") or x.get("instrumentId")
            if iid is not None:
                rates_by_id[int(iid)] = x
    meta = await etoro_instrument_meta(ids)
    warnings = []
    seen = []
    now = now_utc().isoformat()
    for p in raw:
        iid = p.get("instrumentID") or p.get("instrumentId")
        if iid is None:
            continue
        iid = int(iid)
        pid = str(p.get("positionID") or p.get("positionId") or f"{iid}-{p.get('openDateTime', '')}")
        m = meta.get(iid, {})
        symbol = m.get("symbol") or f"ETORO-{iid}"
        asset = m.get("asset_type") or "unknown"
        rate = rates_by_id.get(iid, {})
        price = rate.get("lastExecution") or rate.get("ask") or rate.get("bid") or 0
        qty = p.get("units") or p.get("initialUnits") or 0
        is_buy = p.get("isBuy", True)
        invested = p.get("initialAmountInDollars") or p.get("amount") or 0
        # eToro positions are margined CFDs: worth = invested + unrealized P&L
        # (NOT units x price — that's leveraged notional exposure)
        pnl = pnl_by_id.get(pid)
        if pnl is None:
            pnl = qty * ((price - (p.get("openRate") or 0)) * (1 if is_buy else -1))
        inv_type = {"stock": "shares", "crypto": "crypto"}.get(asset, "other")
        if asset == "unknown":
            warnings.append(f"Instrument {iid} type unmapped — stored under Other")
        doc = {
            "user_id": user["id"], "source": "etoro",
            "external_position_id": pid, "etoro_instrument_id": iid,
            "type": inv_type, "name": m.get("name") or symbol,
            "symbol": symbol if inv_type in ("shares", "crypto") else "",
            "currency": "USD", "price_currency": "USD",
            "quantity": qty, "current_price": price,
            "buy_price": p.get("openRate") or 0,
            "amount": invested, "pnl": round(pnl, 2), "is_buy": is_buy,
            "leverage": p.get("leverage") or 1, "date": str(p.get("openDateTime", ""))[:10],
            "notes": f"eToro position {pid}", "synced_at": now,
        }
        await db.investments.update_one(
            {"user_id": user["id"], "source": "etoro", "external_position_id": pid},
            {"$set": doc}, upsert=True)
        seen.append(pid)
    await db.investments.delete_many({"user_id": user["id"], "source": "etoro",
                                      "external_position_id": {"$nin": seen}})
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"etoro_last_sync": now}})
    total_value = round((await db.investments.aggregate([
        {"$match": {"user_id": user["id"], "source": "etoro"}},
        {"$group": {"_id": None, "v": {"$sum": {"$add": ["$amount", {"$ifNull": ["$pnl", 0]}]}}}}]).to_list(1) or [{}])[0].get("v", 0), 2)
    return {"synced": len(seen), "warnings": warnings, "synced_at": now, "total_value_usd": total_value}


# ---------------- shares privacy ----------------

class PinIn(BaseModel):
    pin: str


@app.post("/api/shares/unlock")
async def unlock_shares(data: PinIn, response: Response, request: Request, user=Depends(get_current_user)):
    if data.pin != os.environ.get("SHARES_PIN", "2468"):
        raise HTTPException(403, "Incorrect passcode")
    token = jwt.encode({"sub": user["id"], "type": "shares_unlock",
                        "exp": now_utc() + timedelta(hours=12)},
                       get_jwt_secret(), algorithm=JWT_ALGORITHM)
    response.set_cookie("shares_unlock", token, httponly=True, secure=True,
                        samesite="none", max_age=43200, path="/")
    return {"ok": True}


def shares_visible(request: Request) -> bool:
    token = request.cookies.get("shares_unlock")
    if not token:
        return False
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM]).get("type") == "shares_unlock"
    except jwt.InvalidTokenError:
        return False


# ---------------- dashboard ----------------

def investment_native(inv):
    if inv.get("source") == "etoro":
        # margined CFD positions: invested + unrealized P&L (not units x price)
        pnl = inv.get("pnl")
        if pnl is None:
            sign = 1 if inv.get("is_buy", True) else -1
            pnl = (inv.get("quantity") or 0) * ((inv.get("current_price") or 0) - (inv.get("buy_price") or 0)) * sign
        return round((inv.get("amount") or 0) + pnl, 2), \
            (inv.get("price_currency") or inv.get("currency", "AUD"))
    if inv.get("type") in ("shares", "crypto") and inv.get("symbol"):
        return round((inv.get("quantity") or 0) * (inv.get("current_price") or 0), 2), \
            (inv.get("price_currency") or inv.get("currency", "AUD"))
    return inv.get("amount", 0), inv.get("currency", "AUD")


def investment_worth_aud(inv, rates):
    if inv.get("source") == "etoro":
        nv, cur = investment_native(inv)
        return to_aud(nv, cur, rates)
    if inv.get("type") in ("shares", "crypto") and inv.get("symbol") and inv.get("quantity") and inv.get("current_price"):
        return to_aud(inv["quantity"] * inv["current_price"],
                      inv.get("price_currency") or inv.get("currency", "AUD"), rates)
    return to_aud(inv.get("amount", 0), inv.get("currency", "AUD"), rates)


async def _dashboard_data(request: Request, user: dict) -> dict:
    rates_data = await rate_service.get()
    rates = rates_data["rates"]
    my_name = user.get("partner_name") or user.get("name") or "Yash"

    investments = [doc_out(d) async for d in db.investments.find({"user_id": user["id"]})]
    worths = [investment_worth_aud(i, rates) for i in investments]
    inv_total = sum(worths)
    inv_by_type = {}
    for i, w in zip(investments, worths):
        inv_by_type[i["type"]] = inv_by_type.get(i["type"], 0) + w
    shares_count = sum(1 for i in investments if i.get("type") in ("shares", "crypto"))
    visible = shares_visible(request)
    if visible:
        shares_total = inv_by_type.get("shares", 0) + inv_by_type.get("crypto", 0)
    else:
        shares_total = 0
        inv_total -= sum(w for i, w in zip(investments, worths) if i.get("type") in ("shares", "crypto"))
        inv_by_type.pop("shares", None)
        inv_by_type.pop("crypto", None)

    properties = [doc_out(d) async for d in db.properties.find(
        {"$or": [{"user_id": user["id"]}, {"partners.email": user["email"]}]})]
    prop_value_mine = 0.0
    prop_debt_mine = 0.0
    prop_rent = 0.0
    for p in properties:
        partners = p.get("partners", [])
        if partners:
            pct = next((pt.get("percentage", 0) for pt in partners
                        if (pt.get("name") or "").lower() == my_name.lower() or pt.get("email") == user["email"]), 0)
            share = pct / 100
        else:
            share = 1.0
        prop_value_mine += to_aud(p["current_value"], p.get("currency", "AUD"), rates) * share
        prop_debt_mine += to_aud(p["debt"], p.get("currency", "AUD"), rates) * share
        prop_rent += to_aud(p["monthly_rent"], p.get("currency", "AUD"), rates) * share

    projects = []
    my_contributions = 0.0
    loans_outstanding = 0.0
    my_equity_total = 0.0
    my_loan_share_total = 0.0
    async for p in db.projects.find({"user_id": user["id"]}):
        p = doc_out(p)
        pid = p["id"]
        my_pct = next((pt.get("percentage", 0) for pt in p.get("partners", []) if pt.get("name") == my_name), 0)
        contrib_mine = 0.0
        total_contrib = 0.0
        async for c in db.contributions.find({"project_id": pid}):
            total_contrib += c["amount"]
            if c.get("partner") == my_name:
                contrib_mine += c["amount"]
        total_costs = 0.0
        async for c in db.costs.find({"project_id": pid}):
            total_costs += c["amount"]
        drawn = 0.0
        outstanding = 0.0
        async for l in db.loans.find({"project_id": pid}):
            m = loan_metrics(l)
            drawn += m["drawn"]
            outstanding += m["outstanding"]
        project_cost = p.get("land_cost", 0) + p.get("stamp_duty", 0) + total_costs
        equity_total = project_cost - drawn if project_cost > 0 else total_contrib
        my_equity = equity_total * my_pct / 100
        my_loan_share = outstanding * my_pct / 100
        my_contributions += contrib_mine
        loans_outstanding += outstanding
        my_equity_total += my_equity
        my_loan_share_total += my_loan_share
        projects.append({"id": pid, "name": p["name"], "my_percentage": my_pct,
                         "my_contributions": contrib_mine, "my_equity": round(my_equity, 2),
                         "project_cost": project_cost,
                         "loan_outstanding": outstanding, "my_loan_share": round(my_loan_share, 2),
                         "final_profit": p.get("final_profit", 0)})

    pl_total = 0.0
    async for l in db.personal_loans.find({"user_id": user["id"]}):
        m = await personal_loan_metrics(l, user)
        pl_total += m["total_owed"]

    bal = await ledger_balances(user)
    ledger_net = bal["totals"].get(my_name, bal["totals"].get("Yash", 0.0))

    gross = inv_total + prop_value_mine + my_equity_total + ledger_net
    debts = prop_debt_mine + my_loan_share_total + pl_total
    net_worth = gross - debts
    return {
        "net_worth": round(net_worth, 2),
        "net_worth_without_debts": round(gross, 2),
        "debts": {"property_debt": round(prop_debt_mine, 2),
                  "project_loans": round(my_loan_share_total, 2),
                  "personal_loans": round(pl_total, 2), "total": round(debts, 2)},
        "investments": {"total": round(inv_total, 2), "by_type": inv_by_type,
                        "shares_total": round(shares_total, 2), "shares_count": shares_count},
        "properties": {"value": round(prop_value_mine, 2), "debt": round(prop_debt_mine, 2),
                       "equity": round(prop_value_mine - prop_debt_mine, 2), "monthly_rent": round(prop_rent, 2)},
        "projects": {"list": projects, "my_contributions": round(my_contributions, 2),
                     "loans_outstanding": round(loans_outstanding, 2),
                     "my_equity": round(my_equity_total, 2), "my_loan_share": round(my_loan_share_total, 2)},
        "ledger_net": round(ledger_net, 2),
        "rates": rates_data,
    }


@app.get("/api/dashboard")
async def dashboard(request: Request, user=Depends(get_current_user)):
    return await _dashboard_data(request, user)


@app.get("/api/report/networth")
async def networth_report(request: Request, user=Depends(get_current_user)):
    rates_data = await rate_service.get()
    rates = rates_data["rates"]
    my_name = user.get("partner_name") or user.get("name") or "Yash Sojitra"
    dash = await _dashboard_data(request, user)
    visible = shares_visible(request)

    investments = []
    async for i in db.investments.find({"user_id": user["id"]}):
        i = doc_out(i)
        if i.get("type") in ("shares", "crypto") and not visible:
            investments.append({"name": "Hidden holding", "type": "shares", "native": None,
                                "currency": "", "worth_aud": None, "redacted": True})
            continue
        nv, cur = investment_native(i)
        investments.append({"name": i["name"], "type": i["type"], "native": nv, "currency": cur,
                            "worth_aud": round(investment_worth_aud(i, rates), 2)})

    properties = []
    async for p in db.properties.find(
            {"$or": [{"user_id": user["id"]}, {"partners.email": user["email"]}]}):
        partners = p.get("partners", [])
        if partners:
            pct = next((pt.get("percentage", 0) for pt in partners
                        if (pt.get("name") or "").lower() == my_name.lower()
                        or pt.get("email") == user["email"]), 0)
        else:
            pct = 100
        cur = p.get("currency", "AUD")
        properties.append({"name": p["name"], "currency": cur, "value": p.get("current_value", 0),
                           "debt": p.get("debt", 0), "rent": p.get("monthly_rent", 0),
                           "my_percentage": pct,
                           "my_equity_aud": round(to_aud((p.get("current_value", 0) - p.get("debt", 0)) * pct / 100, cur, rates), 2)})

    loans = []
    async for l in db.personal_loans.find({"user_id": user["id"]}):
        l = doc_out(l)
        m = await personal_loan_metrics(l, user)
        loans.append({"lender": l["lender"], "amount": l["amount"], "type": l["type"],
                      "return_amount": m["return_amount"], "total_owed": m["total_owed"]})

    bal = await _ledger_balances_for(user["id"])
    personal = await _personal_pairs_for(user["id"])
    return {"generated_at": now_utc().isoformat(),
            "user": {"name": user.get("name"), "email": user["email"]},
            "base_currency": "AUD",
            "summary": {"net_worth": dash["net_worth"],
                        "net_worth_without_debts": dash["net_worth_without_debts"],
                        "debts": dash["debts"], "ledger_net": dash["ledger_net"]},
            "investments": investments, "properties": properties,
            "projects": dash["projects"]["list"], "private_loans": loans,
            "ledger": {"company": bal["totals"], "personal": personal},
            "rates": rates_data["rates"]}


# ---------------- google auth (emergent managed) ----------------

@app.post("/api/auth/google/session")
async def google_session(data: GoogleSessionIn, response: Response):
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": data.session_id})
    except Exception:
        raise HTTPException(502, "Auth provider unavailable")
    if r.status_code != 200:
        raise HTTPException(401, "Invalid session")
    profile = r.json()
    email = profile["email"].lower().strip()
    user = await db.users.find_one({"email": email})
    if not user:
        is_admin = email == os.environ["ADMIN_EMAIL"].lower()
        await db.users.insert_one({
            "email": email, "name": profile.get("name", ""),
            "picture": profile.get("picture", ""), "google_id": profile.get("id", ""),
            "role": "admin" if is_admin else "user",
            "status": "approved" if is_admin else "pending",
            "created_at": now_utc().isoformat()})
        user = await db.users.find_one({"email": email})
    else:
        await db.users.update_one({"_id": user["_id"]}, {"$set": {
            "google_id": profile.get("id", ""), "picture": profile.get("picture", ""),
            "name": user.get("name") or profile.get("name", "")}})
    uid = str(user["_id"])
    session_token = profile.get("session_token") or secrets.token_urlsafe(32)
    await db.user_sessions.insert_one({
        "user_id": uid, "session_token": session_token,
        "expires_at": (now_utc() + timedelta(days=7)).isoformat(),
        "created_at": now_utc().isoformat()})
    response.set_cookie("session_token", session_token, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")
    return {"id": uid, "email": email, "name": user.get("name") or profile.get("name", ""),
            "picture": profile.get("picture", ""), "role": user.get("role", "user"),
            "status": user.get("status", "pending")}


# ---------------- admin ----------------

@app.get("/api/admin/users")
async def admin_list_users(user=Depends(require_admin)):
    out = []
    async for u in db.users.find({}, {"password_hash": 0}).sort("created_at", -1):
        out.append(doc_out(u))
    return out


@app.post("/api/admin/users/{uid}/status")
async def admin_set_status(uid: str, data: StatusIn, user=Depends(require_admin)):
    if data.status not in ("approved", "pending", "rejected"):
        raise HTTPException(400, "Invalid status")
    res = await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"status": data.status}})
    if not res.matched_count:
        raise HTTPException(404, "User not found")
    return {"ok": True, "status": data.status}


@app.delete("/api/admin/users/{uid}")
async def admin_delete_user(uid: str, user=Depends(require_admin)):
    if uid == user["id"]:
        raise HTTPException(400, "Cannot delete your own account")
    await db.users.delete_one({"_id": ObjectId(uid)})
    for coll in ("projects", "contributions", "costs", "loans", "ledger",
                 "investments", "properties", "feasibility"):
        await db[coll].delete_many({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    return {"ok": True}


# ---------------- feasibility ----------------

def compute_feasibility(d: dict) -> dict:
    contingency = d["construction_cost"] * d.get("contingency_pct", 0) / 100
    total_cost = (d["land_cost"] + d["stamp_duty"] + d["acquisition_legal"]
                  + d["council_permits"] + d["design_architect"] + d["engineering"]
                  + d["surveying"] + d["project_management"] + d["demolition"] + d["site_works"]
                  + d["construction_cost"] + contingency + d["holding_costs"] + d["finance_interest"]
                  + d["bond"] + d["marketing"] + d["agent_fees"] + d["legal"] + d["other_costs"])
    revenue = d["expected_revenue"]
    profit = revenue - total_cost
    margin = profit / revenue * 100 if revenue > 0 else 0
    cash_in = total_cost - d.get("loan_amount", 0)
    roi_cash = profit / cash_in * 100 if cash_in > 0 else 0
    roi_cost = profit / total_cost * 100 if total_cost > 0 else 0
    return {"contingency_amount": round(contingency, 2), "total_cost": round(total_cost, 2),
            "cash_in": round(cash_in, 2), "profit": round(profit, 2),
            "margin_pct": round(margin, 1), "roi_pct": round(roi_cost, 1),
            "roi_cash_pct": round(roi_cash, 1),
            "feasible": profit > 0 and roi_cash >= 50}


@app.get("/api/feasibility")
async def list_feasibility(user=Depends(get_current_user)):
    return [doc_out(d) async for d in db.feasibility.find({"user_id": user["id"]}).sort("created_at", -1)]


@app.post("/api/feasibility")
async def add_feasibility(data: FeasibilityIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    doc["computed"] = compute_feasibility(doc)
    doc["user_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    res = await db.feasibility.insert_one(doc)
    return doc_out(await db.feasibility.find_one({"_id": res.inserted_id}))


@app.put("/api/feasibility/{fid}")
async def update_feasibility(fid: str, data: FeasibilityIn, user=Depends(get_current_user)):
    existing = await db.feasibility.find_one({"_id": ObjectId(fid), "user_id": user["id"]})
    if not existing:
        raise HTTPException(404, "Study not found")
    doc = data.model_dump()
    doc["computed"] = compute_feasibility(doc)
    await db.feasibility.update_one({"_id": ObjectId(fid)}, {"$set": doc})
    return doc_out(await db.feasibility.find_one({"_id": ObjectId(fid)}))


@app.delete("/api/feasibility/{fid}")
async def delete_feasibility(fid: str, user=Depends(get_current_user)):
    res = await db.feasibility.delete_one({"_id": ObjectId(fid), "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Study not found")
    return {"ok": True}


# ---------------- startup ----------------

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.user_sessions.create_index("session_token")
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Yash", "role": "admin", "status": "approved",
            "created_at": now_utc().isoformat()})
        log.info("Admin user seeded: %s", admin_email)
    else:
        updates = {}
        if not verify_password(admin_password, existing.get("password_hash", "")):
            updates["password_hash"] = hash_password(admin_password)
        if existing.get("role") != "admin" or existing.get("status") != "approved":
            updates["role"] = "admin"
            updates["status"] = "approved"
        if updates:
            await db.users.update_one({"email": admin_email}, {"$set": updates})
    admin = await db.users.find_one({"email": admin_email})
    admin_id = str(admin["_id"])
    for coll in ("projects", "contributions", "costs", "loans", "ledger",
                 "investments", "properties", "feasibility"):
        await db[coll].update_many({"user_id": {"$exists": False}},
                                   {"$set": {"user_id": admin_id}})
    # one-time name migration: short names -> full names
    RENAME = {"Yash": "Yash Sojitra", "Sanjay": "Sanjay Jogani",
              "Pranay": "Pranay Jetani", "Max": "Max Ma"}
    for coll, fields in (("ledger", ["from_partner", "to_partner"]),
                         ("contributions", ["partner"]),
                         ("costs", ["paid_by"]),
                         ("personal_loans", ["lender"]),
                         ("people", ["name"])):
        for old, new in RENAME.items():
            for f in fields:
                await db[coll].update_many({f: old}, {"$set": {f: new}})
    for coll in ("projects", "properties"):
        async for doc in db[coll].find({"partners.name": {"$in": list(RENAME)}}):
            for pt in doc.get("partners", []):
                if pt.get("name") in RENAME:
                    pt["name"] = RENAME[pt["name"]]
            await db[coll].update_one({"_id": doc["_id"]},
                                      {"$set": {"partners": doc["partners"]}})
    if admin.get("name") == "Yash":
        await db.users.update_one({"_id": admin["_id"]}, {"$set": {"name": "Yash Sojitra"}})
    await rate_service.refresh()
    asyncio.create_task(fx_loop())


@app.get("/api/health")
async def health():
    return {"ok": True}
