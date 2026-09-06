import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmt } from "../lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { TrendingUp, Building2, HardHat, Users, Wallet } from "lucide-react";

const COLORS = ["#D97706", "#059669", "#2563EB", "#8B5CF6"];

export default function Dashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/dashboard").then((r) => setData(r.data)).catch(() => {});
  }, []);

  if (!data) return <div className="text-muted-foreground" data-testid="dashboard-loading">Loading…</div>;

  const pie = [
    { name: "Investments", value: Math.max(0, data.investments.total) },
    { name: "Property Equity", value: Math.max(0, data.properties.equity) },
    { name: "Project Equity", value: Math.max(0, data.projects.equity) },
    { name: "Partner Receivables", value: Math.max(0, data.ledger_net) },
  ].filter((d) => d.value > 0);

  const cards = [
    { label: "Investments", value: data.investments.total, icon: TrendingUp, testid: "stat-investments" },
    { label: "Property Equity", value: data.properties.equity, icon: Building2, testid: "stat-property-equity" },
    { label: "Project Equity", value: data.projects.equity, icon: HardHat, testid: "stat-project-equity" },
    { label: "Partner Ledger Net", value: data.ledger_net, icon: Users, testid: "stat-ledger-net" },
  ];

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div>
        <p className="label-overline">Net Worth · AUD</p>
        <h1 className="font-heading font-extrabold text-3xl sm:text-4xl tracking-tight mt-1">
          <span className="font-mono" data-testid="net-worth-value">{fmt(data.net_worth)}</span>
        </h1>
        {data.rates?.fetched_at && (
          <p className="text-xs text-muted-foreground mt-1 font-mono" data-testid="fx-info">
            FX: 1 AUD = {data.rates.rates.USD?.toFixed(4)} USD · {data.rates.rates.INR?.toFixed(2)} INR
            {data.rates.stale ? " (stale)" : ""} · rates by exchangerate-api.com
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <Card key={c.label} className="card-hover" data-testid={c.testid}>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <p className="label-overline">{c.label}</p>
                <c.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className={`font-mono font-semibold text-xl sm:text-2xl mt-2 ${c.value < 0 ? "text-negative" : ""}`}>
                {fmt(c.value)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <Card className="lg:col-span-5" data-testid="allocation-chart-card">
          <CardHeader><CardTitle className="font-heading text-lg">Asset Allocation</CardTitle></CardHeader>
          <CardContent>
            {pie.length === 0 ? (
              <p className="text-sm text-muted-foreground">Add investments, properties or projects to see allocation.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={pie} dataKey="value" nameKey="name" innerRadius={60} outerRadius={95} paddingAngle={3}>
                    {pie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => fmt(v)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-7" data-testid="projects-summary-card">
          <CardHeader><CardTitle className="font-heading text-lg">Project Positions</CardTitle></CardHeader>
          <CardContent>
            {data.projects.list.length === 0 ? (
              <p className="text-sm text-muted-foreground">No projects yet. Create one from the Projects page.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left label-overline border-b border-border">
                      <th className="pb-2 pr-4">Project</th>
                      <th className="pb-2 pr-4">My %</th>
                      <th className="pb-2 pr-4">Contributed</th>
                      <th className="pb-2 pr-4">Loan Share</th>
                      <th className="pb-2">Equity</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {data.projects.list.map((p) => (
                      <tr key={p.id} className="border-b border-border/50" data-testid={`dashboard-project-row-${p.id}`}>
                        <td className="py-2.5 pr-4 font-sans font-medium">{p.name}</td>
                        <td className="py-2.5 pr-4">{p.my_percentage}%</td>
                        <td className="py-2.5 pr-4">{fmt(p.my_contributions)}</td>
                        <td className="py-2.5 pr-4 text-negative">{fmt(p.my_loan_share)}</td>
                        <td className={`py-2.5 ${p.equity < 0 ? "text-negative" : "text-positive"}`}>{fmt(p.equity)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card data-testid="property-summary-card">
          <CardContent className="p-5">
            <p className="label-overline flex items-center gap-2"><Wallet className="h-3.5 w-3.5" /> Properties</p>
            <p className="font-mono font-semibold text-xl mt-2">{fmt(data.properties.value)}</p>
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              Debt {fmt(data.properties.debt)} · Rent {fmt(data.properties.monthly_rent)}/mo
            </p>
          </CardContent>
        </Card>
        <Card data-testid="investment-breakdown-card">
          <CardContent className="p-5">
            <p className="label-overline">Investment Mix</p>
            <div className="mt-2 space-y-1 font-mono text-sm">
              <p>Shares: {fmt(data.investments.by_type.shares || 0)}</p>
              <p>Term Insurance: {fmt(data.investments.by_type.term_insurance || 0)}</p>
              <p>Other: {fmt(data.investments.by_type.other || 0)}</p>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="project-debt-card">
          <CardContent className="p-5">
            <p className="label-overline">Project Debt (My Share)</p>
            <p className="font-mono font-semibold text-xl mt-2 text-negative">{fmt(data.projects.my_loan_share)}</p>
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              Contributed {fmt(data.projects.my_contributions)}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
