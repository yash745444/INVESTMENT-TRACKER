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
PARTNERS = ["Yash", "Sanjay", "Pranay", "Max"]
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
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(401, "Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(401, "User not found")
    user["id"] = str(user.pop("_id"))
    user.pop("password_hash", None)
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
    partners: List[dict] = []  # [{name, percentage}]


class ContributionIn(BaseModel):
    date: str
    partner: str
    amount: float
    description: Optional[str] = ""


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
    type: str  # paid_on_behalf | settlement
    from_partner: str  # payer (paid_on_behalf) / sender (settlement)
    to_partner: str    # beneficiary (paid_on_behalf) / receiver (settlement)
    amount: float
    project_id: Optional[str] = None
    project_name: Optional[str] = ""
    note: Optional[str] = ""


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
    return {"id": str(user["_id"]), "email": email, "name": user.get("name", "")}


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
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
    async for p in db.projects.find().sort("created_at", -1):
        pid = str(p["_id"])
        p = doc_out(p)
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
        p["totals"] = {"contributions": contrib, "costs": cost, "drawn": drawn,
                       "outstanding": outstanding, "monthly_repayment": monthly}
        out.append(p)
    return out


@app.post("/api/projects")
async def create_project(data: ProjectIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    total_pct = sum(p.get("percentage", 0) for p in doc["partners"])
    if doc["partners"] and abs(total_pct - 100) > 0.01:
        raise HTTPException(400, f"Partner percentages must sum to 100 (currently {total_pct})")
    doc["created_at"] = now_utc().isoformat()
    res = await db.projects.insert_one(doc)
    return doc_out(await db.projects.find_one({"_id": res.inserted_id}))


@app.get("/api/projects/{pid}")
async def get_project(pid: str, user=Depends(get_current_user)):
    p = await db.projects.find_one({"_id": ObjectId(pid)})
    if not p:
        raise HTTPException(404, "Project not found")
    return doc_out(p)


@app.put("/api/projects/{pid}")
async def update_project(pid: str, data: ProjectIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    total_pct = sum(p.get("percentage", 0) for p in doc["partners"])
    if doc["partners"] and abs(total_pct - 100) > 0.01:
        raise HTTPException(400, f"Partner percentages must sum to 100 (currently {total_pct})")
    await db.projects.update_one({"_id": ObjectId(pid)}, {"$set": doc})
    return doc_out(await db.projects.find_one({"_id": ObjectId(pid)}))


@app.delete("/api/projects/{pid}")
async def delete_project(pid: str, user=Depends(get_current_user)):
    await db.projects.delete_one({"_id": ObjectId(pid)})
    for coll in ("contributions", "costs", "loans"):
        await db[coll].delete_many({"project_id": pid})
    return {"ok": True}


# ---------------- contributions / costs ----------------

async def crud_list(coll, pid):
    out = []
    async for d in db[coll].find({"project_id": pid}).sort("date", -1):
        out.append(doc_out(d))
    return out


@app.get("/api/projects/{pid}/contributions")
async def list_contributions(pid: str, user=Depends(get_current_user)):
    return await crud_list("contributions", pid)


@app.post("/api/projects/{pid}/contributions")
async def add_contribution(pid: str, data: ContributionIn, user=Depends(get_current_user)):
    doc = data.model_dump(); doc["project_id"] = pid
    res = await db.contributions.insert_one(doc)
    return doc_out(await db.contributions.find_one({"_id": res.inserted_id}))


@app.delete("/api/contributions/{cid}")
async def delete_contribution(cid: str, user=Depends(get_current_user)):
    await db.contributions.delete_one({"_id": ObjectId(cid)})
    return {"ok": True}


@app.get("/api/projects/{pid}/costs")
async def list_costs(pid: str, user=Depends(get_current_user)):
    return await crud_list("costs", pid)


@app.post("/api/projects/{pid}/costs")
async def add_cost(pid: str, data: CostIn, user=Depends(get_current_user)):
    doc = data.model_dump(); doc["project_id"] = pid
    res = await db.costs.insert_one(doc)
    return doc_out(await db.costs.find_one({"_id": res.inserted_id}))


@app.delete("/api/costs/{cid}")
async def delete_cost(cid: str, user=Depends(get_current_user)):
    await db.costs.delete_one({"_id": ObjectId(cid)})
    return {"ok": True}


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
    out = []
    async for l in db.loans.find({"project_id": pid}):
        l = doc_out(l)
        l["metrics"] = loan_metrics(l)
        out.append(l)
    return out


@app.post("/api/projects/{pid}/loans")
async def add_loan(pid: str, data: LoanIn, user=Depends(get_current_user)):
    if data.type not in ("interest_only", "amortizing"):
        raise HTTPException(400, "type must be interest_only or amortizing")
    doc = data.model_dump(); doc["project_id"] = pid
    res = await db.loans.insert_one(doc)
    l = doc_out(await db.loans.find_one({"_id": res.inserted_id}))
    l["metrics"] = loan_metrics(l)
    return l


@app.put("/api/loans/{lid}")
async def update_loan(lid: str, data: LoanIn, user=Depends(get_current_user)):
    doc = data.model_dump()
    await db.loans.update_one({"_id": ObjectId(lid)}, {"$set": doc})
    l = doc_out(await db.loans.find_one({"_id": ObjectId(lid)}))
    l["metrics"] = loan_metrics(l)
    return l


@app.delete("/api/loans/{lid}")
async def delete_loan(lid: str, user=Depends(get_current_user)):
    await db.loans.delete_one({"_id": ObjectId(lid)})
    return {"ok": True}


@app.post("/api/loans/{lid}/drawdowns")
async def add_drawdown(lid: str, data: DrawdownIn, user=Depends(get_current_user)):
    await db.loans.update_one({"_id": ObjectId(lid)},
                              {"$push": {"drawdowns": data.model_dump()}})
    l = doc_out(await db.loans.find_one({"_id": ObjectId(lid)}))
    l["metrics"] = loan_metrics(l)
    return l


@app.get("/api/loans/{lid}/schedule")
async def loan_schedule(lid: str, months: int = 12, user=Depends(get_current_user)):
    loan = await db.loans.find_one({"_id": ObjectId(lid)})
    if not loan:
        raise HTTPException(404, "Loan not found")
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
    async for d in db.ledger.find().sort("date", -1):
        out.append(doc_out(d))
    return out


@app.post("/api/ledger")
async def add_ledger(data: LedgerIn, user=Depends(get_current_user)):
    if data.from_partner == data.to_partner:
        raise HTTPException(400, "Partners must be different")
    doc = data.model_dump()
    doc["created_at"] = now_utc().isoformat()
    res = await db.ledger.insert_one(doc)
    return doc_out(await db.ledger.find_one({"_id": res.inserted_id}))


@app.delete("/api/ledger/{tid}")
async def delete_ledger(tid: str, user=Depends(get_current_user)):
    await db.ledger.delete_one({"_id": ObjectId(tid)})
    return {"ok": True}


def pairwise_balances(txns) -> dict:
    net = {}
    for t in txns:
        a, b = t["from_partner"], t["to_partner"]
        amt = t["amount"]
        # positive net[a][b] means b owes a
        if t["type"] == "paid_on_behalf":
            net.setdefault(a, {}).setdefault(b, 0.0)
            net[a][b] += amt
        else:  # settlement: money actually moved from a to b, reducing what b owes a
            net.setdefault(b, {}).setdefault(a, 0.0)
            net[b][a] -= amt
    return net


@app.get("/api/ledger/balances")
async def ledger_balances(user=Depends(get_current_user)):
    txns = [t async for t in db.ledger.find()]
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
    totals = {p: 0.0 for p in PARTNERS}
    for pr in pairs:
        if pr["owes"]:
            debtor, creditor = pr["owes"].split(" owes ")
            totals[creditor] += pr["amount"]
            totals[debtor] -= pr["amount"]
    return {"pairs": pairs, "totals": {k: round(v, 2) for k, v in totals.items()}}


@app.get("/api/ledger/report")
async def ledger_report(user=Depends(get_current_user)):
    txns = [doc_out(t) async for t in db.ledger.find().sort("date", 1)]
    bal = await ledger_balances(user)
    return {"transactions": txns, "balances": bal, "partners": PARTNERS,
            "generated_at": now_utc().isoformat()}


# ---------------- investments ----------------

@app.get("/api/investments")
async def list_investments(request: Request, user=Depends(get_current_user)):
    visible = shares_visible(request)
    out = []
    async for d in db.investments.find().sort("created_at", -1):
        d = doc_out(d)
        if d.get("type") == "shares" and not visible:
            out.append({"id": d["id"], "type": "shares", "name": "Hidden holding", "symbol": "",
                        "quantity": 0, "leverage": 1, "current_price": 0, "price_currency": "",
                        "currency": "AUD", "amount": 0, "date": "", "notes": "", "redacted": True})
        else:
            out.append(d)
    return out


@app.post("/api/investments")
async def add_investment(data: InvestmentIn, user=Depends(get_current_user)):
    doc = data.model_dump(); doc["created_at"] = now_utc().isoformat()
    res = await db.investments.insert_one(doc)
    return doc_out(await db.investments.find_one({"_id": res.inserted_id}))


@app.put("/api/investments/{iid}")
async def update_investment(iid: str, data: InvestmentIn, user=Depends(get_current_user)):
    await db.investments.update_one({"_id": ObjectId(iid)}, {"$set": data.model_dump()})
    return doc_out(await db.investments.find_one({"_id": ObjectId(iid)}))


@app.delete("/api/investments/{iid}")
async def delete_investment(iid: str, user=Depends(get_current_user)):
    await db.investments.delete_one({"_id": ObjectId(iid)})
    return {"ok": True}


# ---------------- properties ----------------

@app.get("/api/properties")
async def list_properties(user=Depends(get_current_user)):
    return [doc_out(d) async for d in db.properties.find().sort("created_at", -1)]


@app.post("/api/properties")
async def add_property(data: PropertyIn, user=Depends(get_current_user)):
    doc = data.model_dump(); doc["created_at"] = now_utc().isoformat()
    res = await db.properties.insert_one(doc)
    return doc_out(await db.properties.find_one({"_id": res.inserted_id}))


@app.put("/api/properties/{pid}")
async def update_property(pid: str, data: PropertyIn, user=Depends(get_current_user)):
    await db.properties.update_one({"_id": ObjectId(pid)}, {"$set": data.model_dump()})
    return doc_out(await db.properties.find_one({"_id": ObjectId(pid)}))


@app.delete("/api/properties/{pid}")
async def delete_property(pid: str, user=Depends(get_current_user)):
    await db.properties.delete_one({"_id": ObjectId(pid)})
    return {"ok": True}


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

def investment_worth_aud(inv, rates):
    if inv.get("type") == "shares" and inv.get("symbol") and inv.get("quantity") and inv.get("current_price"):
        return to_aud(inv["quantity"] * inv["current_price"],
                      inv.get("price_currency") or inv.get("currency", "AUD"), rates)
    return to_aud(inv.get("amount", 0), inv.get("currency", "AUD"), rates)


@app.get("/api/dashboard")
async def dashboard(request: Request, user=Depends(get_current_user)):
    rates_data = await rate_service.get()
    rates = rates_data["rates"]

    investments = [doc_out(d) async for d in db.investments.find()]
    worths = [investment_worth_aud(i, rates) for i in investments]
    inv_total = sum(worths)
    inv_by_type = {}
    for i, w in zip(investments, worths):
        inv_by_type[i["type"]] = inv_by_type.get(i["type"], 0) + w
    shares_count = sum(1 for i in investments if i.get("type") == "shares")
    visible = shares_visible(request)
    if visible:
        shares_total = inv_by_type.get("shares", 0)
    else:
        shares_total = 0
        inv_total -= sum(w for i, w in zip(investments, worths) if i.get("type") == "shares")
        inv_by_type.pop("shares", None)

    properties = [doc_out(d) async for d in db.properties.find()]
    prop_value = sum(to_aud(p["current_value"], p.get("currency", "AUD"), rates) for p in properties)
    prop_debt = sum(to_aud(p["debt"], p.get("currency", "AUD"), rates) for p in properties)
    prop_rent = sum(to_aud(p["monthly_rent"], p.get("currency", "AUD"), rates) for p in properties)

    projects = []
    my_contributions = 0.0
    loans_outstanding = 0.0
    async for p in db.projects.find():
        p = doc_out(p)
        pid = p["id"]
        my_pct = next((pt.get("percentage", 0) for pt in p.get("partners", []) if pt.get("name") == "Yash"), 0)
        contrib = 0.0
        async for c in db.contributions.find({"project_id": pid, "partner": "Yash"}):
            contrib += c["amount"]
        outstanding = 0.0
        async for l in db.loans.find({"project_id": pid}):
            outstanding += loan_metrics(l)["outstanding"]
        my_contributions += contrib
        loans_outstanding += outstanding
        projects.append({"id": pid, "name": p["name"], "my_percentage": my_pct,
                         "my_contributions": contrib, "loan_outstanding": outstanding})

    bal = await ledger_balances(user)
    ledger_net = bal["totals"].get("Yash", 0.0)

    net_worth = inv_total + (prop_value - prop_debt) + my_contributions + ledger_net
    return {
        "net_worth": round(net_worth, 2),
        "investments": {"total": round(inv_total, 2), "by_type": inv_by_type,
                        "shares_total": round(shares_total, 2), "shares_count": shares_count},
        "properties": {"value": round(prop_value, 2), "debt": round(prop_debt, 2),
                       "equity": round(prop_value - prop_debt, 2), "monthly_rent": round(prop_rent, 2)},
        "projects": {"list": projects, "my_contributions": round(my_contributions, 2),
                     "loans_outstanding": round(loans_outstanding, 2)},
        "ledger_net": round(ledger_net, 2),
        "rates": rates_data,
    }


# ---------------- startup ----------------

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Yash", "role": "admin", "created_at": now_utc().isoformat()})
        log.info("Admin user seeded: %s", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password)}})
    await rate_service.refresh()
    asyncio.create_task(fx_loop())


@app.get("/api/health")
async def health():
    return {"ok": True}
