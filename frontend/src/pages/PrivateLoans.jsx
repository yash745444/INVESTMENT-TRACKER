import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmt2, fmtDate, today } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { DatePicker } from "../components/DatePicker";
import { toast } from "sonner";
import { Plus, Trash2, HandCoins, Pencil } from "lucide-react";

const EMPTY = { lender: "", amount: "", date: today(), type: "interest",
  annual_rate: "", project_id: "", basis_amount: "", notes: "" };

export default function PrivateLoans() {
  const [loans, setLoans] = useState(null);
  const [projects, setProjects] = useState([]);
  const [people, setPeople] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    const [l, p] = await Promise.all([api.get("/personal-loans"), api.get("/projects")]);
    setLoans(l.data);
    setProjects(p.data.filter((x) => !x.shared));
    api.get("/people").then((r) => setPeople(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...form,
        amount: Number(form.amount),
        annual_rate: Number(form.annual_rate) || 0,
        basis_amount: Number(form.basis_amount) || 0,
        project_id: form.type === "profit_share" ? (form.project_id || null) : null,
      };
      if (editing) await api.put(`/personal-loans/${editing}`, payload);
      else await api.post("/personal-loans", payload);
      toast.success(editing ? "Loan updated" : "Loan added");
      setOpen(false);
      setEditing(null);
      setForm(EMPTY);
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const totalOwed = loans?.reduce((s, l) => s + l.computed.total_owed, 0) || 0;

  return (
    <div className="space-y-6" data-testid="personal-loans-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Private Loans</h1>
          <p className="text-sm text-muted-foreground mt-1 font-mono" data-testid="pl-total-owed">
            Total owed to lenders: {fmt(totalOwed)}
          </p>
        </div>
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(EMPTY); } }}>
          <DialogTrigger asChild><Button data-testid="add-pl-button"><Plus className="h-4 w-4 mr-1.5" /> Add Loan</Button></DialogTrigger>
          <DialogContent data-testid="pl-dialog">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Private Loan</DialogTitle></DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Lender name</Label>
                  <Input data-testid="pl-lender-input" required value={form.lender} list="lender-people-list"
                    onChange={(e) => setForm({ ...form, lender: e.target.value })} placeholder="Pick or type a name" />
                  <datalist id="lender-people-list">
                    {people.map((p) => <option key={p.id} value={p.name} />)}
                  </datalist></div>
                <div className="space-y-1.5"><Label>Amount (AUD)</Label>
                  <Input data-testid="pl-amount-input" type="number" step="0.01" required value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Date taken</Label>
                  <DatePicker testid="pl-date-input" value={form.date} onChange={(v) => setForm({ ...form, date: v })} /></div>
                <div className="space-y-1.5"><Label>Return type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                    <SelectTrigger data-testid="pl-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="interest">Interest rate (% yearly)</SelectItem>
                      <SelectItem value="profit_share">Share of project profit</SelectItem>
                    </SelectContent>
                  </Select></div>
              </div>
              {form.type === "interest" ? (
                <div className="space-y-1.5"><Label>Annual interest rate %</Label>
                  <Input data-testid="pl-rate-input" type="number" step="0.01" required value={form.annual_rate}
                    onChange={(e) => setForm({ ...form, annual_rate: e.target.value })} placeholder="e.g. 8" /></div>
              ) : (
                <>
                  <div className="space-y-1.5"><Label>Linked project</Label>
                    <Select value={form.project_id} onValueChange={(v) => setForm({ ...form, project_id: v })}>
                      <SelectTrigger data-testid="pl-project-select"><SelectValue placeholder="Select project" /></SelectTrigger>
                      <SelectContent>
                        {projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                      </SelectContent>
                    </Select></div>
                  <div className="space-y-1.5"><Label>Basis amount (optional)</Label>
                    <Input data-testid="pl-basis-input" type="number" step="0.01" value={form.basis_amount}
                      onChange={(e) => setForm({ ...form, basis_amount: e.target.value })}
                      placeholder="Defaults to your contributions in the project" />
                    <p className="text-xs text-muted-foreground">Lender share = loan ÷ basis. Their return = that share of the project's final profit.</p></div>
                </>
              )}
              <div className="space-y-1.5"><Label>Notes</Label>
                <Input data-testid="pl-notes-input" value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
              <Button data-testid="pl-submit" type="submit" className="w-full">{editing ? "Save Changes" : "Save Loan"}</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {!loans ? <p className="text-muted-foreground">Loading…</p> : loans.length === 0 ? (
        <Card><CardContent className="p-10 text-center text-muted-foreground">
          <HandCoins className="h-8 w-8 mx-auto mb-3 opacity-40" />
          No private loans yet. Add money you've borrowed from private lenders.
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {loans.map((l) => (
            <Card key={l.id} className="card-hover" data-testid={`pl-card-${l.id}`}>
              <CardContent className="p-5 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-heading font-semibold text-lg tracking-tight">{l.lender}</h3>
                    <p className="text-xs text-muted-foreground">
                      {l.type === "interest"
                        ? `Interest ${l.annual_rate}% p.a. · taken ${fmtDate(l.date)}`
                        : `Profit share${l.computed.project_name ? ` · ${l.computed.project_name}` : ""}`}
                    </p>
                  </div>
                  <div className="flex shrink-0">
                  <Button variant="ghost" size="icon" data-testid={`pl-edit-${l.id}`}
                    onClick={() => { setEditing(l.id); setForm({ lender: l.lender, amount: l.amount, date: l.date, type: l.type, annual_rate: l.annual_rate || "", project_id: l.project_id || "", basis_amount: l.basis_amount || "", notes: l.notes || "" }); setOpen(true); }}>
                    <Pencil className="h-3.5 w-3.5" /></Button>
                  <Button variant="ghost" size="icon" data-testid={`pl-delete-${l.id}`}
                    onClick={async () => { await api.delete(`/personal-loans/${l.id}`); toast.success("Deleted"); load(); }}>
                    <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><p className="label-overline">Loan</p><p className="font-mono font-medium">{fmt(l.amount)}</p></div>
                  {l.type === "interest" ? (
                    <>
                      <div><p className="label-overline">Accrued Interest</p>
                        <p className="font-mono font-medium" data-testid={`pl-accrued-${l.id}`}>{fmt2(l.computed.accrued_interest)}</p></div>
                      <div><p className="label-overline">Time Held</p>
                        <p className="font-mono">{l.computed.years} yrs</p></div>
                    </>
                  ) : (
                    <>
                      <div><p className="label-overline">Share of Profit</p>
                        <p className="font-mono font-medium" data-testid={`pl-share-${l.id}`}>{l.computed.share_pct}%</p></div>
                      <div><p className="label-overline">Basis</p>
                        <p className="font-mono">{fmt(l.computed.basis)}</p></div>
                      <div><p className="label-overline">Project Profit</p>
                        <p className="font-mono">{fmt(l.computed.project_profit)}</p></div>
                    </>
                  )}
                  <div><p className="label-overline">Return to Lender</p>
                    <p className="font-mono font-semibold text-gold" data-testid={`pl-return-${l.id}`}>{fmt2(l.computed.return_amount)}</p></div>
                </div>
                <div className="border-t border-border pt-2.5 flex justify-between text-sm">
                  <span className="text-muted-foreground">Total owed</span>
                  <span className="font-mono font-semibold text-negative">{fmt2(l.computed.total_owed)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
