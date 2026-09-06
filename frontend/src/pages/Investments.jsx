import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmt2, CURRENCIES } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, Pencil } from "lucide-react";

const TYPES = [
  { key: "shares", label: "Shares" },
  { key: "term_insurance", label: "Term Insurance" },
  { key: "other", label: "Other Investments" },
];

const EMPTY = { type: "shares", name: "", currency: "AUD", amount: "", date: "", notes: "" };

export default function Investments() {
  const [items, setItems] = useState(null);
  const [rates, setRates] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    const [i, r] = await Promise.all([api.get("/investments"), api.get("/rates")]);
    setItems(i.data); setRates(r.data.rates);
  };
  useEffect(() => { load(); }, []);

  const toAud = (amount, cur) => rates ? amount / (rates[cur] || 1) : 0;

  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, amount: Number(form.amount) };
      if (editing) await api.put(`/investments/${editing}`, payload);
      else await api.post("/investments", payload);
      toast.success(editing ? "Investment updated" : "Investment added");
      setOpen(false); setEditing(null); setForm(EMPTY);
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const totalAud = items?.reduce((s, i) => s + toAud(i.amount, i.currency), 0) || 0;

  return (
    <div className="space-y-6" data-testid="investments-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Personal Investments</h1>
          <p className="text-sm text-muted-foreground mt-1 font-mono" data-testid="investments-total">
            Total: {fmt(totalAud)} AUD
          </p>
        </div>
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(EMPTY); } }}>
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
                <div className="space-y-1.5"><Label>Currency</Label>
                  <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v })}>
                    <SelectTrigger data-testid="inv-currency-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select></div>
              </div>
              <div className="space-y-1.5"><Label>Name</Label>
                <Input data-testid="inv-name-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Apple shares / TAL Term Life" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Current value</Label>
                  <Input data-testid="inv-amount-input" type="number" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Date</Label>
                  <Input data-testid="inv-date-input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></div>
              </div>
              <div className="space-y-1.5"><Label>Notes</Label>
                <Input data-testid="inv-notes-input" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
              <Button data-testid="inv-submit" type="submit" className="w-full">Save</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {!items ? <p className="text-muted-foreground">Loading…</p> : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {TYPES.map((t) => {
            const group = items.filter((i) => i.type === t.key);
            const groupTotal = group.reduce((s, i) => s + toAud(i.amount, i.currency), 0);
            return (
              <Card key={t.key} data-testid={`inv-group-${t.key}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="font-heading text-lg">{t.label}</CardTitle>
                    <span className="font-mono text-sm font-semibold">{fmt(groupTotal)}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {group.length === 0 && <p className="text-sm text-muted-foreground">None yet.</p>}
                  {group.map((i) => (
                    <div key={i.id} className="flex items-start justify-between gap-2 border-b border-border/50 pb-3 last:border-0 last:pb-0"
                      data-testid={`inv-row-${i.id}`}>
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{i.name}</p>
                        <p className="font-mono text-xs text-muted-foreground mt-0.5">
                          {fmt2(i.amount, i.currency)}{i.currency !== "AUD" && ` ≈ ${fmt(toAud(i.amount, i.currency))}`}
                        </p>
                      </div>
                      <div className="flex shrink-0">
                        <Button variant="ghost" size="icon" data-testid={`edit-inv-${i.id}`}
                          onClick={() => { setEditing(i.id); setForm({ ...i }); setOpen(true); }}>
                          <Pencil className="h-3.5 w-3.5" /></Button>
                        <Button variant="ghost" size="icon" data-testid={`delete-inv-${i.id}`}
                          onClick={async () => { await api.delete(`/investments/${i.id}`); toast.success("Deleted"); load(); }}>
                          <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                      </div>
                    </div>
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
