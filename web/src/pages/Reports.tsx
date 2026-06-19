import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { firstOfMonth, lastOfMonth, rupees } from "../format";
import { Card, Spinner } from "../ui";

export default function Reports() {
  const [start, setStart] = useState(firstOfMonth());
  const [end, setEnd] = useState(lastOfMonth());
  const pnl = useLoad(() => api.pnl(`?start=${start}&end=${end}`), [start, end]);
  const byCat = useLoad(() => api.byCategory());
  const byProc = useLoad(() => api.byProcedure());
  const byCol = useLoad(() => api.byCollector());
  const perPartner = useLoad(() => api.perPartner());
  const trends = useLoad(() => api.trends());

  return (
    <>
      <h1>Reports</h1>

      <Card style={{ marginBottom: 16 }}>
        <div className="section-head"><h2>P&amp;L for a range</h2></div>
        <div className="row" style={{ marginBottom: 12 }}>
          <label className="field">Start<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label className="field">End<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
        {pnl.data && (
          <div className="grid cols-3">
            <div className="stat card"><span className="label">Income</span><span className="value pos">{rupees(pnl.data.income)}</span></div>
            <div className="stat card"><span className="label">Expenses</span><span className="value neg">{rupees(pnl.data.expense)}</span></div>
            <div className="stat card"><span className="label">Net</span><span className={`value ${pnl.data.net_profit >= 0 ? "pos" : "neg"}`}>{rupees(pnl.data.net_profit)}</span></div>
          </div>
        )}
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <h2>Month-over-month trend</h2>
        {trends.loading ? <Spinner /> : trends.data?.length ? (
          <table>
            <thead><tr><th>Month</th><th className="num">Income</th><th className="num">Expense</th><th className="num">Net</th></tr></thead>
            <tbody>{trends.data.map((t) => (
              <tr key={t.month}><td>{t.month}</td><td className="num">{rupees(t.income)}</td><td className="num">{rupees(t.expense)}</td><td className="num">{rupees(t.net_profit)}</td></tr>
            ))}</tbody>
          </table>
        ) : <div className="list-empty">No data yet.</div>}
      </Card>

      <div className="grid cols-2">
        <Card>
          <h2>Where money goes (by category)</h2>
          <Rows rows={byCat.data?.map((c) => [c.name, c.total]) ?? []} loading={byCat.loading} />
        </Card>
        <Card>
          <h2>Where money comes from (by procedure)</h2>
          {byProc.loading ? <Spinner /> : byProc.data?.length ? (
            <table><thead><tr><th>Procedure</th><th className="num">Count</th><th className="num">Revenue</th></tr></thead>
              <tbody>{byProc.data.map((p) => <tr key={p.procedure_name}><td>{p.procedure_name}</td><td className="num">{p.count}</td><td className="num">{rupees(p.revenue)}</td></tr>)}</tbody></table>
          ) : <div className="list-empty">No data.</div>}
        </Card>
        <Card>
          <h2>Collected by partner</h2>
          <Rows rows={byCol.data?.map((c) => [c.name, c.collected]) ?? []} loading={byCol.loading} />
        </Card>
        <Card>
          <h2>Per-partner contribution</h2>
          {perPartner.loading ? <Spinner /> : perPartner.data?.length ? (
            <table><thead><tr><th>Partner</th><th className="num">Collected</th><th className="num">Paid</th><th className="num">Entitled</th></tr></thead>
              <tbody>{perPartner.data.map((p) => <tr key={p.partner_id}><td>{p.name}</td><td className="num">{rupees(p.collected)}</td><td className="num">{rupees(p.paid)}</td><td className="num">{rupees(p.entitled)}</td></tr>)}</tbody></table>
          ) : <div className="list-empty">No data.</div>}
        </Card>
      </div>
    </>
  );
}

function Rows({ rows, loading }: { rows: [string, number][]; loading: boolean }) {
  if (loading) return <Spinner />;
  if (!rows.length) return <div className="list-empty">No data.</div>;
  return (
    <table><tbody>{rows.map(([name, val], i) => (
      <tr key={i}><td>{name}</td><td className="num">{rupees(val)}</td></tr>
    ))}</tbody></table>
  );
}
