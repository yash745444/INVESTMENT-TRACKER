import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api, apiError } from "../lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { Check, X, Trash2 } from "lucide-react";

export default function Admin() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState(null);

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
                  <th className="pb-2 pr-4">Role</th><th className="pb-2 pr-4">Status</th><th className="pb-2">Actions</th>
                </tr></thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b border-border/50" data-testid={`user-row-${u.id}`}>
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-2">
                          {u.picture && <img src={u.picture} alt="" className="h-6 w-6 rounded-full" referrerPolicy="no-referrer" />}
                          <span className="font-medium">{u.name || "—"}</span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs">{u.email}</td>
                      <td className="py-2.5 pr-4">{u.role || "user"}</td>
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
                          {u.id !== user?.id && (
                            <Button size="sm" variant="ghost" data-testid={`delete-user-${u.id}`}
                              onClick={() => remove(u.id, u.email)}>
                              <Trash2 className="h-3.5 w-3.5 text-negative" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
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
