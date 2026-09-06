import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "../lib/api";
import { fmt, PARTNERS } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { toast } from "sonner";
import { Plus, HardHat } from "lucide-react";

export default function Projects() {
  const [projects, setProjects] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", address: "", description: "" });
  const [pcts, setPcts] = useState({ Yash: 25, Sanjay: 25, Pranay: 25, Max: 25 });
  const navigate = useNavigate();

  const load = () => api.get("/projects").then((r) => setProjects(r.data)).catch(() => setProjects([]));
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/projects", {
        ...form,
        partners: PARTNERS.map((name) => ({ name, percentage: Number(pcts[name]) || 0 })),
      });
      toast.success("Project created");
      setOpen(false);
      setForm({ name: "", address: "", description: "" });
      load();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <div className="space-y-6" data-testid="projects-page">
      <div className="flex items-center justify-between">
        <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">Construction Projects</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="new-project-button"><Plus className="h-4 w-4 mr-1.5" /> New Project</Button>
          </DialogTrigger>
          <DialogContent data-testid="new-project-dialog">
            <DialogHeader><DialogTitle className="font-heading">New Project</DialogTitle></DialogHeader>
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
              <div className="space-y-2">
                <Label>Ownership %</Label>
                <div className="grid grid-cols-2 gap-3">
                  {PARTNERS.map((p) => (
                    <div key={p} className="flex items-center gap-2">
                      <span className="text-sm w-16">{p}</span>
                      <Input data-testid={`project-pct-${p.toLowerCase()}`} type="number" step="0.01" value={pcts[p]}
                        onChange={(e) => setPcts({ ...pcts, [p]: e.target.value })} />
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground font-mono">
                  Total: {PARTNERS.reduce((s, p) => s + (Number(pcts[p]) || 0), 0)}%
                </p>
              </div>
              <Button data-testid="project-create-submit" type="submit" className="w-full">Create Project</Button>
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
                <div>
                  <h3 className="font-heading font-semibold text-lg tracking-tight">{p.name}</h3>
                  {p.address && <p className="text-xs text-muted-foreground mt-0.5">{p.address}</p>}
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
