import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { fmt, fmt2 } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, CheckCircle2, XCircle, Calculator } from "lucide-react";

const PROJECT_TYPES = [
  ["single_dwelling", "Single Dwelling"],
  ["duplex", "Duplex"],
  ["multi_dwelling", "Multi-Dwelling"],
  ["subdivision", "Subdivision"],
];

const TYPE_HINTS = {
  single_dwelling: "Single dwelling — watch holding costs and resale comparable evidence.",
  duplex: "Duplex — remember dual service connections and strata/subdivision costs if selling separately.",
  multi_dwelling: "Multi-dwelling — include per-lot contributions, body corporate setup, staged selling.",
  subdivision: "Subdivision — include surveying, plan sealing, infrastructure contributions and per-lot service connections.",
};

const FIELD_GROUPS = [
  ["Acquisition", [["land_cost", "Land / Site"], ["stamp_duty", "Stamp Duty"], ["acquisition_legal", "Legal (purchase)"]]],
  ["Approvals & Design", [["council_permits", "Council / DA fees & contributions"], ["design_architect", "Architect / Design"], ["engineering", "Engineering"], ["surveying", "Surveying / Titles"], ["project_management", "Project Management"]]],
  ["Construction", [["demolition", "Demolition / Site Prep"], ["site_works", "Site Works / Services"], ["construction_cost", "Construction Cost"]]],
  ["Holding & Finance", [["holding_costs", "Holding Costs (rates, insurance)"], ["finance_interest", "Finance / Interest"], ["bond", "Bond / Bank Guarantee"]]],
  ["Selling", [["marketing", "Marketing"], ["agent_fees", "Agent / Selling Fees"], ["legal", "Legal (sale)"]]],
  ["Other", [["other_costs", "Other Costs"]]],
];

const EMPTY = { name: "", project_type: "single_dwelling", contingency_pct: 10, expected_revenue: "", loan_amount: "",
  land_cost: "", stamp_duty: "", acquisition_legal: "", council_permits: "", design_architect: "",
  engineering: "", surveying: "", project_management: "", demolition: "", site_works: "",
  construction_cost: "", holding_costs: "", finance_interest: "", bond: "",
  marketing: "", agent_fees: "", legal: "", other_costs: "" };

function compute(f) {
  const n = (k) => Number(f[k]) || 0;
  const contingency = n("construction_cost") * n("contingency_pct") / 100;
  const total = n("land_cost") + n("stamp_duty") + n("acquisition_legal") + n("council_permits")
    + n("design_architect") + n("engineering") + n("surveying") + n("project_management")
    + n("demolition") + n("site_works") + n("construction_cost") + contingency
    + n("holding_costs") + n("finance_interest") + n("bond") + n("marketing")
    + n("agent_fees") + n("legal") + n("other_costs");
  const revenue = n("expected_revenue");
  const profit = revenue - total;
  const margin = revenue > 0 ? profit / revenue * 100 : 0;
  const cash = total - n("loan_amount");
  const roiCash = cash > 0 ? profit / cash * 100 : 0;
  return { contingency, total, profit, margin, cash, roiCash, feasible: profit > 0 && roiCash >= 50 };
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
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Project type</Label>
                    <Select value={form.project_type} onValueChange={(v) => setForm({ ...form, project_type: v })}>
                      <SelectTrigger data-testid="fs-type-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{PROJECT_TYPES.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
                    </Select></div>
                  <div className="space-y-1.5"><Label>Contingency % (of construction)</Label>
                    <Input data-testid="fs-input-contingency-pct" type="number" step="0.1" value={form.contingency_pct}
                      onChange={(e) => setForm({ ...form, contingency_pct: e.target.value })} /></div>
                </div>
                <p className="text-xs text-muted-foreground" data-testid="fs-type-hint">{TYPE_HINTS[form.project_type]}</p>
                {FIELD_GROUPS.map(([group, fields]) => (
                  <div key={group} className="space-y-2">
                    <p className="label-overline border-b border-border pb-1">{group}</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {fields.map(([key, label]) => (
                        <div key={key} className="space-y-1.5"><Label>{label}</Label>
                          <Input data-testid={`fs-input-${key.replace(/_/g, "-")}`} type="number" step="0.01" value={form[key]}
                            onChange={(e) => setForm({ ...form, [key]: e.target.value })} placeholder="0" /></div>
                      ))}
                    </div>
                  </div>
                ))}
                <div className="space-y-2">
                  <p className="label-overline border-b border-border pb-1">Funding & Revenue</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1.5"><Label>Loan amount (debt funding)</Label>
                      <Input data-testid="fs-input-loan-amount" type="number" step="0.01" value={form.loan_amount}
                        onChange={(e) => setForm({ ...form, loan_amount: e.target.value })} placeholder="0" /></div>
                    <div className="space-y-1.5"><Label>Expected Revenue (GRV)</Label>
                      <Input data-testid="fs-input-expected-revenue" type="number" step="0.01" value={form.expected_revenue}
                        onChange={(e) => setForm({ ...form, expected_revenue: e.target.value })} placeholder="0" /></div>
                  </div>
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
                <p className="text-xs text-muted-foreground mt-1">Needs profit &gt; 0 and ROI on cash ≥ 50%</p>
              </div>
              {[["Contingency", c.contingency], ["Total Cost (TDC)", c.total], ["Loan", Number(form.loan_amount) || 0], ["Cash Required", c.cash], ["Expected Revenue", Number(form.expected_revenue) || 0], ["Profit", c.profit]].map(([l, v]) => (
                <div key={l} className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{l}</span>
                  <span className={`font-mono font-medium ${l === "Profit" ? (v >= 0 ? "text-positive" : "text-negative") : ""}`}
                    data-testid={l.startsWith("Total Cost") ? "fs-total-cost" : l === "Profit" ? "fs-profit" : l === "Cash Required" ? "fs-cash-required" : undefined}>{fmt(v)}</span>
                </div>
              ))}
              <div className="flex justify-between text-sm border-t border-border pt-2">
                <span className="text-muted-foreground">Margin on GRV</span>
                <span className="font-mono font-semibold" data-testid="fs-margin">{c.margin.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">ROI on cash in</span>
                <span className={`font-mono font-semibold ${c.roiCash >= 50 ? "text-positive" : "text-negative"}`} data-testid="fs-roi-cash">{c.roiCash.toFixed(1)}%</span>
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
                  <div><p className="label-overline">Cash Required</p><p className="font-mono">{s.computed.cash_in !== undefined ? fmt(s.computed.cash_in) : "—"}</p></div>
                  <div><p className="label-overline">Profit</p>
                    <p className={`font-mono font-semibold ${s.computed.profit >= 0 ? "text-positive" : "text-negative"}`}>{fmt(s.computed.profit)}</p></div>
                  <div><p className="label-overline">Margin / ROI on Cash</p>
                    <p className="font-mono">{s.computed.margin_pct}% / {s.computed.roi_cash_pct !== undefined ? s.computed.roi_cash_pct : s.computed.roi_pct}%</p></div>
                </div>
                <p className="text-[10px] font-mono text-muted-foreground uppercase">{PROJECT_TYPES.find(([k]) => k === s.project_type)?.[1] || "Single Dwelling"}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
