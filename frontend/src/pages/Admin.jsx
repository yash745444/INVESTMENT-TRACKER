import { Fragment, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api, apiError } from "../lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { toast } from "sonner";
import { Check, X, Trash2, SlidersHorizontal } from "lucide-react";

const ACCESS_MODULES = [
  ["dashboard", "Dashboard"], ["projects", "Projects"], ["feasibility", "Feasibility"],
  ["partners", "Partner Ledger"], ["loans", "Private Loans"], ["investments", "Investments"],
  ["properties", "Properties"],
];

export default function Admin() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState(null);
  const [linkNames, setLinkNames] = useState({});
  const [accOpen, setAccOpen] = useState(null);
  const [accEdit, setAccEdit] = useState({});

  const load = () => api.get("/admin/users").then((r) => setUsers(r.data)).catch((e) => {
    if (e?.response?.status === 403) navigate("/");
    else toast.error(apiError(e));
  });

  useEffect(() => {
    if (user && user.role !== "admin") { navigate("/"); return; }
    load();
  }, [user]);

  const setStatus = async (id, status) => {
    try {
      await api.post(`/admin/users/${id}/status`, { status });
      toast.success(`User ${status}`);
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const remove = async (id, email) => {
    if (!window.confirm(`Delete ${email} and ALL their data? This cannot be undone.`)) return;
    try {
      await api.delete(`/admin/users/${id}`);
      toast.success("User deleted");
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const badge = (status) => {
    const s = status || "approved";
    if (s === "approved") return <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-secondary text-positive">approved</span>;
    if (s === "pending") return <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-secondary text-gold">pending</span>;
    return <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-secondary text-negative">rejected</span>;
  };

  return (
    <div className="space-y-6" data-testid="admin-page">
      <h1 className="font-heading font-bold text-2xl sm:text-3xl tracking-tight">User Access</h1>
      <Card>
        <CardHeader><CardTitle className="font-heading text-lg">Access Requests & Users</CardTitle></CardHeader>
        <CardContent>
          {!users ? <p className="text-sm text-muted-foreground">Loading…</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="admin-users-table">
                <thead><tr className="text-left label-overline border-b border-border">
                  <th className="pb-2 pr-4">User</th><th className="pb-2 pr-4">Email</th>
                  <th className="pb-2 pr-4">Role</th><th className="pb-2 pr-4">Linked Partner</th><th className="pb-2 pr-4">Status</th><th className="pb-2">Actions</th>
                </tr></thead>
                <tbody>
                  {users.map((u) => (
                    <Fragment key={u.id}>
                    <tr className="border-b border-border/50" data-testid={`user-row-${u.id}`}>
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-2">
                          {u.picture && <img src={u.picture} alt="" className="h-6 w-6 rounded-full" referrerPolicy="no-referrer" />}
                          <span className="font-medium">{u.name || "—"}</span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs">{u.email}</td>
                      <td className="py-2.5 pr-4">{u.role || "user"}</td>
                      <td className="py-2.5 pr-4">
                        <div className="flex gap-1.5 items-center">
                          <Input className="h-8 w-28 text-xs" placeholder="e.g. Sanjay" data-testid={`partner-input-${u.id}`}
                            value={linkNames[u.id] ?? u.partner_name ?? ""}
                            onChange={(e) => setLinkNames({ ...linkNames, [u.id]: e.target.value })} />
                          <Button size="sm" variant="ghost" data-testid={`partner-save-${u.id}`}
                            onClick={async () => {
                              await api.post(`/admin/users/${u.id}/partner`, { partner_name: linkNames[u.id] ?? u.partner_name ?? "" });
                              toast.success("Partner linked");
                              load();
                            }}>Save</Button>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4" data-testid={`status-badge-${u.id}`}>{badge(u.status)}</td>
                      <td className="py-2.5">
                        <div className="flex gap-1">
                          {u.status === "pending" && (
                            <Button size="sm" variant="outline" data-testid={`approve-user-${u.id}`}
                              onClick={() => setStatus(u.id, "approved")}>
                              <Check className="h-3.5 w-3.5 mr-1 text-positive" /> Approve
                            </Button>
                          )}
                          {u.status !== "rejected" && u.id !== user?.id && (
                            <Button size="sm" variant="ghost" data-testid={`reject-user-${u.id}`}
                              onClick={() => setStatus(u.id, "rejected")}>
                              <X className="h-3.5 w-3.5 text-negative" />
                            </Button>
                          )}
                          {u.id !== user?.id && u.role !== "admin" && (
                            <Button size="sm" variant="outline" data-testid={`access-toggle-${u.id}`}
                              onClick={() => {
                                setAccOpen(accOpen === u.id ? null : u.id);
                                setAccEdit({ ...accEdit, [u.id]: Array.isArray(u.access) ? [...u.access] : ACCESS_MODULES.map((m) => m[0]) });
                              }}>
                              <SlidersHorizontal className="h-3.5 w-3.5 mr-1" /> Access
                            </Button>
                          )}
                          {u.id !== user?.id && (
                            <Button size="sm" variant="ghost" data-testid={`delete-user-${u.id}`}
                              onClick={() => remove(u.id, u.email)}>
                              <Trash2 className="h-3.5 w-3.5 text-negative" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {accOpen === u.id && (
                      <tr data-testid={`access-row-${u.id}`}>
                        <td colSpan={6} className="py-3">
                          <div className="flex items-center gap-2 flex-wrap rounded-lg border border-border p-3">
                            <span className="label-overline mr-1">Can access:</span>
                            {ACCESS_MODULES.map(([mod, label]) => {
                              const on = (accEdit[u.id] || []).includes(mod);
                              return (
                                <button key={mod} type="button" data-testid={`access-${u.id}-${mod}`}
                                  onClick={() => setAccEdit({ ...accEdit, [u.id]: on ? accEdit[u.id].filter((x) => x !== mod) : [...(accEdit[u.id] || []), mod] })}
                                  className={`text-xs font-mono px-2.5 py-1 rounded-full border transition-colors ${on ? "text-gold" : "border-border text-muted-foreground"}`}
                                  style={on ? { borderColor: "hsl(var(--gold))" } : {}}>
                                  {label}
                                </button>
                              );
                            })}
                            <Button size="sm" data-testid={`access-save-${u.id}`}
                              onClick={async () => {
                                try {
                                  await api.put(`/admin/users/${u.id}/access`, { access: accEdit[u.id] || [] });
                                  toast.success("Access updated");
                                  setAccOpen(null);
                                  load();
                                } catch (e) { toast.error(apiError(e)); }
                              }}>Save</Button>
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
