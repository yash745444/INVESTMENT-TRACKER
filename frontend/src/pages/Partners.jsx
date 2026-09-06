import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmt2, fmtDate, today, PARTNERS } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, FileText, ArrowRight } from "lucide-react";

export default function Partners() {
  const [txns, setTxns] = useState(null);
  const [balances, setBalances] = useState(null);
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState(null);
  const [form, setForm] = useState({
    date: today(), type: "paid_on_behalf", from_partner: "Yash", to_partner: "Sanjay",
    amount: "", project_id: "", note: "",
  });

  const load = async () => {
    const [t, b, p] = await Promise.all([
      api.get("/ledger"), api.get("/ledger/balances"), api.get("/projects"),
    ]);
    setTxns(t.data); setBalances(b.data); setProjects(p.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const proj = projects.find((p) => p.id === form.project_id);
      await api.post("/ledger", {
        ...form, amount: Number(form.amount),
        project_id: form.project_id || null, project_name: proj?.name || "",
      });
      toast.success("Transaction recorded");
      setOpen(false);
      setForm({ ...form, amount: "", note: "" });
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
    txt += `Partners: Yash, Sanjay, Pranay, Max\n\n== WHO OWES WHOM ==\n`;
    report.balances.pairs.forEach((p) => {
      txt += p.owes ? `${p.owes}: $${p.amount.toFixed(2)}\n` : `${p.a} <-> ${p.b}: settled\n`;
    });
    txt += `\n== NET POSITIONS ==\n`;
    Object.entries(report.balances.totals).forEach(([k, v]) => {
      txt += `${k}: ${v >= 0 ? "owed TO them" : "they owe"} $${Math.abs(v).toFixed(2)}\n`;
    });
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
        <div className="flex gap-2">
          <Button variant="outline" data-testid="report-button" onClick={openReport}>
            <FileText className="h-4 w-4 mr-1.5" /> Report
          </Button>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button data-testid="add-transaction-button"><Plus className="h-4 w-4 mr-1.5" /> Add Transaction</Button></DialogTrigger>
            <DialogContent data-testid="add-transaction-dialog">
              <DialogHeader><DialogTitle className="font-heading">Add Transaction</DialogTitle></DialogHeader>
              <form onSubmit={submit} className="space-y-4">
                <div className="space-y-1.5"><Label>Type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                    <SelectTrigger data-testid="txn-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="paid_on_behalf">Paid on behalf of partner</SelectItem>
                      <SelectItem value="settlement">Settle up (pay / take money)</SelectItem>
                    </SelectContent>
                  </Select></div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>{form.type === "paid_on_behalf" ? "Paid by" : "From"}</Label>
                    <Select value={form.from_partner} onValueChange={(v) => setForm({ ...form, from_partner: v })}>
                      <SelectTrigger data-testid="txn-from-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{PARTNERS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                    </Select></div>
                  <div className="space-y-1.5"><Label>{form.type === "paid_on_behalf" ? "On behalf of" : "To"}</Label>
                    <Select value={form.to_partner} onValueChange={(v) => setForm({ ...form, to_partner: v })}>
                      <SelectTrigger data-testid="txn-to-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{PARTNERS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                    </Select></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Date</Label>
                    <Input data-testid="txn-date-input" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></div>
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
                <Button data-testid="txn-submit" type="submit" className="w-full">Save Transaction</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {PARTNERS.map((p) => (
          <Card key={p} data-testid={`partner-total-${p.toLowerCase()}`}>
            <CardContent className="p-4">
              <p className="label-overline">{p}{p === "Yash" ? " (You)" : ""}</p>
              <p className={`font-mono font-semibold text-lg mt-1.5 ${(balances?.totals[p] || 0) < 0 ? "text-negative" : "text-positive"}`}>
                {(balances?.totals[p] || 0) >= 0 ? `+${fmt(balances?.totals[p] || 0)}` : fmt(balances?.totals[p] || 0)}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {(balances?.totals[p] || 0) >= 0 ? "owed to them" : "they owe"}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card data-testid="pairwise-card">
        <CardHeader><CardTitle className="font-heading text-lg">Who Owes Whom</CardTitle></CardHeader>
        <CardContent>
          {!balances ? <p className="text-sm text-muted-foreground">Loading…</p> : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {balances.pairs.map((p) => (
                <div key={`${p.a}-${p.b}`} className="flex items-center justify-between rounded-lg border border-border p-3.5"
                  data-testid={`pair-${p.a.toLowerCase()}-${p.b.toLowerCase()}`}>
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {p.a} <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" /> {p.b}
                  </div>
                  {p.owes ? (
                    <span className="font-mono text-sm"><span className="text-negative">{p.owes}</span> <span className="text-gold font-semibold">{fmt2(p.amount)}</span></span>
                  ) : (
                    <span className="font-mono text-xs text-positive">settled</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

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
                  {txns.map((t) => (
                    <tr key={t.id} className="border-b border-border/50" data-testid={`txn-row-${t.id}`}>
                      <td className="py-2.5 pr-4">{fmtDate(t.date)}</td>
                      <td className="py-2.5 pr-4 font-sans">
                        {t.type === "paid_on_behalf"
                          ? <span><b>{t.from_partner}</b> paid for <b>{t.to_partner}</b></span>
                          : <span><b>{t.from_partner}</b> → <b>{t.to_partner}</b> (settle)</span>}
                      </td>
                      <td className="py-2.5 pr-4 font-sans">{t.project_name || "—"}</td>
                      <td className="py-2.5 pr-4 font-sans">{t.note || "—"}</td>
                      <td className="py-2.5 pr-4">{fmt2(t.amount)}</td>
                      <td className="py-2.5"><Button variant="ghost" size="icon" data-testid={`delete-txn-${t.id}`}
                        onClick={async () => { await api.delete(`/ledger/${t.id}`); toast.success("Deleted"); load(); }}>
                        <Trash2 className="h-3.5 w-3.5 text-negative" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="report-dialog">
          <DialogHeader><DialogTitle className="font-heading">Partner Ledger Report</DialogTitle></DialogHeader>
          {report && (
            <div className="space-y-5">
              <div>
                <p className="label-overline mb-2">Who owes whom</p>
                <div className="space-y-1.5">
                  {report.balances.pairs.map((p) => (
                    <p key={`${p.a}-${p.b}`} className="text-sm font-mono" data-testid={`report-pair-${p.a.toLowerCase()}-${p.b.toLowerCase()}`}>
                      {p.owes ? `${p.owes} ${fmt2(p.amount)}` : `${p.a} ↔ ${p.b}: settled`}
                    </p>
                  ))}
                </div>
              </div>
              <div>
                <p className="label-overline mb-2">Net positions</p>
                <div className="space-y-1.5">
                  {Object.entries(report.balances.totals).map(([k, v]) => (
                    <p key={k} className="text-sm font-mono">
                      {k}: {v >= 0 ? `is owed ${fmt2(v)}` : `owes ${fmt2(-v)}`}
                    </p>
                  ))}
                </div>
              </div>
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
