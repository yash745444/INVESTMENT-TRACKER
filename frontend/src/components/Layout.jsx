import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";
import { LayoutDashboard, HardHat, Users, TrendingUp, Building2, LogOut, Landmark } from "lucide-react";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: HardHat },
  { to: "/partners", label: "Partner Ledger", icon: Users },
  { to: "/investments", label: "Investments", icon: TrendingUp },
  { to: "/properties", label: "Properties", icon: Building2 },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [rates, setRates] = useState(null);

  useEffect(() => {
    api.get("/rates").then((r) => setRates(r.data)).catch(() => {});
  }, []);

  const doLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-background/80 border-b border-border">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
              <Landmark className="h-4 w-4 text-primary-foreground" />
            </div>
            <span className="font-heading font-bold text-lg tracking-tight">Wealth Command</span>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {rates && (
              <div className="hidden md:flex items-center gap-3 font-mono text-xs text-muted-foreground" data-testid="fx-ticker">
                <span>1 AUD = ${rates.rates.USD?.toFixed(3)} USD</span>
                <span className="text-border">|</span>
                <span>₹{rates.rates.INR?.toFixed(2)} INR</span>
                {rates.stale && <span className="text-gold">(stale)</span>}
              </div>
            )}
            <ThemeToggle />
            <Button data-testid="logout-button" variant="ghost" size="icon" onClick={doLogout} aria-label="Logout">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <nav className="md:hidden border-t border-border overflow-x-auto">
          <div className="flex px-2">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}
                data-testid={`nav-mobile-${n.label.toLowerCase().replace(/\s/g, "-")}`}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                    isActive ? "border-gold text-foreground" : "border-transparent text-muted-foreground"}`}
                style={({ isActive }) => isActive ? { borderColor: "hsl(var(--gold))" } : {}}>
                <n.icon className="h-3.5 w-3.5" />{n.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>
      <div className="max-w-[1400px] mx-auto flex">
        <aside className="hidden md:block w-56 shrink-0 border-r border-border min-h-[calc(100vh-4rem)] py-6 px-3 sticky top-16 self-start">
          <div className="space-y-1">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}
                data-testid={`nav-${n.label.toLowerCase().replace(/\s/g, "-")}`}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"}`}>
                <n.icon className="h-4 w-4" />{n.label}
              </NavLink>
            ))}
          </div>
          <div className="mt-8 px-3">
            <p className="label-overline">Signed in</p>
            <p className="text-sm font-medium mt-1 truncate" data-testid="user-email">{user?.email}</p>
          </div>
        </aside>
        <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
