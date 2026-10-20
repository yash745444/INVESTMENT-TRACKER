import { useEffect, useRef, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmt2, CURRENCIES } from "../lib/format";
import { DatePicker } from "../components/DatePicker";
import { PinUnlock } from "../components/PinUnlock";
import { isSharesUnlocked } from "../lib/sharesLock";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "../components/ui/hover-card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, Lock, RefreshCw, Search } from "lucide-react";

const TYPES = [
  { key: "shares", label: "Shares" },
  { key: "crypto", label: "Crypto" },
  { key: "term_insurance", label: "Term Insurance" },
  { key: "other", label: "Other Investments" },
];

const EMPTY = { type: "shares", name: "", currency: "AUD", amount: "", date: "", notes: "", symbol: "", quantity: "", leverage: 1, current_price: "", price_currency: "", buy_price: "", qty_mode: "quantity", invested_amount: "" };

export default function Investments() {
  const [items, setItems] = useState(null);
  const [rates, setRates] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [unlocked, setUnlocked] = useState(isSharesUnlocked());
  const [pinOpen, setPinOpen] = useState(false);
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const searchTimer = useRef(null);

  const load = async () => {
    const [i, r] = await Promise.all([api.get("/investments"), api.get("/rates")]);
    setItems(i.data); setRates(r.data.rates);
    if (i.data.some((x) => x.redacted)) setUnlocked(false); // server redacted → show lock UI
  };
  useEffect(() => { load(); }, []);

  const toAud = (amount, cur) => rates ? amount / (rates[cur] || 1) : 0;
  const isMarket = (i) => (i.type === "shares" || i.type === "crypto") && i.symbol;
  // eToro rows are margined CFDs: worth = invested + P&L, not qty x price (leveraged notional)
  const worthOf = (i) => i.source === "etoro"
    ? (Number(i.amount) || 0) + (i.pnl ?? (Number(i.quantity) || 0) * ((Number(i.current_price) || 0) - (Number(i.buy_price) || 0)) * (i.is_buy === false ? -1 : 1))
    : (isMarket(i) && i.quantity && i.current_price ? i.quantity * i.current_price : i.amount);
  const worthCur = (i) => (isMarket(i) || i.source === "etoro") ? (i.price_currency || i.currency) : i.currency;

  const submit = async (e) => {
    e.preventDefault();
    try {
      const qty = (form.type === "shares" || form.type === "crypto")
        ? (form.qty_mode === "amount" && Number(form.buy_price) > 0
            ? Number(form.invested_amount) / Number(form.buy_price)
            : Number(form.quantity) || 0)
        : 0;
      const payload = {
        ...form,
        amount: (form.type === "shares" || form.type === "crypto") && form.symbol
          ? qty * (Number(form.current_price) || 0)
          : Number(form.amount),
        quantity: qty,
        leverage: Number(form.leverage) || 1,
        current_price: Number(form.current_price) || 0,
        buy_price: Number(form.buy_price) || 0,
      };
      if (editing) await api.put(`/investments/${editing}`, payload);
      else await api.post("/investments", payload);
      toast.success(editing ? "Investment updated" : "Investment added");
      setOpen(false); setEditing(null); setForm(EMPTY);
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const totalAud = items?.reduce((s, i) => s + toAud(worthOf(i), worthCur(i)), 0) || 0;
  const sharesCount = items?.filter((i) => i.type === "shares" || i.type === "crypto").length || 0;
  const effectiveQty = form.qty_mode === "amount" && Number(form.buy_price) > 0
    ? (Number(form.invested_amount) || 0) / Number(form.buy_price)
    : Number(form.quantity) || 0;

  const onSearchChange = (v) => {
    setSearchQ(v);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!v.trim()) { setSearchResults([]); return; }
    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.get("/market/search", { params: { q: v } });
        setSearchResults(r.data.results);
      } catch { setSearchResults([]); }
      setSearching(false);
    }, 400);
  };

  const selectShare = async (s) => {
    setSearchResults([]);
    setSearchQ(`${s.symbol} — ${s.name}`);
    try {
      const r = await api.get(`/market/quote/${encodeURIComponent(s.symbol)}`);
      setForm((f) => ({ ...f, symbol: s.symbol, name: f.name || r.data.name || s.name,
        current_price: r.data.price, price_currency: r.data.currency || f.currency,
        currency: r.data.currency || f.currency }));
      toast.success(`Price fetched: ${r.data.price} ${r.data.currency}`);
    } catch (err) { toast.error(apiError(err)); }
  };

  const refreshPrices = async () => {
    const shares = (items || []).filter((i) => i.type === "shares" && i.symbol && i.source !== "etoro");
    let ok = 0;
    for (const s of shares) {
      try {
        const r = await api.get(`/market/quote/${encodeURIComponent(s.symbol)}`);
        await api.put(`/investments/${s.id}`, { ...s, current_price: r.data.price, price_currency: r.data.currency || s.price_currency });
        ok++;
      } catch {}
    }
    toast.success(`Updated ${ok}/${shares.length} prices`);
    load();
  };

  const syncEtoro = async () => {
    setSyncing(true);
    try {
      const r = await api.post("/integrations/etoro/sync");
      toast.success(`Synced ${r.data.synced} eToro position${r.data.synced === 1 ? "" : "s"} — total value $${(r.data.total_value_usd ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })} USD`);
      (r.data.warnings || []).forEach((w) => toast.warning(w));
      load();
    } catch (err) { toast.error(apiError(err)); }
    setSyncing(false);
  };

  return (
    <div className="space-y-6" data-testid="investments-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Personal Investments</h1>
          <p className="text-sm text-muted-foreground mt-1 font-mono" data-testid="investments-total">
            Total: {fmt(totalAud)} AUD{!unlocked && sharesCount > 0 ? " (shares hidden)" : ""}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" data-testid="etoro-sync-button" disabled={syncing} onClick={syncEtoro}>
            <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Syncing…" : "Sync eToro"}
          </Button>
          {!unlocked && sharesCount > 0 && (
            <Button variant="outline" data-testid="unlock-shares-inv-button" onClick={() => setPinOpen(true)}>
              <Lock className="h-4 w-4 mr-1.5" /> Reveal Shares
            </Button>
          )}
          {unlocked && sharesCount > 0 && (
            <Button variant="outline" data-testid="refresh-prices-button" onClick={refreshPrices}>
              <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh Prices
            </Button>
          )}
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(EMPTY); setSearchQ(""); setSearchResults([]); } }}>
          <DialogTrigger asChild><Button data-testid="add-investment-button"><Plus className="h-4 w-4 mr-1.5" /> Add Investment</Button></DialogTrigger>
          <DialogContent data-testid="investment-dialog">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Investment</DialogTitle></DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                    <SelectTrigger data-testid="inv-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{TYPES.map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}</SelectContent>
                  </Select></div>
                {form.type === "shares" || form.type === "crypto" ? (
                  <div className="space-y-1.5"><Label>Leverage</Label>
                    <Select value={String(form.leverage)} onValueChange={(v) => setForm({ ...form, leverage: Number(v) })}>
                      <SelectTrigger data-testid="inv-leverage-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">1× (no leverage)</SelectItem>
                        <SelectItem value="2">2×</SelectItem>
                        <SelectItem value="5">5×</SelectItem>
                      </SelectContent>
                    </Select></div>
                ) : (
                  <div className="space-y-1.5"><Label>Currency</Label>
                    <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v })}>
                      <SelectTrigger data-testid="inv-currency-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select></div>
                )}
              </div>

              {(form.type === "shares" || form.type === "crypto") && (
                <div className="space-y-1.5 relative">
                  <Label>Search market</Label>
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input data-testid="inv-search-input" className="pl-8" value={searchQ}
                      onChange={(e) => onSearchChange(e.target.value)}
                      placeholder="Search e.g. Apple, BHP, Reliance…" />
                  </div>
                  {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
                  {searchResults.length > 0 && (
                    <div className="absolute z-20 mt-1 w-full rounded-lg border border-border bg-popover shadow-lg max-h-52 overflow-y-auto" data-testid="inv-search-results">
                      {searchResults.map((s) => (
                        <button type="button" key={s.symbol} data-testid={`inv-search-result-${s.symbol}`}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-secondary transition-colors flex justify-between gap-2"
                          onClick={() => selectShare(s)}>
                          <span className="truncate">{s.name}</span>
                          <span className="font-mono text-xs text-muted-foreground shrink-0">{s.symbol} · {s.exchange}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="space-y-1.5"><Label>Name</Label>
                <Input data-testid="inv-name-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Apple shares / TAL Term Life" /></div>

              {form.type === "shares" || form.type === "crypto" ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5"><Label>Buy price / unit</Label>
                      <Input data-testid="inv-buy-price-input" type="number" step="any" value={form.buy_price}
                        onChange={(e) => setForm({ ...form, buy_price: e.target.value })} placeholder="What you paid" /></div>
                    <div className="space-y-1.5"><Label>Input mode</Label>
                      <Select value={form.qty_mode} onValueChange={(v) => setForm({ ...form, qty_mode: v })}>
                        <SelectTrigger data-testid="inv-qty-mode-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="quantity">By quantity</SelectItem>
                          <SelectItem value="amount">By total amount</SelectItem>
                        </SelectContent>
                      </Select></div>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    {form.qty_mode === "quantity" ? (
                      <div className="space-y-1.5"><Label>Quantity (fractions ok)</Label>
                        <Input data-testid="inv-quantity-input" type="number" step="any" required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></div>
                    ) : (
                      <div className="space-y-1.5"><Label>Total invested</Label>
                        <Input data-testid="inv-invested-input" type="number" step="any" required value={form.invested_amount} onChange={(e) => setForm({ ...form, invested_amount: e.target.value })} /></div>
                    )}
                    <div className="space-y-1.5"><Label>Current price</Label>
                      <Input data-testid="inv-price-input" type="number" step="any" required value={form.current_price} onChange={(e) => setForm({ ...form, current_price: e.target.value })} /></div>
                    <div className="space-y-1.5"><Label>Currency</Label>
                      <Select value={form.price_currency || form.currency} onValueChange={(v) => setForm({ ...form, price_currency: v, currency: v })}>
                        <SelectTrigger data-testid="inv-price-currency-select"><SelectValue /></SelectTrigger>
                        <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                      </Select></div>
                  </div>
                  {form.qty_mode === "amount" && Number(form.invested_amount) > 0 && Number(form.buy_price) > 0 && (
                    <p className="text-xs font-mono text-muted-foreground" data-testid="inv-qty-preview">
                      = {((Number(form.invested_amount) || 0) / Number(form.buy_price)).toFixed(4)} shares
                    </p>
                  )}
                </div>
              ) : (
                <div className="space-y-1.5"><Label>Current value</Label>
                  <Input data-testid="inv-amount-input" type="number" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
              )}
              <div className="space-y-1.5"><Label>Date</Label>
                <DatePicker testid="inv-date-input" value={form.date} onChange={(v) => setForm({ ...form, date: v })} /></div>
              {(form.type === "shares" || form.type === "crypto") && effectiveQty > 0 && Number(form.current_price) > 0 ? (
                <p className="text-xs font-mono text-muted-foreground" data-testid="inv-worth-preview">
                  Worth: {fmt2(effectiveQty * Number(form.current_price), form.price_currency || form.currency)}
                  {Number(form.leverage) > 1 && ` · Exposure ×${form.leverage}: ${fmt2(effectiveQty * Number(form.current_price) * form.leverage, form.price_currency || form.currency)}`}
                </p>
              ) : null}
              <div className="space-y-1.5"><Label>Notes</Label>
                <Input data-testid="inv-notes-input" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
              <Button data-testid="inv-submit" type="submit" className="w-full">Save</Button>
            </form>
          </DialogContent>
        </Dialog>
        </div>
      </div>

      <PinUnlock open={pinOpen} onOpenChange={setPinOpen} onUnlock={() => { setUnlocked(true); load(); }} />

      {!items ? <p className="text-muted-foreground">Loading…</p> : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {TYPES.map((t) => {
            const group = items.filter((i) => i.type === t.key);
            const groupTotal = group.reduce((s, i) => s + toAud(worthOf(i), worthCur(i)), 0);
            const masked = (t.key === "shares" || t.key === "crypto") && !unlocked;
            return (
              <Card key={t.key} data-testid={`inv-group-${t.key}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="font-heading text-lg flex items-center gap-2">{t.label}{masked && <Lock className="h-3.5 w-3.5 text-muted-foreground" />}</CardTitle>
                    <span className="font-mono text-sm font-semibold" data-testid={`inv-group-total-${t.key}`}>{masked ? "••••" : fmt(groupTotal)}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {group.length === 0 && <p className="text-sm text-muted-foreground">None yet.</p>}
                  {masked && group.length > 0 && (
                    <button data-testid="shares-masked-button" onClick={() => setPinOpen(true)}
                      className="w-full text-left text-sm text-muted-foreground flex items-center gap-2 py-2">
                      <Lock className="h-3.5 w-3.5" /> {group.length} holding{group.length > 1 ? "s" : ""} hidden — enter passcode to view
                    </button>
                  )}
                  {!masked && group.map((i) => (
                    <HoverCard key={i.id} openDelay={150}>
                      <HoverCardTrigger asChild>
                        <div className="flex items-start justify-between gap-2 border-b border-border/50 pb-3 last:border-0 last:pb-0 cursor-pointer"
                          data-testid={`inv-row-${i.id}`}>
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">
                              {i.name}
                              {i.source === "etoro" && (
                                <span className="ml-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded border text-gold" style={{ borderColor: "hsl(var(--gold))" }} data-testid={`etoro-badge-${i.id}`}>eToro</span>
                              )}
                              {i.type === "shares" && Number(i.leverage) > 1 && (
                                <span className="ml-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded border text-gold" style={{ borderColor: "hsl(var(--gold))" }}>×{i.leverage}</span>
                              )}
                            </p>
                            <p className="font-mono text-xs text-muted-foreground mt-0.5">
                              {i.redacted ? "••••"
                                : (i.type === "shares" || i.type === "crypto") && i.symbol
                                ? (i.source === "etoro"
                                  ? `${i.symbol} · invested ${fmt2(i.amount, worthCur(i))} · P&L ${(i.pnl ?? 0) >= 0 ? "+" : ""}${fmt2(i.pnl ?? 0, worthCur(i))} (${i.amount ? (((i.pnl ?? 0) / i.amount) * 100).toFixed(1) : "0.0"}%) = ${fmt2(worthOf(i), worthCur(i))}${worthCur(i) !== "AUD" ? ` ≈ ${fmt(toAud(worthOf(i), worthCur(i)))}` : ""}`
                                  : `${i.symbol} · ${Number(i.quantity).toFixed(4).replace(/\.?0+$/, "")} × ${fmt2(i.current_price, i.price_currency || i.currency)} = ${fmt2(worthOf(i), worthCur(i))}${worthCur(i) !== "AUD" ? ` ≈ ${fmt(toAud(worthOf(i), worthCur(i)))}` : ""}${i.buy_price ? ` · P&L ${(((i.current_price - i.buy_price) / i.buy_price) * 100).toFixed(1)}%` : ""}`)
                                : `${fmt2(i.amount, i.currency)}${i.currency !== "AUD" ? ` ≈ ${fmt(toAud(i.amount, i.currency))}` : ""}`}
                            </p>
                          </div>
                          <div className="flex shrink-0">
                            <Button variant="ghost" size="icon" data-testid={`edit-inv-${i.id}`}
                              onClick={() => { setEditing(i.id); setForm({ ...EMPTY, ...i }); setSearchQ(i.symbol || ""); setOpen(true); }}>
                              <Pencil className="h-3.5 w-3.5" /></Button>
                            <Button variant="ghost" size="icon" data-testid={`delete-inv-${i.id}`}
                              onClick={async () => { await api.delete(`/investments/${i.id}`); toast.success("Deleted"); load(); }}>
                              <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                          </div>
                        </div>
                      </HoverCardTrigger>
                      <HoverCardContent className="w-64 rounded-lg border border-border bg-popover p-4" data-testid={`inv-hover-${i.id}`}>
                        <p className="label-overline">Current worth</p>
                        <p className="font-mono font-semibold text-lg mt-1">{fmt2(worthOf(i), worthCur(i))}</p>
                        {worthCur(i) !== "AUD" && <p className="font-mono text-xs text-muted-foreground">≈ {fmt(toAud(worthOf(i), worthCur(i)))} AUD</p>}
                        {i.type === "shares" && Number(i.leverage) > 1 && (
                          <p className="font-mono text-xs text-gold mt-1">Exposure ×{i.leverage}: {fmt2(worthOf(i) * i.leverage, worthCur(i))}</p>
                        )}
                      </HoverCardContent>
                    </HoverCard>
                  ))}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
