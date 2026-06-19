import { Link } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";
import { rupees } from "../format";
import { Badge, Card, Money, Spinner, Stat } from "../ui";

export default function Dashboard() {
  const dash = useLoad(() => api.dashboard());
  const reminders = useLoad(() => api.reminders());
  const receivables = useLoad(() => api.receivables());

  return (
    <>
      <h1>Dashboard</h1>
      <p className="muted" style={{ marginTop: -4 }}>
        Where money comes from and where it goes — this period.
      </p>

      {dash.loading || !dash.data ? (
        <Spinner />
      ) : (
        <div className="grid cols-3" style={{ marginBottom: 16 }}>
          <Stat label="Income" value={dash.data.income} tone="pos" />
          <Stat label="Expenses" value={dash.data.expense} tone="neg" />
          <Stat label="Net profit" value={dash.data.net_profit} tone={dash.data.net_profit >= 0 ? "pos" : "neg"} />
        </div>
      )}

      <div className="grid cols-2">
        <Card>
          <div className="section-head"><h2>Account balances</h2><Link to="/journal">Journal →</Link></div>
          {dash.data?.account_balances.length ? (
            <table>
              <tbody>
                {dash.data.account_balances.map((a) => (
                  <tr key={a.account_id}>
                    <td>{a.name}</td>
                    <td className="num"><Money n={a.balance} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="list-empty">No accounts yet.</div>}
        </Card>

        <Card>
          <div className="section-head"><h2>Needs attention</h2><Badge tone="amber">{reminders.data?.length ?? 0}</Badge></div>
          {reminders.loading ? <Spinner /> : reminders.data?.length ? (
            <div className="grid" style={{ gap: 8 }}>
              {reminders.data.map((r, i) => (
                <div key={i} className="inline" style={{ justifyContent: "space-between" }}>
                  <span>{r.message}</span>
                  <Badge tone={r.severity === "high" ? "red" : "amber"}>{r.severity}</Badge>
                </div>
              ))}
            </div>
          ) : <div className="list-empty">All caught up ✓</div>}
        </Card>
      </div>

      <Card style={{ marginTop: 16 }}>
        <div className="section-head">
          <h2>Patients to chase</h2>
          <span className="muted">Total outstanding: {rupees(receivables.data?.total ?? 0)}</span>
        </div>
        {receivables.data?.rows.length ? (
          <table>
            <thead><tr><th>Patient</th><th className="num">Outstanding</th></tr></thead>
            <tbody>
              {receivables.data.rows.slice(0, 8).map((r) => (
                <tr key={r.patient_id}>
                  <td><Link to={`/patients/${r.patient_id}`}>{r.name}</Link></td>
                  <td className="num">{rupees(r.outstanding)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="list-empty">Nothing outstanding ✓</div>}
      </Card>
    </>
  );
}
