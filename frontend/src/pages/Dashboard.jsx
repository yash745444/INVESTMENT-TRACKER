import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { fmt, fmt2 } from "../lib/format";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { TrendingUp, Building2, HardHat, Users, Wallet, Lock, FileText } from "lucide-react";
import { PinUnlock } from "../components/PinUnlock";
import { isSharesUnlocked, setSharesUnlocked } from "../lib/sharesLock";

const COLORS = ["#D97706", "#059669", "#2563EB", "#8B5CF6"];

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [unlocked, setUnlocked] = useState(isSharesUnlocked());
  const [pinOpen, setPinOpen] = useState(false);
  const [withDebts, setWithDebts] = useState(true);
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState(null);
  const navigate = useNavigate();

  const load = () => api.get("/dashboard").then((r) => {
    setData(r.data);
    if ((r.data.investments.shares_total || 0) > 0) { setSharesUnlocked(); setUnlocked(true); }
  }).catch(() => {});
  useEffect(() => { load(); }, []);

  const openReport = async () => {
    const r = await api.get("/report/networth");
    setReport(r.data);
    setReportOpen(true);
  };

  const downloadReport = () => {
    if (!report) return;
    const f = (v) => v == null ? "••••" : `$${Number(v).toLocaleString("en-AU", { maximumFractionDigits: 0 })}`;
    let t = `NET WORTH REPORT — ${report.user.name} (${report.user.email})\nGenerated: ${new Date(report.generated_at).toLocaleString("en-AU")}\nBase currency: AUD\n\n== SUMMARY ==\nNet worth (with debts): ${f(report.summary.net_worth)}\nNet worth (without debts): ${f(report.summary.net_worth_without_debts)}\nTotal debts: ${f(report.summary.debts.total)} (property ${f(report.summary.debts.property_debt)} · project loans ${f(report.summary.debts.project_loans)} · private loans ${f(report.summary.debts.personal_loans)})\n\n== INVESTMENTS ==\n`;
    report.investments.forEach((i) => { t += `${i.name} (${i.type}): ${i.redacted ? "hidden" : `${i.native} ${i.currency} ≈ ${f(i.worth_aud)}`}\n`; });
    t += `\n== PROPERTIES ==\n`;
    report.properties.forEach((p) => { t += `${p.name}: value ${f(p.value)} ${p.currency}, debt ${f(p.debt)}, rent ${f(p.rent)}/mo, my share ${p.my_percentage}% → my equity ${f(p.my_equity_aud)}\n`; });
    t += `\n== PROJECTS ==\n`;
    report.projects.forEach((p) => { t += `${p.name}: my share ${p.my_percentage}%, invested ${f(p.my_contributions)}, my equity ${f(p.my_equity)}, loan share ${f(p.my_loan_share)}\n`; });
    if (report.private_loans.length) {
      t += `\n== PRIVATE LOANS (I owe) ==\n`;
      report.private_loans.forEach((l) => { t += `${l.lender}: ${f(l.amount)} (${l.type}) → return ${f(l.return_amount)}, total owed ${f(l.total_owed)}\n`; });
    }
    t += `\n== PARTNER POSITIONS ==\n`;
    Object.entries(report.ledger.company).forEach(([k, v]) => { if (Math.abs(v) > 0.005) t += `${k}: ${v > 0 ? "take from company" : "pay to company"} ${f(Math.abs(v))}\n`; });
    report.ledger.personal.forEach((d) => { t += `${d.debtor} owes ${d.creditor} ${f(d.amount)} (personal)\n`; });
    t += `\nFX: 1 AUD = ${report.rates.USD?.toFixed(4)} USD · ${report.rates.INR?.toFixed(2)} INR\n`;
    const url = URL.createObjectURL(new Blob([t], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url; a.download = `net-worth-report-${new Date().toISOString().slice(0, 10)}.txt`; a.click();
    URL.revokeObjectURL(url);
  };

  if (!data) return <div className="text-muted-foreground" data-testid="dashboard-loading">Loading…</div>;

  const sharesCount = data.investments.shares_count || 0;
  const invDisplay = data.investments.total;
  const netDisplay = withDebts ? data.net_worth : data.net_worth_without_debts;

  const pie = [
    { name: "Investments", value: Math.max(0, invDisplay) },
    { name: "Property Equity", value: Math.max(0, data.properties.equity) },
    { name: "Project Equity", value: Math.max(0, data.projects.equity) },
    { name: "Partner Receivables", value: Math.max(0, data.ledger_net) },
  ].filter((d) => d.value > 0);

  const cards = [
    { label: "Investments", value: invDisplay, icon: TrendingUp, testid: "stat-investments", path: "/investments", locked: !unlocked && sharesCount > 0 },
    { label: "Property Equity", value: data.properties.equity, icon: Building2, testid: "stat-property-equity", path: "/properties" },
    { label: "Project Invested", value: data.projects.my_contributions, icon: HardHat, testid: "stat-project-invested", path: "/projects" },
    { label: "Partner Ledger Net", value: data.ledger_net, icon: Users, testid: "stat-ledger-net", path: "/partners" },
  ];

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div>
        <p className="label-overline">Net Worth · AUD</p>
        <div className="flex items-center gap-3 mt-1 flex-wrap">
          <h1 className="font-heading font-extrabold text-3xl sm:text-4xl tracking-tight">
            <span className="font-mono" data-testid="net-worth-value">{fmt(netDisplay)}</span>
          </h1>
          <div className="flex rounded-full border border-border overflow-hidden text-xs font-mono" data-testid="networth-toggle">
            <button onClick={() => setWithDebts(true)} data-testid="nw-with-debts"
              className={`px-3 py-1.5 transition-colors ${withDebts ? "bg-secondary text-foreground" : "text-muted-foreground"}`}>With debts</button>
            <button onClick={() => setWithDebts(false)} data-testid="nw-without-debts"
              className={`px-3 py-1.5 transition-colors ${!withDebts ? "bg-secondary text-foreground" : "text-muted-foreground"}`}>Without debts</button>
          </div>
          <button data-testid="networth-report-button" onClick={openReport}
            className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground border border-border rounded-full px-3 py-1.5 hover:border-gold transition-colors">
            <FileText className="h-3 w-3" /> Net worth report
          </button>
          {!unlocked && sharesCount > 0 && (
            <button data-testid="unlock-shares-button" onClick={() => setPinOpen(true)}
              className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground border border-border rounded-full px-3 py-1.5 hover:border-gold transition-colors">
              <Lock className="h-3 w-3" /> Reveal shares
            </button>
          )}
        </div>
        {!unlocked && sharesCount > 0 && (
          <p className="text-xs text-muted-foreground mt-1" data-testid="shares-hidden-note">Excludes shares — enter passcode to reveal</p>
        )}
        {data.rates?.fetched_at && (
          <p className="text-xs text-muted-foreground mt-1 font-mono" data-testid="fx-info">
            FX: 1 AUD = {data.rates.rates.USD?.toFixed(4)} USD · {data.rates.rates.INR?.toFixed(2)} INR
            {data.rates.stale ? " (stale)" : ""} · rates by exchangerate-api.com
          </p>
        )}
        {withDebts && data.debts?.total > 0 && (
          <p className="text-xs text-muted-foreground mt-1 font-mono" data-testid="debts-breakdown">
            Debts: property {fmt(data.debts.property_debt)} · project loans {fmt(data.debts.project_loans)} · private loans {fmt(data.debts.personal_loans)}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <Card key={c.label} className="card-hover cursor-pointer" data-testid={c.testid} onClick={() => navigate(c.path)}>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <p className="label-overline">{c.label}</p>
                <c.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className={`font-mono font-semibold text-xl sm:text-2xl mt-2 ${c.value < 0 ? "text-negative" : ""}`}>
                {fmt(c.value)}
              </p>
              {c.locked && <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><Lock className="h-3 w-3" /> excl. hidden shares</p>}
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
                      <th className="pb-2 pr-4">Invested</th>
                      <th className="pb-2 pr-4">My Equity</th>
                      <th className="pb-2">Loans Outstanding</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {data.projects.list.map((p) => (
                      <tr key={p.id} className="border-b border-border/50" data-testid={`dashboard-project-row-${p.id}`}>
                        <td className="py-2.5 pr-4 font-sans font-medium">{p.name}</td>
                        <td className="py-2.5 pr-4">{p.my_percentage}%</td>
                        <td className="py-2.5 pr-4 text-positive">{fmt(p.my_contributions)}</td>
                        <td className={`py-2.5 pr-4 ${p.my_equity < 0 ? "text-negative" : "text-positive"}`}>{fmt(p.my_equity)}</td>
                        <td className="py-2.5 text-muted-foreground">{fmt(p.loan_outstanding)}</td>
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
              <p data-testid="investment-mix-shares">Shares: {unlocked ? fmt(data.investments.by_type.shares || 0) : "••••"}</p>
              <p>Term Insurance: {fmt(data.investments.by_type.term_insurance || 0)}</p>
              <p>Other: {fmt(data.investments.by_type.other || 0)}</p>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="project-debt-card">
          <CardContent className="p-5">
            <p className="label-overline">Project Loans Outstanding</p>
            <p className="font-mono font-semibold text-xl mt-2 text-negative">{fmt(data.projects.loans_outstanding)}</p>
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              Info only — not deducted from net worth
            </p>
          </CardContent>
        </Card>
      </div>

      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="networth-report-dialog">
          <DialogHeader><DialogTitle className="font-heading">Net Worth Report</DialogTitle></DialogHeader>
          {report && (
            <div className="space-y-4 text-sm">
              <div>
                <p className="label-overline mb-1.5">Summary</p>
                <p className="font-mono" data-testid="report-nw">With debts: <b>{fmt(report.summary.net_worth)}</b></p>
                <p className="font-mono">Without debts: <b>{fmt(report.summary.net_worth_without_debts)}</b></p>
                <p className="font-mono text-negative text-xs">Debts: {fmt(report.summary.debts.total)}</p>
              </div>
              {[
                ["Investments", report.investments, (i) => `${i.name} — ${i.redacted ? "hidden" : `${fmt2(i.native, i.currency)} ≈ ${fmt(i.worth_aud)}`}`],
                ["Properties", report.properties, (p) => `${p.name} — equity ${fmt(p.my_equity_aud)} (${p.my_percentage}%) · rent ${fmt(p.rent, p.currency)}/mo`],
                ["Projects", report.projects, (p) => `${p.name} — ${p.my_percentage}% · invested ${fmt(p.my_contributions)} · equity ${fmt(p.my_equity)}`],
                ["Private Loans", report.private_loans, (l) => `${l.lender} — ${fmt(l.amount)} · owed ${fmt(l.total_owed)}`],
              ].map(([title, items, render]) => (
                <div key={title}>
                  <p className="label-overline mb-1.5">{title}</p>
                  {items.length === 0 ? <p className="text-muted-foreground text-xs">None.</p> :
                    items.map((it, idx) => <p key={idx} className="font-mono text-xs py-0.5">{render(it)}</p>)}
                </div>
              ))}
              <div>
                <p className="label-overline mb-1.5">Partner Positions</p>
                {Object.entries(report.ledger.company).filter(([, v]) => Math.abs(v) > 0.005).map(([k, v]) => (
                  <p key={k} className="font-mono text-xs">{k}: {v > 0 ? "Take from Company" : "Pay to Company"} {fmt(Math.abs(v))}</p>
                ))}
                {report.ledger.personal.map((d) => (
                  <p key={d.debtor + d.creditor} className="font-mono text-xs">{d.debtor} owes {d.creditor} {fmt(d.amount)} (personal)</p>
                ))}
              </div>
              <Button data-testid="download-networth-report" onClick={downloadReport} className="w-full">Download (.txt)</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <PinUnlock open={pinOpen} onOpenChange={setPinOpen} onUnlock={() => { setUnlocked(true); load(); }} />
    </div>
  );
}
