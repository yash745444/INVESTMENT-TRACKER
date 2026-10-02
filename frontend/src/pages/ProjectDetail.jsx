import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { fmt, fmt2, fmtDate, today, PARTNERS } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { ArrowLeft, Plus, Trash2, ChevronDown, ChevronUp, Copy, Pencil } from "lucide-react";
import { DatePicker } from "../components/DatePicker";
import { useAuth } from "../context/AuthContext";

const COST_CATEGORIES = ["Site Acquisition", "Architectural & Permits", "Foundation & Structure", "MEP & Finishes", "Marketing & Legal", "Other"];

export default function ProjectDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [contributions, setContributions] = useState([]);
  const [costs, setCosts] = useState([]);
  const [loans, setLoans] = useState([]);
  const [profit, setProfit] = useState("");

  const load = async () => {
    try {
      const [p, c, co, l] = await Promise.all([
        api.get(`/projects/${id}`),
        api.get(`/projects/${id}/contributions`),
        api.get(`/projects/${id}/costs`),
        api.get(`/projects/${id}/loans`),
      ]);
      setProject(p.data); setContributions(c.data); setCosts(co.data); setLoans(l.data);
      setProfit(p.data.final_profit || "");
    } catch { toast.error("Failed to load project"); }
  };
  useEffect(() => { load(); }, [id]);

  const saveProfit = async () => {
    try {
      await api.post(`/projects/${id}/profit`, { final_profit: Number(profit) || 0 });
      toast.success("Project outcome saved");
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  if (!project) return <div className="text-muted-foreground">Loading…</div>;

  const partnerNames = project.partners?.length ? project.partners.map((p) => p.name) : PARTNERS;
  const readOnly = !!project.shared;
  const memberPartner = readOnly
    ? project.partners?.find((pt) => pt.email === user?.email)?.name || null
    : null;
  const totalContrib = contributions.reduce((s, c) => s + c.amount, 0);
  const totalCosts = costs.reduce((s, c) => s + c.amount, 0);
  const totalDrawn = loans.reduce((s, l) => s + l.metrics.drawn, 0);
  const totalOutstanding = loans.reduce((s, l) => s + l.metrics.outstanding, 0);
  const totalMonthly = loans.reduce((s, l) => s + l.metrics.monthly_payment, 0);

  return (
    <div className="space-y-6" data-testid="project-detail-page">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" data-testid="back-to-projects" onClick={() => navigate("/projects")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">{project.name}</h1>
          {project.address && <p className="text-sm text-muted-foreground">{project.address}</p>}
          {readOnly && <span className="inline-block mt-1 text-[10px] font-mono px-2 py-0.5 rounded-full border text-gold" style={{ borderColor: "hsl(var(--gold))" }} data-testid="project-readonly-badge">Shared project · view only</span>}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {[
          ["Contributions", totalContrib, "pd-stat-contributions"],
          ["Costs Incurred", totalCosts, "pd-stat-costs"],
          ["Cash Position", totalContrib + totalDrawn - totalCosts, "pd-stat-cash"],
          ["Loan Outstanding", totalOutstanding, "pd-stat-outstanding"],
          ["Repayment / mo", totalMonthly, "pd-stat-monthly"],
          ["Project Value", project.current_value || 0, "pd-stat-value"],
        ].map(([label, val, tid]) => (
          <Card key={tid} data-testid={tid}>
            <CardContent className="p-4">
              <p className="label-overline">{label}</p>
              <p className={`font-mono font-semibold text-lg mt-1.5 ${label.includes("Loan") || label.includes("Costs") ? "text-negative" : ""}`}>{fmt(val)}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="overview">
        <TabsList data-testid="project-tabs">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="partners" data-testid="tab-partners">Partners</TabsTrigger>
          <TabsTrigger value="contributions" data-testid="tab-contributions">Contributions</TabsTrigger>
          <TabsTrigger value="costs" data-testid="tab-costs">Cost Tracker</TabsTrigger>
          <TabsTrigger value="loans" data-testid="tab-loans">Loans</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-5">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <Card data-testid="overview-partners-card">
              <CardHeader><CardTitle className="font-heading text-lg">Ownership Split</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {project.partners?.map((pt) => {
                  const share = contributions.filter((c) => c.partner === pt.name).reduce((s, c) => s + c.amount, 0);
                  return (
                    <div key={pt.name} className="flex items-center justify-between" data-testid={`overview-partner-${pt.name.toLowerCase()}`}>
                      <span className="text-sm font-medium">{pt.name}</span>
                      <span className="font-mono text-sm">{pt.percentage}% · {fmt(share)} in</span>
                    </div>
                  );
                })}
                {(!project.partners || project.partners.length === 0) && (
                  <p className="text-sm text-muted-foreground">No ownership percentages set.</p>
                )}
              </CardContent>
            </Card>
            <Card data-testid="overview-loans-card">
              <CardHeader><CardTitle className="font-heading text-lg">Debt Facilities</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {loans.length === 0 && <p className="text-sm text-muted-foreground">No loans yet.</p>}
                {loans.map((l) => (
                  <div key={l.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{l.name}</p>
                      <p className="text-xs text-muted-foreground">{l.type === "interest_only" ? "Interest-only" : "Principal + Interest"} · {l.annual_rate}% · {l.term_months}mo</p>
                    </div>
                    <span className="font-mono text-sm text-negative">{fmt(l.metrics.outstanding)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card data-testid="overview-outcome-card">
              <CardHeader><CardTitle className="font-heading text-lg">Project Outcome</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">Final profit (my share) when the project settles — drives profit-share lender returns in Private Loans.</p>
                {readOnly ? (
                  <p className="font-mono font-semibold text-lg" data-testid="final-profit-value">{fmt(project.final_profit || 0)}</p>
                ) : (
                  <div className="flex gap-2">
                    <Input data-testid="final-profit-input" type="number" step="0.01" value={profit}
                      onChange={(e) => setProfit(e.target.value)} placeholder="0" />
                    <Button data-testid="final-profit-save" onClick={saveProfit} size="sm">Save</Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="partners" className="mt-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {(project.partners || []).map((pt) => {
              const invested = contributions.filter((c) => c.partner === pt.name).reduce((s, c) => s + c.amount, 0);
              return (
                <Card key={pt.name} className="card-hover" data-testid={`partner-card-${pt.name.toLowerCase()}`}>
                  <CardContent className="p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-heading font-semibold">{pt.name}{pt.name === user?.name && <span className="text-xs text-gold ml-1.5">(You)</span>}</h3>
                      <span className="font-mono text-sm text-muted-foreground">{pt.percentage}%</span>
                    </div>
                    <div className="space-y-1.5 text-sm">
                      <div className="flex justify-between"><span className="text-muted-foreground">Invested</span>
                        <span className="font-mono font-semibold text-positive">{fmt(invested)}</span></div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="contributions" className="mt-5">
          <ContributionsTab projectId={id} contributions={contributions} reload={load} partnerNames={partnerNames} partners={project.partners || []} readOnly={readOnly} memberPartner={memberPartner} />
        </TabsContent>
        <TabsContent value="costs" className="mt-5">
          <CostsTab projectId={id} costs={costs} reload={load} partnerNames={partnerNames} readOnly={readOnly} />
        </TabsContent>
        <TabsContent value="loans" className="mt-5">
          <LoansTab projectId={id} loans={loans} reload={load} readOnly={readOnly} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function DataTable({ head, rows, testid }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid={testid}>
        <thead><tr className="text-left label-overline border-b border-border">
          {head.map((h) => <th key={h} className="pb-2 pr-4">{h}</th>)}
        </tr></thead>
        <tbody className="font-mono">{rows}</tbody>
      </table>
    </div>
  );
}

function ContributionsTab({ projectId, contributions, reload, partnerNames, partners, readOnly, memberPartner }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ date: today(), partner: partnerNames?.[0] || "", amount: "", description: "" });

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (!editing && !memberPartner && form.partner === "__company") {
        const r = await api.post(`/projects/${projectId}/contributions/split`, { date: form.date, amount: Number(form.amount), description: form.description });
        toast.success(`Company contribution split across ${r.data.inserted} partners`);
        setOpen(false);
        setForm({ date: today(), partner: partnerNames?.[0] || "", amount: "", description: "" });
        reload();
        return;
      }
      const payload = { ...form, partner: memberPartner || form.partner, amount: Number(form.amount) };
      if (editing) await api.put(`/contributions/${editing}`, payload);
      else await api.post(`/projects/${projectId}/contributions`, payload);
      toast.success(editing ? "Contribution updated" : "Contribution added");
      setOpen(false);
      setEditing(null);
      setForm({ date: today(), partner: partnerNames?.[0] || "", amount: "", description: "" });
      reload();
    } catch (err) { toast.error(apiError(err)); }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="font-heading text-lg">Capital Contributions</CardTitle>
        {(!readOnly || memberPartner) && (
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditing(null); }}>
          <DialogTrigger asChild><Button size="sm" data-testid="add-contribution-button"><Plus className="h-4 w-4 mr-1" /> Add</Button></DialogTrigger>
          <DialogContent data-testid="add-contribution-dialog">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Contribution</DialogTitle></DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Date</Label>
                  <DatePicker testid="contribution-date-input" value={form.date} onChange={(v) => setForm({ ...form, date: v })} /></div>
                <div className="space-y-1.5"><Label>Partner</Label>
                  <Select value={memberPartner || form.partner} onValueChange={(v) => setForm({ ...form, partner: v })} disabled={!!memberPartner}>
                    <SelectTrigger data-testid="contribution-partner-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {partnerNames.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                      {!editing && !memberPartner && partners.length > 0 && (
                        <SelectItem value="__company" data-testid="contribution-company-option">Company — split by ownership %</SelectItem>
                      )}
                    </SelectContent>
                  </Select></div>
              </div>
              {form.partner === "__company" && Number(form.amount) > 0 && (
                <div className="rounded-lg border border-border p-3 space-y-1" data-testid="company-split-preview">
                  <p className="label-overline">Split preview</p>
                  {partners.filter((pt) => pt.percentage > 0).map((pt) => (
                    <div key={pt.name} className="flex justify-between text-xs font-mono" data-testid={`split-preview-${pt.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
                      <span>{pt.name} ({pt.percentage}%)</span>
                      <span>{fmt2(Number(form.amount) * pt.percentage / 100)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="space-y-1.5"><Label>Amount (AUD)</Label>
                <Input data-testid="contribution-amount-input" type="number" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
              <div className="space-y-1.5"><Label>Description</Label>
                <Input data-testid="contribution-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="e.g. 10% Deposit" /></div>
              <Button data-testid="contribution-submit" type="submit" className="w-full">{editing ? "Save Changes" : "Save"}</Button>
            </form>
          </DialogContent>
        </Dialog>)}
      </CardHeader>
      <CardContent>
        {contributions.length === 0 ? <p className="text-sm text-muted-foreground">No contributions recorded.</p> : (
          <DataTable testid="contributions-table" head={["Date", "Partner", "Description", "Amount", ""]}
            rows={contributions.map((c) => (
              <tr key={c.id} className="border-b border-border/50" data-testid={`contribution-row-${c.id}`}>
                <td className="py-2.5 pr-4">{fmtDate(c.date)}</td>
                <td className="py-2.5 pr-4 font-sans font-medium">{c.partner}</td>
                <td className="py-2.5 pr-4 font-sans">{c.description || "—"}</td>
                <td className="py-2.5 pr-4">{fmt2(c.amount)}</td>
                <td className="py-2.5">
                  <div className="flex">
                    <Button variant="ghost" size="icon" data-testid={`duplicate-contribution-${c.id}`} title="Duplicate (change partner)"
                      onClick={() => { setEditing(null); setForm({ date: today(), partner: memberPartner || c.partner, amount: c.amount, description: c.description || "" }); setOpen(true); }}>
                      <Copy className="h-3.5 w-3.5" /></Button>
                    {!readOnly && (<Button variant="ghost" size="icon" data-testid={`edit-contribution-${c.id}`} title="Edit"
                      onClick={() => { setEditing(c.id); setForm({ date: c.date, partner: c.partner, amount: c.amount, description: c.description || "" }); setOpen(true); }}>
                      <Pencil className="h-3.5 w-3.5" /></Button>)}
                    {!readOnly && (<Button variant="ghost" size="icon" data-testid={`delete-contribution-${c.id}`}
                      onClick={async () => { await api.delete(`/contributions/${c.id}`); toast.success("Deleted"); reload(); }}>
                      <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>)}
                  </div>
                </td>
              </tr>
            ))} />
        )}
      </CardContent>
    </Card>
  );
}

function CostsTab({ projectId, costs, reload, partnerNames, readOnly }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [rows, setRows] = useState([{ date: today(), category: "Site Acquisition", description: "", amount: "", paid_by: "" }]);
  const [form, setForm] = useState({ date: today(), category: "Site Acquisition", amount: "", description: "", paid_by: "" });

  const submitBulk = async () => {
    const items = rows.filter((r) => Number(r.amount) > 0).map((r) => ({ ...r, amount: Number(r.amount) }));
    if (!items.length) { toast.error("Add at least one amount"); return; }
    try {
      await api.post(`/projects/${projectId}/costs/bulk`, { items });
      toast.success(`${items.length} expenses added`);
      setBulkOpen(false);
      setRows([{ date: today(), category: "Site Acquisition", description: "", amount: "", paid_by: "" }]);
      reload();
    } catch (err) { toast.error(apiError(err)); }
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editing) await api.put(`/costs/${editing}`, { ...form, amount: Number(form.amount) });
      else await api.post(`/projects/${projectId}/costs`, { ...form, amount: Number(form.amount) });
      toast.success(editing ? "Cost updated" : "Cost added");
      setOpen(false);
      setEditing(null);
      setForm({ date: today(), category: "Site Acquisition", amount: "", description: "", paid_by: "" });
      reload();
    } catch (err) { toast.error(apiError(err)); }
  };

  const byCategory = {};
  costs.forEach((c) => { byCategory[c.category] = (byCategory[c.category] || 0) + c.amount; });

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {COST_CATEGORIES.map((cat) => (
          <Card key={cat} data-testid={`cost-cat-${cat.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
            <CardContent className="p-3.5">
              <p className="label-overline truncate">{cat}</p>
              <p className="font-mono font-medium text-sm mt-1">{fmt(byCategory[cat] || 0)}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="font-heading text-lg">Project Cash / Cost Tracker</CardTitle>
          <div className="flex gap-2">
          {!readOnly && (
          <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
            <DialogTrigger asChild><Button size="sm" variant="outline" data-testid="bulk-costs-button"><Plus className="h-4 w-4 mr-1" /> Bulk Add</Button></DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="bulk-costs-dialog">
              <DialogHeader><DialogTitle className="font-heading">Bulk Add Expenses</DialogTitle></DialogHeader>
              <div className="space-y-3">
                {rows.map((r, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-3"><Label className="text-xs">Date</Label>
                      <DatePicker testid={`bulk-date-${i}`} value={r.date} onChange={(v) => setRows(rows.map((x, j) => j === i ? { ...x, date: v } : x))} /></div>
                    <div className="col-span-3"><Label className="text-xs">Category</Label>
                      <Select value={r.category} onValueChange={(v) => setRows(rows.map((x, j) => j === i ? { ...x, category: v } : x))}>
                        <SelectTrigger data-testid={`bulk-category-${i}`}><SelectValue /></SelectTrigger>
                        <SelectContent>{COST_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                      </Select></div>
                    <div className="col-span-3"><Label className="text-xs">Description</Label>
                      <Input data-testid={`bulk-desc-${i}`} value={r.description} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, description: e.target.value } : x))} /></div>
                    <div className="col-span-2"><Label className="text-xs">Amount</Label>
                      <Input data-testid={`bulk-amount-${i}`} type="number" step="0.01" value={r.amount} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} /></div>
                    <div className="col-span-1">
                      <Button type="button" variant="ghost" size="icon" data-testid={`bulk-remove-${i}`} onClick={() => setRows(rows.filter((_, j) => j !== i))} disabled={rows.length === 1}>
                        <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                    </div>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" data-testid="bulk-add-row"
                  onClick={() => setRows([...rows, { date: today(), category: "Site Acquisition", description: "", amount: "", paid_by: "" }])}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add row
                </Button>
                <Button data-testid="bulk-submit" className="w-full" onClick={submitBulk}>
                  Save All ({rows.filter((r) => Number(r.amount) > 0).length})
                </Button>
              </div>
            </DialogContent>
          </Dialog>)}
          {!readOnly && (
          <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditing(null); }}>
            <DialogTrigger asChild><Button size="sm" data-testid="add-cost-button"><Plus className="h-4 w-4 mr-1" /> Add Cost</Button></DialogTrigger>
            <DialogContent data-testid="add-cost-dialog">
              <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Cost</DialogTitle></DialogHeader>
              <form onSubmit={submit} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Date</Label>
                    <DatePicker testid="cost-date-input" value={form.date} onChange={(v) => setForm({ ...form, date: v })} /></div>
                  <div className="space-y-1.5"><Label>Category</Label>
                    <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                      <SelectTrigger data-testid="cost-category-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{COST_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Amount (AUD)</Label>
                    <Input data-testid="cost-amount-input" type="number" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
                  <div className="space-y-1.5"><Label>Paid by</Label>
                    <Select value={form.paid_by} onValueChange={(v) => setForm({ ...form, paid_by: v })}>
                      <SelectTrigger data-testid="cost-paidby-select"><SelectValue placeholder="—" /></SelectTrigger>
                      <SelectContent>{partnerNames.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                    </Select></div>
                </div>
                <div className="space-y-1.5"><Label>Description</Label>
                  <Input data-testid="cost-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
                <Button data-testid="cost-submit" type="submit" className="w-full">{editing ? "Save Changes" : "Save"}</Button>
              </form>
            </DialogContent>
          </Dialog>)}
          </div>
        </CardHeader>
        <CardContent>
          {costs.length === 0 ? <p className="text-sm text-muted-foreground">No costs recorded.</p> : (
            <DataTable testid="costs-table" head={["Date", "Category", "Description", "Paid By", "Amount", ""]}
              rows={costs.map((c) => (
                <tr key={c.id} className="border-b border-border/50" data-testid={`cost-row-${c.id}`}>
                  <td className="py-2.5 pr-4">{fmtDate(c.date)}</td>
                  <td className="py-2.5 pr-4 font-sans">{c.category}</td>
                  <td className="py-2.5 pr-4 font-sans">{c.description || "—"}</td>
                  <td className="py-2.5 pr-4 font-sans">{c.paid_by || "—"}</td>
                  <td className="py-2.5 pr-4 text-negative">{fmt2(c.amount)}</td>
                  <td className="py-2.5"><div className="flex">
                    {!readOnly && (<Button variant="ghost" size="icon" data-testid={`edit-cost-${c.id}`} title="Edit"
                      onClick={() => { setEditing(c.id); setForm({ date: c.date, category: c.category, amount: c.amount, description: c.description || "", paid_by: c.paid_by || "" }); setOpen(true); }}>
                      <Pencil className="h-3.5 w-3.5" /></Button>)}
                    {!readOnly && (<Button variant="ghost" size="icon" data-testid={`delete-cost-${c.id}`}
                      onClick={async () => { await api.delete(`/costs/${c.id}`); toast.success("Deleted"); reload(); }}>
                      <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>)}
                  </div></td>
                </tr>
              ))} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function LoansTab({ projectId, loans, reload, readOnly }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", lender: "", type: "interest_only", annual_rate: "", term_months: "", start_date: today(), first_amount: "", first_date: today() });

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        await api.put(`/loans/${editing}`, {
          name: form.name, lender: form.lender, type: form.type,
          annual_rate: Number(form.annual_rate), term_months: Number(form.term_months),
          start_date: form.start_date,
        });
      } else {
        const drawdowns = form.first_amount ? [{ date: form.first_date, amount: Number(form.first_amount), description: "Initial drawdown" }] : [];
        await api.post(`/projects/${projectId}/loans`, {
          name: form.name, lender: form.lender, type: form.type,
          annual_rate: Number(form.annual_rate), term_months: Number(form.term_months),
          start_date: form.start_date, drawdowns,
        });
      }
      toast.success(editing ? "Loan updated — repayments recalculated" : "Loan added");
      setOpen(false);
      setEditing(null);
      setForm({ name: "", lender: "", type: "interest_only", annual_rate: "", term_months: "", start_date: today(), first_amount: "", first_date: today() });
      reload();
    } catch (err) { toast.error(apiError(err)); }
  };

  const startEdit = (l) => {
    setEditing(l.id);
    setForm({ name: l.name, lender: l.lender || "", type: l.type, annual_rate: l.annual_rate, term_months: l.term_months, start_date: l.start_date, first_amount: "", first_date: today() });
    setOpen(true);
  };

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        {!readOnly && (
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditing(null); }}>
          <DialogTrigger asChild><Button size="sm" data-testid="add-loan-button"><Plus className="h-4 w-4 mr-1" /> Add Loan</Button></DialogTrigger>
          <DialogContent data-testid="add-loan-dialog">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Loan Facility</DialogTitle></DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Loan name</Label>
                  <Input data-testid="loan-name-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Construction Facility" /></div>
                <div className="space-y-1.5"><Label>Lender</Label>
                  <Input data-testid="loan-lender-input" value={form.lender} onChange={(e) => setForm({ ...form, lender: e.target.value })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Type</Label>
                  <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                    <SelectTrigger data-testid="loan-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="interest_only">Interest-only</SelectItem>
                      <SelectItem value="amortizing">Principal + Interest</SelectItem>
                    </SelectContent>
                  </Select></div>
                <div className="space-y-1.5"><Label>Annual rate %</Label>
                  <Input data-testid="loan-rate-input" type="number" step="0.01" required value={form.annual_rate} onChange={(e) => setForm({ ...form, annual_rate: e.target.value })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Term (months)</Label>
                  <Input data-testid="loan-term-input" type="number" required value={form.term_months} onChange={(e) => setForm({ ...form, term_months: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Start date</Label>
                  <DatePicker testid="loan-start-input" value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} /></div>
              </div>
              {!editing && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Initial drawdown (optional)</Label>
                  <Input data-testid="loan-first-amount-input" type="number" step="0.01" value={form.first_amount} onChange={(e) => setForm({ ...form, first_amount: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Drawdown date</Label>
                  <DatePicker testid="loan-first-date-input" value={form.first_date} onChange={(v) => setForm({ ...form, first_date: v })} /></div>
              </div>)}
              <Button data-testid="loan-submit" type="submit" className="w-full">{editing ? "Save Changes" : "Save Loan"}</Button>
            </form>
          </DialogContent>
        </Dialog>)}
      </div>

      {loans.length === 0 && (
        <Card><CardContent className="p-10 text-center text-muted-foreground">No loans yet. Add a facility to track drawdowns and repayments.</CardContent></Card>
      )}
      {loans.map((l) => <LoanCard key={l.id} loan={l} reload={reload} readOnly={readOnly} onEdit={startEdit} />)}
    </div>
  );
}

function LoanCard({ loan, reload, readOnly, onEdit }) {
  const [schedule, setSchedule] = useState(null);
  const [ddOpen, setDdOpen] = useState(false);
  const [ddEdit, setDdEdit] = useState(null);
  const [dd, setDd] = useState({ date: today(), amount: "", description: "" });
  const m = loan.metrics;

  const addDrawdown = async (e) => {
    e.preventDefault();
    try {
      if (ddEdit !== null) await api.put(`/loans/${loan.id}/drawdowns/${ddEdit}`, { ...dd, amount: Number(dd.amount) });
      else await api.post(`/loans/${loan.id}/drawdowns`, { ...dd, amount: Number(dd.amount) });
      toast.success(ddEdit !== null ? "Drawdown updated — repayments updated" : "Drawdown added — repayments updated");
      setDdOpen(false);
      setDdEdit(null);
      setDd({ date: today(), amount: "", description: "" });
      setSchedule(null);
      reload();
    } catch (err) { toast.error(apiError(err)); }
  };

  const toggleSchedule = async () => {
    if (schedule) { setSchedule(null); return; }
    const r = await api.get(`/loans/${loan.id}/schedule?months=12`);
    setSchedule(r.data.schedule);
  };

  return (
    <Card data-testid={`loan-card-${loan.id}`}>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-heading font-semibold text-lg">{loan.name}</h3>
            <p className="text-xs text-muted-foreground">
              {loan.lender && `${loan.lender} · `}{loan.type === "interest_only" ? "Interest-only" : "Principal + Interest"} · {loan.annual_rate}% p.a. · {loan.term_months} months · from {fmtDate(loan.start_date)}
            </p>
          </div>
          <div className="flex gap-1.5">
            {!readOnly && (
            <Dialog open={ddOpen} onOpenChange={(v) => { setDdOpen(v); if (!v) setDdEdit(null); }}>
              <DialogTrigger asChild><Button size="sm" variant="outline" data-testid={`add-drawdown-${loan.id}`}><Plus className="h-3.5 w-3.5 mr-1" /> Drawdown</Button></DialogTrigger>
              <DialogContent data-testid="add-drawdown-dialog">
                <DialogHeader><DialogTitle className="font-heading">{ddEdit !== null ? "Edit" : "Add"} Drawdown</DialogTitle></DialogHeader>
                <form onSubmit={addDrawdown} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5"><Label>Date</Label>
                      <DatePicker testid="drawdown-date-input" value={dd.date} onChange={(v) => setDd({ ...dd, date: v })} /></div>
                    <div className="space-y-1.5"><Label>Amount</Label>
                      <Input data-testid="drawdown-amount-input" type="number" step="0.01" required value={dd.amount} onChange={(e) => setDd({ ...dd, amount: e.target.value })} /></div>
                  </div>
                  <div className="space-y-1.5"><Label>Description</Label>
                    <Input data-testid="drawdown-description-input" value={dd.description} onChange={(e) => setDd({ ...dd, description: e.target.value })} /></div>
                  <Button data-testid="drawdown-submit" type="submit" className="w-full">{ddEdit !== null ? "Save Changes" : "Add Drawdown"}</Button>
                </form>
              </DialogContent>
            </Dialog>)}
            {!readOnly && (
            <Button size="sm" variant="ghost" data-testid={`edit-loan-${loan.id}`} title="Edit loan" onClick={() => onEdit(loan)}>
              <Pencil className="h-4 w-4" />
            </Button>)}
            <Button size="sm" variant="ghost" data-testid={`toggle-schedule-${loan.id}`} onClick={toggleSchedule}>
              {schedule ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
            {!readOnly && (
            <Button size="sm" variant="ghost" data-testid={`delete-loan-${loan.id}`}
              onClick={async () => { await api.delete(`/loans/${loan.id}`); toast.success("Loan deleted"); reload(); }}>
              <Trash2 className="h-4 w-4 text-negative" />
            </Button>)}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div><p className="label-overline">Drawn</p><p className="font-mono font-medium">{fmt(m.drawn)}</p></div>
          <div><p className="label-overline">Outstanding</p><p className="font-mono font-medium text-negative">{fmt(m.outstanding)}</p></div>
          <div><p className="label-overline">Repayment / mo</p><p className="font-mono font-semibold text-gold">{fmt2(m.monthly_payment)}</p></div>
          <div><p className="label-overline">Remaining</p><p className="font-mono font-medium">{m.remaining_months} / {loan.term_months} mo</p></div>
        </div>

        {loan.drawdowns?.length > 0 && (
          <div className="text-xs font-mono text-muted-foreground space-y-1">
            {loan.drawdowns.map((d, i) => (
              <div key={i} className="flex items-center justify-between gap-2" data-testid={`drawdown-row-${loan.id}-${i}`}>
                <p>· {fmtDate(d.date)} — {fmt2(d.amount)} {d.description && `(${d.description})`}</p>
                {!readOnly && (
                  <span className="flex shrink-0">
                    <Button variant="ghost" size="icon" className="h-6 w-6" data-testid={`edit-drawdown-${loan.id}-${i}`} title="Edit drawdown"
                      onClick={() => { setDdEdit(i); setDd({ date: d.date, amount: d.amount, description: d.description || "" }); setDdOpen(true); }}>
                      <Pencil className="h-3 w-3" /></Button>
                    <Button variant="ghost" size="icon" className="h-6 w-6" data-testid={`delete-drawdown-${loan.id}-${i}`} title="Remove drawdown"
                      onClick={async () => { await api.delete(`/loans/${loan.id}/drawdowns/${i}`); toast.success("Drawdown removed — repayments updated"); setSchedule(null); reload(); }}>
                      <Trash2 className="h-3 w-3 text-negative" /></Button>
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {schedule && (
          <DataTable testid={`loan-schedule-${loan.id}`} head={["Month", "Payment", "Interest", "Principal", "Balance"]}
            rows={schedule.map((s) => (
              <tr key={s.month} className="border-b border-border/50">
                <td className="py-2 pr-4">{s.month}</td>
                <td className="py-2 pr-4">{fmt2(s.payment)}</td>
                <td className="py-2 pr-4">{fmt2(s.interest)}</td>
                <td className="py-2 pr-4">{fmt2(s.principal)}</td>
                <td className="py-2">{fmt2(s.balance)}</td>
              </tr>
            ))} />
        )}
      </CardContent>
    </Card>
  );
}
