import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { fmt } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { toast } from "sonner";
import { Plus, HardHat, X, Trash2, Pencil } from "lucide-react";

const DEFAULT_PARTNERS = [
  { name: "Yash Sojitra", percentage: 25, email: "" }, { name: "Sanjay Jogani", percentage: 25, email: "" },
  { name: "Pranay Jetani", percentage: 25, email: "" }, { name: "Max Ma", percentage: 25, email: "" },
];

export default function Projects() {
  const [projects, setProjects] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", address: "", description: "", current_value: "" });
  const [partnerRows, setPartnerRows] = useState(DEFAULT_PARTNERS);
  const [people, setPeople] = useState([]);
  const navigate = useNavigate();

  const load = () => api.get("/projects").then((r) => setProjects(r.data)).catch(() => setProjects([]));
  useEffect(() => { load(); api.get("/people").then((r) => setPeople(r.data)).catch(() => {}); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...form,
        partners: partnerRows.filter((r) => r.name.trim()).map((r) => ({ name: r.name.trim(), percentage: Number(r.percentage) || 0, email: (r.email || "").trim() })),
        current_value: Number(form.current_value) || 0,
      };
      if (editing) {
        payload.status = editing.status || "active";
        payload.final_profit = Number(editing.final_profit) || 0;
        await api.put(`/projects/${editing.id}`, payload);
      } else {
        await api.post("/projects", payload);
      }
      toast.success(editing ? "Project updated" : "Project created");
      setOpen(false);
      setEditing(null);
      setForm({ name: "", address: "", description: "", current_value: "" });
      setPartnerRows(DEFAULT_PARTNERS);
      load();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <div className="space-y-6" data-testid="projects-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Construction Projects</h1>
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm({ name: "", address: "", description: "" }); setPartnerRows(DEFAULT_PARTNERS); } }}>
          <DialogTrigger asChild>
            <Button data-testid="new-project-button"><Plus className="h-4 w-4 mr-1.5" /> New Project</Button>
          </DialogTrigger>
          <DialogContent className="max-h-[85vh] overflow-y-auto" data-testid="new-project-dialog">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "New"} Project</DialogTitle></DialogHeader>
            <form onSubmit={create} className="space-y-4">
              <div className="space-y-1.5">
                <Label>Project name</Label>
                <Input data-testid="project-name-input" required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="32-34 Cadman" />
              </div>
              <div className="space-y-1.5">
                <Label>Address</Label>
                <Input data-testid="project-address-input" value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Input data-testid="project-description-input" value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>Current project value (AUD, as at now)</Label>
                <Input data-testid="project-value-input" type="number" step="0.01" value={form.current_value}
                  onChange={(e) => setForm({ ...form, current_value: e.target.value })} placeholder="e.g. 5200000" />
              </div>
              <div className="space-y-2">
                <Label>Ownership %</Label>
                <datalist id="people-names-list">
                  {people.map((p) => <option key={p.id} value={p.name} />)}
                </datalist>
                <div className="space-y-2">
                  {partnerRows.map((row, i) => (
                    <div key={i} className="space-y-1.5">
                      <div className="flex items-center gap-2">
                        <Input data-testid={`project-partner-name-${i}`} value={row.name} placeholder="Partner name" list="people-names-list"
                          onChange={(e) => setPartnerRows(partnerRows.map((r, j) => j === i ? { ...r, name: e.target.value } : r))} />
                        <Input data-testid={`project-partner-pct-${i}`} type="number" step="0.01" className="w-24 shrink-0" value={row.percentage}
                          onChange={(e) => setPartnerRows(partnerRows.map((r, j) => j === i ? { ...r, percentage: e.target.value } : r))} />
                        {partnerRows.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" data-testid={`project-partner-remove-${i}`}
                            onClick={() => setPartnerRows(partnerRows.filter((_, j) => j !== i))}>
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                      <Input data-testid={`project-partner-email-${i}`} value={row.email || ""} className="text-xs"
                        placeholder="Partner email (optional — links their account to this project)"
                        onChange={(e) => setPartnerRows(partnerRows.map((r, j) => j === i ? { ...r, email: e.target.value } : r))} />
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between">
                  <Button type="button" variant="outline" size="sm" data-testid="project-add-partner"
                    onClick={() => setPartnerRows([...partnerRows, { name: "", percentage: 0 }])}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add partner
                  </Button>
                  <p className="text-xs text-muted-foreground font-mono" data-testid="project-pct-total">
                    Total: {partnerRows.reduce((s, r) => s + (Number(r.percentage) || 0), 0)}%
                  </p>
                </div>
              </div>
              <Button data-testid="project-create-submit" type="submit" className="w-full">{editing ? "Save Changes" : "Create Project"}</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {!projects ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : projects.length === 0 ? (
        <Card><CardContent className="p-10 text-center text-muted-foreground">
          <HardHat className="h-8 w-8 mx-auto mb-3 opacity-40" />
          No projects yet. Create your first project to start tracking.
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {projects.map((p) => (
            <Card key={p.id} className="card-hover cursor-pointer" data-testid={`project-card-${p.id}`}
              onClick={() => navigate(`/projects/${p.id}`)}>
              <CardContent className="p-5 space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-heading font-semibold text-lg tracking-tight">{p.name}</h3>
                    {p.address && <p className="text-xs text-muted-foreground mt-0.5">{p.address}</p>}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {p.shared && <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border text-gold" style={{ borderColor: "hsl(var(--gold))" }} data-testid={`project-shared-${p.id}`}>Shared</span>}
                    {!p.shared && (
                      <Button variant="ghost" size="icon" data-testid={`edit-project-${p.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditing(p);
                          setForm({ name: p.name, address: p.address || "", description: p.description || "", current_value: p.current_value || "" });
                          setPartnerRows(p.partners?.length ? p.partners.map((pt) => ({ name: pt.name, percentage: pt.percentage, email: pt.email || "" })) : [{ name: "", percentage: 0, email: "" }]);
                          setOpen(true);
                        }}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                    )}
                    {!p.shared && (
                      <Button variant="ghost" size="icon" data-testid={`delete-project-${p.id}`}
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (!window.confirm(`Delete project "${p.name}" and all its records?`)) return;
                          await api.delete(`/projects/${p.id}`);
                          toast.success("Project deleted");
                          load();
                        }}>
                        <Trash2 className="h-4 w-4 text-negative" />
                      </Button>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="label-overline">Contributed</p>
                    <p className="font-mono font-medium">{fmt(p.totals.contributions)}</p></div>
                  <div><p className="label-overline">Costs</p>
                    <p className="font-mono font-medium">{fmt(p.totals.costs)}</p></div>
                  <div><p className="label-overline">Loan Outstanding</p>
                    <p className="font-mono font-medium text-negative">{fmt(p.totals.outstanding)}</p></div>
                  <div><p className="label-overline">Repayment/mo</p>
                    <p className="font-mono font-medium">{fmt(p.totals.monthly_repayment)}</p></div>
                  <div><p className="label-overline">Project Value</p>
                    <p className="font-mono font-medium text-gold" data-testid={`project-value-${p.id}`}>{p.current_value ? fmt(p.current_value) : "—"}</p></div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {p.partners?.map((pt) => (
                    <span key={pt.name} className="text-xs font-mono px-2 py-0.5 rounded-full bg-secondary">
                      {pt.name} {pt.percentage}%
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
