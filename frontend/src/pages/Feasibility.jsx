import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmt2 } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { toast } from "sonner";
import { Plus, Trash2, CheckCircle2, XCircle, Calculator } from "lucide-react";

const COST_FIELDS = [
  ["land_cost", "Land / Site Acquisition"],
  ["construction_cost", "Construction Cost"],
  ["bond", "Bond / Bank Guarantee"],
  ["council_permits", "Council & Permits"],
  ["design_architect", "Design & Architect"],
  ["finance_interest", "Finance & Interest"],
  ["legal", "Legal"],
  ["marketing", "Marketing & Sales"],
  ["other_costs", "Other Costs"],
];

const EMPTY = { name: "", contingency_pct: 10, expected_revenue: "",
  land_cost: "", construction_cost: "", bond: "", council_permits: "",
  design_architect: "", finance_interest: "", legal: "", marketing: "", other_costs: "" };

function compute(f) {
  const n = (k) => Number(f[k]) || 0;
  const contingency = n("construction_cost") * n("contingency_pct") / 100;
  const total = n("land_cost") + n("construction_cost") + n("bond") + n("council_permits")
    + n("design_architect") + n("finance_interest") + n("legal") + n("marketing")
    + contingency + n("other_costs");
  const revenue = n("expected_revenue");
  const profit = revenue - total;
  const margin = revenue > 0 ? profit / revenue * 100 : 0;
  const roi = total > 0 ? profit / total * 100 : 0;
  return { contingency, total, profit, margin, roi, feasible: profit > 0 && margin >= 15 };
}

export default function Feasibility() {
  const [studies, setStudies] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [showForm, setShowForm] = useState(false);

  const load = () => api.get("/feasibility").then((r) => setStudies(r.data)).catch(() => setStudies([]));
  useEffect(() => { load(); }, []);

  const c = compute(form);

  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form };
      Object.keys(payload).forEach((k) => { if (k !== "name") payload[k] = Number(payload[k]) || 0; });
      await api.post("/feasibility", payload);
      toast.success("Feasibility study saved");
      setForm(EMPTY);
      setShowForm(false);
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  return (
    <div className="space-y-6" data-testid="feasibility-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Project Feasibility</h1>
        <Button data-testid="new-study-button" onClick={() => setShowForm(!showForm)}>
          <Plus className="h-4 w-4 mr-1.5" /> New Study
        </Button>
      </div>

      {showForm && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <Card className="lg:col-span-7" data-testid="feasibility-form-card">
            <CardHeader><CardTitle className="font-heading text-lg flex items-center gap-2"><Calculator className="h-4 w-4" /> Cost Inputs</CardTitle></CardHeader>
            <CardContent>
              <form onSubmit={save} className="space-y-4">
                <div className="space-y-1.5"><Label>Study name</Label>
                  <Input data-testid="fs-name-input" required value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. 32-34 Cadman v1" /></div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {COST_FIELDS.map(([key, label]) => (
                    <div key={key} className="space-y-1.5"><Label>{label}</Label>
                      <Input data-testid={`fs-input-${key.replace(/_/g, "-")}`} type="number" step="0.01" value={form[key]}
                        onChange={(e) => setForm({ ...form, [key]: e.target.value })} placeholder="0" /></div>
                  ))}
                  <div className="space-y-1.5"><Label>Contingency % (of construction)</Label>
                    <Input data-testid="fs-input-contingency-pct" type="number" step="0.1" value={form.contingency_pct}
                      onChange={(e) => setForm({ ...form, contingency_pct: e.target.value })} /></div>
                  <div className="space-y-1.5"><Label>Expected Revenue (sales)</Label>
                    <Input data-testid="fs-input-expected-revenue" type="number" step="0.01" value={form.expected_revenue}
                      onChange={(e) => setForm({ ...form, expected_revenue: e.target.value })} placeholder="0" /></div>
                </div>
                <Button data-testid="fs-save-button" type="submit" className="w-full">Save Study</Button>
              </form>
            </CardContent>
          </Card>

          <Card className="lg:col-span-5 h-fit" data-testid="feasibility-result-card">
            <CardHeader><CardTitle className="font-heading text-lg">Live Result</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className={`rounded-lg border p-4 text-center ${c.feasible ? "border-positive" : "border-negative"}`} data-testid="fs-verdict">
                {c.feasible ? (
                  <p className="flex items-center justify-center gap-2 font-heading font-bold text-lg text-positive"><CheckCircle2 className="h-5 w-5" /> Feasible</p>
                ) : (
                  <p className="flex items-center justify-center gap-2 font-heading font-bold text-lg text-negative"><XCircle className="h-5 w-5" /> Not Feasible</p>
                )}
                <p className="text-xs text-muted-foreground mt-1">Needs profit &gt; 0 and margin ≥ 15%</p>
              </div>
              {[["Contingency", c.contingency], ["Total Cost", c.total], ["Expected Revenue", Number(form.expected_revenue) || 0], ["Profit", c.profit]].map(([l, v]) => (
                <div key={l} className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{l}</span>
                  <span className={`font-mono font-medium ${l === "Profit" ? (v >= 0 ? "text-positive" : "text-negative") : ""}`}
                    data-testid={l === "Total Cost" ? "fs-total-cost" : l === "Profit" ? "fs-profit" : undefined}>{fmt(v)}</span>
                </div>
              ))}
              <div className="flex justify-between text-sm border-t border-border pt-2">
                <span className="text-muted-foreground">Margin / ROI</span>
                <span className="font-mono font-semibold" data-testid="fs-margin">{c.margin.toFixed(1)}% / {c.roi.toFixed(1)}%</span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {!studies ? <p className="text-muted-foreground">Loading…</p> : studies.length === 0 && !showForm ? (
        <Card><CardContent className="p-10 text-center text-muted-foreground">
          <Calculator className="h-8 w-8 mx-auto mb-3 opacity-40" />
          No feasibility studies yet. Run the numbers on your next project.
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {studies.map((s) => (
            <Card key={s.id} className="card-hover" data-testid={`fs-study-${s.id}`}>
              <CardContent className="p-5 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-heading font-semibold text-lg tracking-tight">{s.name}</h3>
                  <div className="flex items-center gap-1.5">
                    {s.computed.feasible
                      ? <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-secondary text-positive">FEASIBLE</span>
                      : <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-secondary text-negative">NOT FEASIBLE</span>}
                    <Button variant="ghost" size="icon" data-testid={`fs-delete-${s.id}`}
                      onClick={async () => { await api.delete(`/feasibility/${s.id}`); toast.success("Deleted"); load(); }}>
                      <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><p className="label-overline">Total Cost</p><p className="font-mono">{fmt(s.computed.total_cost)}</p></div>
                  <div><p className="label-overline">Revenue</p><p className="font-mono">{fmt(s.expected_revenue)}</p></div>
                  <div><p className="label-overline">Profit</p>
                    <p className={`font-mono font-semibold ${s.computed.profit >= 0 ? "text-positive" : "text-negative"}`}>{fmt(s.computed.profit)}</p></div>
                  <div><p className="label-overline">Margin / ROI</p>
                    <p className="font-mono">{s.computed.margin_pct}% / {s.computed.roi_pct}%</p></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
