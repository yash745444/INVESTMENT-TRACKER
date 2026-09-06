import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmtDate, CURRENCIES } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, Building2, X } from "lucide-react";
import { DatePicker } from "../components/DatePicker";

const EMPTY = { name: "", address: "", purchase_date: "", purchase_price: "", current_value: "", monthly_rent: "", debt: "", currency: "AUD", partners: [], notes: "" };

export default function Properties() {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = () => api.get("/properties").then((r) => setItems(r.data)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...form,
        partners: (form.partners || []).filter((p) => p.name?.trim()).map((p) => ({ name: p.name.trim(), percentage: Number(p.percentage) || 0 })),
        purchase_price: Number(form.purchase_price) || 0,
        current_value: Number(form.current_value) || 0,
        monthly_rent: Number(form.monthly_rent) || 0,
        debt: Number(form.debt) || 0,
      };
      if (editing) await api.put(`/properties/${editing}`, payload);
      else await api.post("/properties", payload);
      toast.success(editing ? "Property updated" : "Property added");
      setOpen(false); setEditing(null); setForm(EMPTY);
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const field = (key, label, type = "text", testid) => (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input data-testid={testid} type={type} step={type === "number" ? "0.01" : undefined}
        value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </div>
  );

  return (
    <div className="space-y-6" data-testid="properties-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Investment Properties</h1>
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(EMPTY); } }}>
          <DialogTrigger asChild><Button data-testid="add-property-button"><Plus className="h-4 w-4 mr-1.5" /> Add Property</Button></DialogTrigger>
          <DialogContent data-testid="property-dialog" className="max-h-[85vh] overflow-y-auto">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Property</DialogTitle></DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              {field("name", "Property name", "text", "prop-name-input")}
              {field("address", "Address", "text", "prop-address-input")}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Purchase date</Label>
                  <DatePicker testid="prop-purchase-date-input" value={form.purchase_date} onChange={(v) => setForm({ ...form, purchase_date: v })} /></div>
                <div className="space-y-1.5"><Label>Currency</Label>
                  <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v })}>
                    <SelectTrigger data-testid="prop-currency-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {field("purchase_price", "Purchase price", "number", "prop-purchase-price-input")}
                {field("current_value", "Current value", "number", "prop-current-value-input")}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {field("monthly_rent", "Current monthly rent", "number", "prop-rent-input")}
                {field("debt", "Mortgage / debt", "number", "prop-debt-input")}
              </div>
              <div className="space-y-2">
                <Label>Partnership (ownership %)</Label>
                {(form.partners || []).map((pt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input data-testid={`prop-partner-name-${i}`} value={pt.name} placeholder="Partner name"
                      onChange={(e) => setForm({ ...form, partners: form.partners.map((r, j) => j === i ? { ...r, name: e.target.value } : r) })} />
                    <Input data-testid={`prop-partner-pct-${i}`} type="number" step="0.01" className="w-24 shrink-0" value={pt.percentage}
                      onChange={(e) => setForm({ ...form, partners: form.partners.map((r, j) => j === i ? { ...r, percentage: e.target.value } : r) })} />
                    <Button type="button" variant="ghost" size="icon" data-testid={`prop-partner-remove-${i}`}
                      onClick={() => setForm({ ...form, partners: form.partners.filter((_, j) => j !== i) })}>
                      <X className="h-3.5 w-3.5" /></Button>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" data-testid="prop-add-partner"
                  onClick={() => setForm({ ...form, partners: [...(form.partners || []), { name: "", percentage: "" }] })}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add partner
                </Button>
              </div>
              {field("notes", "Notes", "text", "prop-notes-input")}
              <Button data-testid="prop-submit" type="submit" className="w-full">Save</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {!items ? <p className="text-muted-foreground">Loading…</p> : items.length === 0 ? (
        <Card><CardContent className="p-10 text-center text-muted-foreground">
          <Building2 className="h-8 w-8 mx-auto mb-3 opacity-40" />
          No properties yet. Add your investment properties to track rent and debt.
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {items.map((p) => (
            <Card key={p.id} className="card-hover" data-testid={`property-card-${p.id}`}>
              <CardContent className="p-5 space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-heading font-semibold text-lg tracking-tight">{p.name}</h3>
                    {p.address && <p className="text-xs text-muted-foreground mt-0.5">{p.address}</p>}
                  </div>
                  <div className="flex shrink-0">
                    <Button variant="ghost" size="icon" data-testid={`edit-prop-${p.id}`}
                      onClick={() => { setEditing(p.id); setForm({ ...p }); setOpen(true); }}>
                      <Pencil className="h-3.5 w-3.5" /></Button>
                    <Button variant="ghost" size="icon" data-testid={`delete-prop-${p.id}`}
                      onClick={async () => { await api.delete(`/properties/${p.id}`); toast.success("Deleted"); load(); }}>
                      <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="label-overline">Rent / mo</p>
                    <p className="font-mono font-medium text-positive">{fmt(p.monthly_rent, p.currency)}</p></div>
                  <div><p className="label-overline">Bought</p>
                    <p className="font-mono font-medium">{fmtDate(p.purchase_date)}</p></div>
                  <div><p className="label-overline">Current Value</p>
                    <p className="font-mono font-medium">{fmt(p.current_value, p.currency)}</p></div>
                  <div><p className="label-overline">Debt</p>
                    <p className="font-mono font-medium text-negative">{fmt(p.debt, p.currency)}</p></div>
                </div>
                <div className="border-t border-border pt-3 flex justify-between text-sm">
                  <span className="text-muted-foreground">Equity</span>
                  <span className={`font-mono font-semibold ${p.current_value - p.debt < 0 ? "text-negative" : "text-positive"}`}>
                    {fmt(p.current_value - p.debt, p.currency)}
                  </span>
                </div>
                {p.partners?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1" data-testid={`prop-partners-${p.id}`}>
                    {p.partners.map((pt) => (
                      <span key={pt.name} className="text-xs font-mono px-2 py-0.5 rounded-full bg-secondary"
                        data-testid={`prop-partner-${p.id}-${pt.name.toLowerCase()}`}>
                        {pt.name} {pt.percentage}%
                      </span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
