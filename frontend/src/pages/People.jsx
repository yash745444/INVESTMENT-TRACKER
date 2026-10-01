import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api, apiError } from "../lib/api";
import { fmt2 } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Checkbox } from "../components/ui/checkbox";
import { Card, CardContent } from "../components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, Eye } from "lucide-react";

const VIS_FIELDS = [
  ["projects", "Projects & shares"],
  ["properties", "Properties"],
  ["debts", "Debts & positions"],
  ["loans", "Private loans (as lender)"],
];
const EMPTY = { name: "", email: "", visibility: { projects: true, properties: true, debts: true, loans: true } };

export default function People() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [people, setPeople] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [profile, setProfile] = useState(null);

  const load = () => api.get("/people").then((r) => setPeople(r.data)).catch(() => setPeople([]));
  useEffect(() => {
    if (user && user.role !== "admin") { navigate("/partners"); return; }
    load();
  }, [user]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editing) await api.put(`/people/${editing}`, form);
      else await api.post("/people", form);
      toast.success(editing ? "Person updated" : "Person added");
      setOpen(false); setEditing(null); setForm(EMPTY);
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  const viewProfile = async (id) => {
    try {
      const r = await api.get(`/people/${id}/profile`);
      setProfile(r.data);
    } catch (err) { toast.error(apiError(err)); }
  };

  return (
    <div className="space-y-6" data-testid="people-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">People</h1>
          <p className="text-sm text-muted-foreground mt-1">Individual financial profiles. Add someone once, pick their name anywhere, and control exactly what they see when they get access.</p>
        </div>
        <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setEditing(null); setForm(EMPTY); } }}>
          <DialogTrigger asChild><Button data-testid="add-person-button"><Plus className="h-4 w-4 mr-1.5" /> Add Person</Button></DialogTrigger>
          <DialogContent data-testid="person-dialog">
            <DialogHeader><DialogTitle className="font-heading">{editing ? "Edit" : "Add"} Person</DialogTitle></DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5"><Label>Name</Label>
                <Input data-testid="person-name-input" required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Sanjay" /></div>
              <div className="space-y-1.5"><Label>Email (optional — link when they get access)</Label>
                <Input data-testid="person-email-input" type="email" value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="their@gmail.com" /></div>
              <div className="space-y-2">
                <Label>What they can see when they log in</Label>
                {VIS_FIELDS.map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2.5 text-sm cursor-pointer">
                    <Checkbox data-testid={`vis-${key}`} checked={form.visibility[key] !== false}
                      onCheckedChange={(c) => setForm({ ...form, visibility: { ...form.visibility, [key]: !!c } })} />
                    {label}
                  </label>
                ))}
              </div>
              <Button data-testid="person-submit" type="submit" className="w-full">Save</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {!people ? <p className="text-muted-foreground">Loading…</p> : people.length === 0 ? (
        <Card><CardContent className="p-10 text-center text-muted-foreground">
          No people yet. Add your partners and lenders to build their individual profiles.
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {people.map((p) => (
            <Card key={p.id} className="card-hover" data-testid={`person-card-${p.id}`}>
              <CardContent className="p-5 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-heading font-semibold text-lg tracking-tight">{p.name}</h3>
                    {p.email && <p className="text-xs text-muted-foreground font-mono mt-0.5">{p.email}</p>}
                  </div>
                  <div className="flex shrink-0">
                    <Button variant="ghost" size="icon" data-testid={`profile-person-${p.id}`} onClick={() => viewProfile(p.id)}>
                      <Eye className="h-3.5 w-3.5" /></Button>
                    <Button variant="ghost" size="icon" data-testid={`edit-person-${p.id}`}
                      onClick={() => { setEditing(p.id); setForm({ name: p.name, email: p.email || "", visibility: { ...EMPTY.visibility, ...(p.visibility || {}) } }); setOpen(true); }}>
                      <Pencil className="h-3.5 w-3.5" /></Button>
                    <Button variant="ghost" size="icon" data-testid={`delete-person-${p.id}`}
                      onClick={async () => { await api.delete(`/people/${p.id}`); toast.success("Deleted"); load(); }}>
                      <Trash2 className="h-3.5 w-3.5 text-negative" /></Button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {VIS_FIELDS.map(([k, l]) => p.visibility?.[k] !== false && (
                    <span key={k} className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-secondary">{l}</span>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!profile} onOpenChange={() => setProfile(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="person-profile-dialog">
          <DialogHeader><DialogTitle className="font-heading">{profile?.name} — Financial Profile</DialogTitle></DialogHeader>
          {profile && (
            <div className="space-y-4">
              <div>
                <p className="label-overline mb-1.5">Company position</p>
                <p className={`font-mono text-sm font-semibold ${profile.position < 0 ? "text-negative" : "text-positive"}`} data-testid="person-position">
                  {Math.abs(profile.position) < 0.005 ? "Settled" : profile.position > 0 ? `Take from Company ${fmt2(profile.position)}` : `Pay to Company ${fmt2(-profile.position)}`}
                </p>
              </div>
              <div>
                <p className="label-overline mb-1.5">Projects</p>
                {profile.projects.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> :
                  profile.projects.map((x) => (
                    <p key={x.id} className="text-sm font-mono" data-testid={`person-project-${x.id}`}>
                      {x.name} · {x.percentage}% · invested {fmt2(x.contributed)}
                    </p>
                  ))}
              </div>
              <div>
                <p className="label-overline mb-1.5">Properties</p>
                {profile.properties.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> :
                  profile.properties.map((x) => (
                    <p key={x.id} className="text-sm font-mono" data-testid={`person-property-${x.id}`}>
                      {x.name} · {x.percentage}% · equity share {fmt2(x.equity_share)}
                    </p>
                  ))}
              </div>
              <div>
                <p className="label-overline mb-1.5">Personal debts</p>
                {profile.personal.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> :
                  profile.personal.map((d) => (
                    <p key={`${d.debtor}-${d.creditor}`} className="text-sm font-mono">
                      {d.debtor} owes {d.creditor} {fmt2(d.amount)}
                    </p>
                  ))}
              </div>
              <div>
                <p className="label-overline mb-1.5">Private loans (as lender)</p>
                {profile.loans.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> :
                  profile.loans.map((l) => (
                    <p key={l.id} className="text-sm font-mono" data-testid={`person-loan-${l.id}`}>
                      {fmt2(l.amount)} · {l.type === "interest" ? `${l.annual_rate}% p.a.` : "profit share"} · return {fmt2(l.computed.return_amount)}
                    </p>
                  ))}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
