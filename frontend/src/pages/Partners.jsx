import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { fmt, fmt2, fmtDate, today, PARTNERS } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, FileText, Pencil } from "lucide-react";
import { DatePicker } from "../components/DatePicker";

export default function Partners() {
  const [txns, setTxns] = useState(null);
  const [balances, setBalances] = useState(null);
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState(null);
  const [form, setForm] = useState({
    date: today(), type: "paid_on_behalf", from_partner: "Yash Sojitra", to_partner: "Sanjay Jogani",
    amount: "", project_id: "", note: "", lender_name: "",
  });
  const [personal, setPersonal] = useState([]);
  const [pOpen, setPOpen] = useState(false);
  const [pEditing, setPEditing] = useState(null);
  const [pForm, setPForm] = useState({ person: "", direction: "i_paid", amount: "", date: today(), note: "" });
  const { user } = useAuth();
  const [overview, setOverview] = useState(null);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [people, setPeople] = useState([]);

  const load = async () => {
    const [t, b, p, pd, ov] = await Promise.all([
      api.get("/ledger"), api.get("/ledger/balances"), api.get("/projects"), api.get("/ledger/personal"), api.get("/partner/overview"),
    ]);
    setTxns(t.data); setBalances(b.data); setProjects(p.data); setPersonal(pd.data.pairs); setOverview(ov.data);
    api.get("/people").then((r) => setPeople(r.data)).catch(() => setPeople([]));
  };

  const personOptions = [...PARTNERS, ...people.map((p) => p.name).filter((n) => !PARTNERS.includes(n))];
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const proj = projects.find((p) => p.id === form.project_id);
      const payload = {
        ...form,
        from_partner: form.type === "external" ? form.lender_name.trim() : form.from_partner,
        to_partner: form.type === "external" ? "Company" : form.to_partner,
        amount: Number(form.amount),
        project_id: form.project_id || null, project_name: proj?.name || "",
      };
      if (editing) await api.put(`/ledger/${editing}`, payload);
      else await api.post("/ledger", payload);
      toast.success(editing ? "Transaction updated" : "Transaction recorded");
      setOpen(false);
      setEditing(null);
      setForm({ ...form, amount: "", note: "" });
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const submitPersonal = async (e) => {
    e.preventDefault();
    try {
      const me = user?.name || "Yash";
      const other = pForm.person.trim();
      const payload = {
        date: pForm.date, type: "personal",
        from_partner: pForm.direction === "i_paid" ? me : other,
        to_partner: pForm.direction === "i_paid" ? other : me,
        amount: Number(pForm.amount), note: pForm.note,
      };
      if (pEditing) await api.put(`/ledger/${pEditing}`, payload);
      else await api.post("/ledger", payload);
      toast.success(pEditing ? "Personal debt updated" : "Personal debt recorded");
      setPOpen(false);
      setPEditing(null);
      setPForm({ person: "", direction: "i_paid", amount: "", date: today(), note: "" });
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const openReport = async () => {
    const r = await api.get("/ledger/report");
    setReport(r.data);
    setReportOpen(true);
  };

  const downloadReport = () => {
    if (!report) return;
    let txt = `PARTNER LEDGER REPORT — ${new Date().toLocaleDateString("en-AU")}\n`;
    txt += `Company partners: Yash, Sanjay, Pranay, Max\n\n== COMPANY SETTLEMENT ==\n`;
    Object.entries(report.balances.totals).forEach(([k, v]) => {
      txt += Math.abs(v) < 0.005 ? `${k}: settled\n` : v > 0 ? `${k}: Take from Company $${v.toFixed(2)}\n` : `${k}: Pay to Company $${(-v).toFixed(2)}\n`;
    });
    if (report.personal_transactions && report.personal_transactions.length) {
      txt += `\n== PERSONAL DEBTS (outside company pool) ==\n`;
      report.personal.pairs.forEach((p) => { txt += `${p.debtor} owes ${p.creditor}: $${p.amount.toFixed(2)}\n`; });
    }
    txt += `\n== ALL TRANSACTIONS ==\n`;
    report.transactions.forEach((t) => {
      txt += `${t.date} | ${t.type === "paid_on_behalf" ? `${t.from_partner} paid for ${t.to_partner}` : `${t.from_partner} paid ${t.to_partner}`} | $${t.amount.toFixed(2)}${t.project_name ? ` | ${t.project_name}` : ""}${t.note ? ` | ${t.note}` : ""}\n`;
    });
    const url = URL.createObjectURL(new Blob([txt], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url; a.download = "partner-ledger-report.txt"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6" data-testid="partners-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Partner Money Ledger</h1>
        {overview?.scope !== "self" && (
        <div className="flex gap-2">
          <Button variant="outline" data-testid="report-button" onClick={openReport}>
            <FileText className="h-4 w-4 mr-1.5" /> Report
          </Button>
          <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditing(null); }}>
            <DialogTrigger asChild><Button data-testid="add-transaction-button"><Plus className="h-4 w-4 mr-1.5" /> Add Transaction</Button></DialogTrigger>
            <DialogContent data-testid="add-transaction-dialog">
              <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Transaction</DialogTitle></DialogHeader>
              <form onSubmit={submit} className="space-y-4">
                <div className="space-y-1.5"><Label>Type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                    <SelectTrigger data-testid="txn-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="paid_on_behalf">Paid on behalf of partner</SelectItem>
                      <SelectItem value="settlement">Settle up (pay / take money)</SelectItem>
                      <SelectItem value="external">External lender paid (loan to company)</SelectItem>
                    </SelectContent>
                  </Select></div>
                {form.type === "external" ? (
                  <div className="space-y-1.5"><Label>Lender name</Label>
                    <Input data-testid="txn-lender-input" required value={form.lender_name}
                      onChange={(e) => setForm({ ...form, lender_name: e.target.value })} placeholder="e.g. ABC Capital" />
                    <p className="text-xs text-muted-foreground">Recorded as a loan to the company — to be repaid from the partners' pool.</p></div>
                ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>{form.type === "paid_on_behalf" ? "Paid by" : "From"}</Label>
                    <Select value={form.from_partner} onValueChange={(v) => setForm({ ...form, from_partner: v })}>
                      <SelectTrigger data-testid="txn-from-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{personOptions.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                    </Select></div>
                  <div className="space-y-1.5"><Label>{form.type === "paid_on_behalf" ? "On behalf of" : "To"}</Label>
                    <Select value={form.to_partner} onValueChange={(v) => setForm({ ...form, to_partner: v })}>
                      <SelectTrigger data-testid="txn-to-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{personOptions.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                    </Select></div>
                </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Date</Label>
                    <DatePicker testid="txn-date-input" value={form.date} onChange={(v) => setForm({ ...form, date: v })} /></div>
                  <div className="space-y-1.5"><Label>Amount (AUD)</Label>
                    <Input data-testid="txn-amount-input" type="number" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                </div>
                <div className="space-y-1.5"><Label>Project (optional)</Label>
                  <Select value={form.project_id} onValueChange={(v) => setForm({ ...form, project_id: v })}>
                    <SelectTrigger data-testid="txn-project-select"><SelectValue placeholder="None" /></SelectTrigger>
                    <SelectContent>
                      {projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                    </SelectContent>
                  </Select></div>
                <div className="space-y-1.5"><Label>Note</Label>
                  <Input data-testid="txn-note-input" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="e.g. Paid council fees for Sanjay" /></div>
                <Button data-testid="txn-submit" type="submit" className="w-full">{editing ? "Save Changes" : "Save Transaction"}</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
        )}
      </div>

      {overview?.scope === "self" ? (
        <PartnerSelfView overview={overview} />
      ) : (<>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {PARTNERS.map((p) => (
          <Card key={p} data-testid={`partner-total-${p.toLowerCase()}`}>
            <CardContent className="p-4">
              <p className="label-overline">{p}{p === user?.name ? " (You)" : ""}</p>
              <p className={`font-mono font-semibold text-lg mt-1.5 ${(balances?.totals[p] || 0) < 0 ? "text-negative" : "text-positive"}`}>
                {fmt(Math.abs(balances?.totals[p] || 0))}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {Math.abs(balances?.totals[p] || 0) < 0.005 ? "Settled" : (balances?.totals[p] || 0) >= 0 ? "Take from Company" : "Pay to Company"}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {overview?.scope === "all" && (
        <Card data-testid="partner-profiles-card">
          <CardHeader><CardTitle className="font-heading text-lg">Partner Profiles</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {overview.profiles.map((pr) => (
                <button key={pr.name} data-testid={`profile-card-${pr.name.toLowerCase()}`}
                  onClick={() => setSelectedProfile(pr)}
                  className="text-left rounded-lg border border-border p-4 space-y-2 card-hover">
                  <p className="font-heading font-semibold">{pr.name}{pr.name === user?.name && <span className="text-xs text-gold ml-1.5">(You)</span>}</p>
                  <p className="font-mono text-xs text-muted-foreground">{pr.projects.length} project{pr.projects.length !== 1 ? "s" : ""}</p>
                  <p className={`font-mono text-sm font-semibold ${pr.position < 0 ? "text-negative" : "text-positive"}`}>
                    {Math.abs(pr.position) < 0.005 ? "Settled" : pr.position > 0 ? `Take ${fmt(pr.position)}` : `Pay ${fmt(-pr.position)}`}
                  </p>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card data-testid="pairwise-card">
        <CardHeader><CardTitle className="font-heading text-lg">Company Settlement</CardTitle></CardHeader>
        <CardContent>
          {!balances ? <p className="text-sm text-muted-foreground">Loading…</p> : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {PARTNERS.map((p) => {
                const v = balances.totals[p] || 0;
                return (
                  <div key={p} className="flex items-center justify-between rounded-lg border border-border p-3.5 gap-2"
                    data-testid={`company-position-${p.toLowerCase()}`}>
                    <span className="text-sm font-medium shrink-0">{p}{p === user?.name ? " (You)" : ""}</span>
                    {Math.abs(v) < 0.005 ? (
                      <span className="font-mono text-xs text-positive">settled</span>
                    ) : v > 0 ? (
                      <span className="font-mono text-xs text-right"><span className="text-positive block">Take from Company</span><span className="text-gold font-semibold">{fmt2(v)}</span></span>
                    ) : (
                      <span className="font-mono text-xs text-right"><span className="text-negative block">Pay to Company</span><span className="text-gold font-semibold">{fmt2(-v)}</span></span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {balances && Object.entries(balances.totals).filter(([k]) => !PARTNERS.includes(k) && Math.abs(balances.totals[k]) > 0.005).length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-3" data-testid="external-lenders">
              {Object.entries(balances.totals).filter(([k]) => !PARTNERS.includes(k) && Math.abs(balances.totals[k]) > 0.005).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-lg border p-3.5 gap-2" style={{ borderColor: "hsl(var(--gold) / 0.5)" }}
                  data-testid={`external-${k.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
                  <span className="text-sm font-medium shrink-0">{k}</span>
                  <span className="font-mono text-xs text-right">
                    <span className={`block ${v >= 0 ? "text-positive" : "text-negative"}`}>{v >= 0 ? "Company owes them" : "They owe Company"}</span>
                    <span className="text-gold font-semibold">{fmt2(Math.abs(v))}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-3">The 4 partners operate as one company pool — settle with the company, not with each other.</p>
        </CardContent>
      </Card>
      </>)}

      <Card data-testid="personal-debts-card">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="font-heading text-lg">Personal Debts</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">Money paid for someone personally — outside the company pool, not tied to any project.</p>
          </div>
          <Dialog open={pOpen} onOpenChange={(v) => { setPOpen(v); if (!v) setPEditing(null); }}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" data-testid="add-personal-button"><Plus className="h-4 w-4 mr-1" /> Add Personal</Button>
            </DialogTrigger>
            <DialogContent data-testid="add-personal-dialog">
              <DialogHeader><DialogTitle className="font-heading">{pEditing ? "Edit" : "Add"} Personal Debt</DialogTitle></DialogHeader>
              <form onSubmit={submitPersonal} className="space-y-4">
                <div className="space-y-1.5"><Label>Direction</Label>
                  <Select value={pForm.direction} onValueChange={(v) => setPForm({ ...pForm, direction: v })}>
                    <SelectTrigger data-testid="personal-direction-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="i_paid">I paid for them (they owe me)</SelectItem>
                      <SelectItem value="they_paid">They paid for me (I owe them)</SelectItem>
                    </SelectContent>
                  </Select></div>
                <div className="space-y-1.5"><Label>Person</Label>
                  <Select value={personOptions.includes(pForm.person) ? pForm.person : (pForm.person ? "__custom" : "")}
                    onValueChange={(v) => setPForm({ ...pForm, person: v === "__custom" ? "" : v })}>
                    <SelectTrigger data-testid="personal-person-select"><SelectValue placeholder="Select person" /></SelectTrigger>
                    <SelectContent>
                      {personOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
                      <SelectItem value="__custom">Custom…</SelectItem>
                    </SelectContent>
                  </Select>
                  {!personOptions.includes(pForm.person) && (
                    <Input data-testid="personal-person-input" value={pForm.person}
                      onChange={(e) => setPForm({ ...pForm, person: e.target.value })} placeholder="Or type a name" />
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Date</Label>
                    <DatePicker testid="personal-date-input" value={pForm.date} onChange={(v) => setPForm({ ...pForm, date: v })} /></div>
                  <div className="space-y-1.5"><Label>Amount (AUD)</Label>
                    <Input data-testid="personal-amount-input" type="number" step="0.01" required value={pForm.amount}
                      onChange={(e) => setPForm({ ...pForm, amount: e.target.value })} /></div>
                </div>
                <div className="space-y-1.5"><Label>Note</Label>
                  <Input data-testid="personal-note-input" value={pForm.note}
                    onChange={(e) => setPForm({ ...pForm, note: e.target.value })} placeholder="e.g. Paid his car rego" /></div>
                <Button data-testid="personal-submit" type="submit" className="w-full">{pEditing ? "Save Changes" : "Save"}</Button>
              </form>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent className="space-y-4">
          {personal.length === 0 ? (
            <p className="text-sm text-muted-foreground">No personal debts recorded.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {personal.map((pr) => {
                const me = user?.name || "Yash";
                const label = pr.creditor === me ? `${pr.debtor} owes me`
                  : pr.debtor === me ? `I owe ${pr.creditor}` : `${pr.debtor} owes ${pr.creditor}`;
                return (
                  <div key={`${pr.debtor}-${pr.creditor}`} className="flex items-center justify-between rounded-lg border border-border p-3.5"
                    data-testid={`personal-debt-${pr.debtor.toLowerCase()}-${pr.creditor.toLowerCase()}`}>
                    <span className="text-sm font-medium">{label}</span>
                    <span className="font-mono text-sm text-gold font-semibold">{fmt2(pr.amount)}</span>
                  </div>
                );
              })}
            </div>
          )}
          {txns && txns.filter((t) => t.type === "personal").length > 0 && (
            <div className="space-y-1.5 border-t border-border pt-3">
              <p className="label-overline">Personal entries</p>
              {txns.filter((t) => t.type === "personal").map((t) => (
                <div key={t.id} className="flex items-center justify-between text-sm" data-testid={`personal-txn-${t.id}`}>
                  <span className="font-mono text-xs text-muted-foreground">
                    {fmtDate(t.date)} · {t.from_partner} paid for {t.to_partner} · {fmt2(t.amount)}{t.note ? ` · ${t.note}` : ""}
                  </span>
                  <span className="flex shrink-0">
                  <Button variant="ghost" size="icon" data-testid={`edit-personal-${t.id}`}
                    onClick={() => {
                      const me = user?.name || "Yash";
                      setPEditing(t.id);
                      setPForm({ person: t.from_partner === me ? t.to_partner : t.from_partner, direction: t.from_partner === me ? "i_paid" : "they_paid", amount: t.amount, date: t.date, note: t.note || "" });
                      setPOpen(true);
                    }}>
                    <Pencil className="h-3.5 w-3.5" /></Button>
                  <Button variant="ghost" size="icon" data-testid={`delete-personal-${t.id}`}
                    onClick={async () => { await api.delete(`/ledger/${t.id}`); toast.success("Deleted"); load(); }}>
                    <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {overview?.scope !== "self" && (
      <Card data-testid="transactions-card">
        <CardHeader><CardTitle className="font-heading text-lg">All Transactions</CardTitle></CardHeader>
        <CardContent>
          {!txns ? <p className="text-sm text-muted-foreground">Loading…</p> : txns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No transactions yet. Add one when someone pays on behalf of another partner, or to settle up.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="transactions-table">
                <thead><tr className="text-left label-overline border-b border-border">
                  <th className="pb-2 pr-4">Date</th><th className="pb-2 pr-4">Transaction</th>
                  <th className="pb-2 pr-4">Project</th><th className="pb-2 pr-4">Note</th>
                  <th className="pb-2 pr-4">Amount</th><th className="pb-2"></th>
                </tr></thead>
                <tbody className="font-mono">
                  {txns.filter((t) => t.type !== "personal").map((t) => (
                    <tr key={t.id} className="border-b border-border/50" data-testid={`txn-row-${t.id}`}>
                      <td className="py-2.5 pr-4">{fmtDate(t.date)}</td>
                      <td className="py-2.5 pr-4 font-sans">
                        {t.type === "paid_on_behalf"
                          ? <span><b>{t.from_partner}</b> paid for <b>{t.to_partner}</b></span>
                          : t.type === "external"
                          ? <span><b>{t.from_partner}</b> → <b>Company</b> (external loan)</span>
                          : <span><b>{t.from_partner}</b> → <b>{t.to_partner}</b> (settle)</span>}
                      </td>
                      <td className="py-2.5 pr-4 font-sans">{t.project_name || "—"}</td>
                      <td className="py-2.5 pr-4 font-sans">{t.note || "—"}</td>
                      <td className="py-2.5 pr-4">{fmt2(t.amount)}</td>
                      <td className="py-2.5"><div className="flex">
                        <Button variant="ghost" size="icon" data-testid={`edit-txn-${t.id}`}
                          onClick={() => {
                            setEditing(t.id);
                            setForm({
                              date: t.date, type: t.type,
                              from_partner: t.type === "external" ? "Yash Sojitra" : t.from_partner,
                              to_partner: t.type === "external" ? "Sanjay Jogani" : t.to_partner,
                              amount: t.amount, project_id: t.project_id || "", note: t.note || "",
                              lender_name: t.type === "external" ? t.from_partner : "",
                            });
                            setOpen(true);
                          }}>
                          <Pencil className="h-3.5 w-3.5" /></Button>
                        <Button variant="ghost" size="icon" data-testid={`delete-txn-${t.id}`}
                          onClick={async () => { await api.delete(`/ledger/${t.id}`); toast.success("Deleted"); load(); }}>
                          <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                      </div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      <Dialog open={!!selectedProfile} onOpenChange={() => setSelectedProfile(null)}>
        <DialogContent data-testid="profile-dialog">
          <DialogHeader><DialogTitle className="font-heading">{selectedProfile?.name} — Profile</DialogTitle></DialogHeader>
          {selectedProfile && (
            <div className="space-y-4">
              <div>
                <p className="label-overline mb-1.5">Company position</p>
                <p className={`font-mono text-sm font-semibold ${selectedProfile.position < 0 ? "text-negative" : "text-positive"}`} data-testid="profile-position">
                  {Math.abs(selectedProfile.position) < 0.005 ? "Settled" : selectedProfile.position > 0 ? `Take from Company ${fmt2(selectedProfile.position)}` : `Pay to Company ${fmt2(-selectedProfile.position)}`}
                </p>
              </div>
              <div>
                <p className="label-overline mb-1.5">Projects</p>
                {selectedProfile.projects.length === 0 ? <p className="text-sm text-muted-foreground">No projects.</p> :
                  selectedProfile.projects.map((p) => (
                    <p key={p.id} className="text-sm font-mono" data-testid={`profile-project-${p.id}`}>
                      {p.name} · {p.percentage}% · invested {fmt2(p.contributed)}
                    </p>
                  ))}
              </div>
              <div>
                <p className="label-overline mb-1.5">Personal debts</p>
                {selectedProfile.personal.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> :
                  selectedProfile.personal.map((pd) => (
                    <p key={`${pd.debtor}-${pd.creditor}`} className="text-sm font-mono">
                      {pd.debtor} owes {pd.creditor} {fmt2(pd.amount)}
                    </p>
                  ))}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="report-dialog">
          <DialogHeader><DialogTitle className="font-heading">Partner Ledger Report</DialogTitle></DialogHeader>
          {report && (
            <div className="space-y-5">
              <div>
                <p className="label-overline mb-2">Company settlement</p>
                <div className="space-y-1.5">
                  {Object.entries(report.balances.totals).map(([k, v]) => (
                    <p key={k} className="text-sm font-mono" data-testid={`report-position-${k.toLowerCase()}`}>
                      {k}: {Math.abs(v) < 0.005 ? "settled" : v > 0 ? `Take from Company ${fmt2(v)}` : `Pay to Company ${fmt2(-v)}`}
                    </p>
                  ))}
                </div>
              </div>
              {report.personal && report.personal.pairs.length > 0 && (
                <div>
                  <p className="label-overline mb-2">Personal debts (outside company pool)</p>
                  <div className="space-y-1.5">
                    {report.personal.pairs.map((p) => (
                      <p key={`${p.debtor}-${p.creditor}`} className="text-sm font-mono" data-testid={`report-personal-${p.debtor.toLowerCase()}-${p.creditor.toLowerCase()}`}>
                        {p.debtor} owes {p.creditor} {fmt2(p.amount)}
                      </p>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <p className="label-overline mb-2">Transaction history ({report.transactions.length})</p>
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {report.transactions.map((t) => (
                    <p key={t.id} className="text-xs font-mono text-muted-foreground">
                      {fmtDate(t.date)} · {t.type === "paid_on_behalf" ? `${t.from_partner} paid for ${t.to_partner}` : `${t.from_partner} → ${t.to_partner}`} · {fmt2(t.amount)}{t.project_name ? ` · ${t.project_name}` : ""}{t.note ? ` · ${t.note}` : ""}
                    </p>
                  ))}
                </div>
              </div>
              <Button data-testid="download-report-button" onClick={downloadReport} className="w-full">Download Report (.txt)</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PartnerSelfView({ overview }) {
  const pos = overview.position || 0;
  return (
    <div className="space-y-5" data-testid="partner-self-view">
      <Card>
        <CardHeader><CardTitle className="font-heading text-lg">My Company Position</CardTitle></CardHeader>
        <CardContent>
          <p className={`font-mono font-semibold text-2xl ${pos < 0 ? "text-negative" : "text-positive"}`} data-testid="self-position">
            {Math.abs(pos) < 0.005 ? "All settled" : pos > 0 ? `Take from Company ${fmt(pos)}` : `Pay to Company ${fmt(-pos)}`}
          </p>
          <p className="text-xs text-muted-foreground mt-1">Your position in the company pool managed by Yash. Other partners' positions are private.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="font-heading text-lg">My Projects</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {overview.projects.length === 0 && <p className="text-sm text-muted-foreground">No projects linked to you yet.</p>}
          {overview.projects.map((p) => (
            <div key={p.id} className="flex justify-between text-sm border-b border-border/50 pb-2 last:border-0" data-testid={`self-project-${p.id}`}>
              <span className="font-medium">{p.name}</span>
              <span className="font-mono">{p.percentage}% · invested {fmt2(p.contributed)}</span>
            </div>
          ))}
        </CardContent>
      </Card>
      {overview.personal.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="font-heading text-lg">Personal Debts</CardTitle></CardHeader>
          <CardContent className="space-y-1.5">
            {overview.personal.map((pd) => (
              <p key={`${pd.debtor}-${pd.creditor}`} className="text-sm font-mono" data-testid={`self-personal-${pd.debtor.toLowerCase()}`}>
                {pd.debtor} owes {pd.creditor} {fmt2(pd.amount)}
              </p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
