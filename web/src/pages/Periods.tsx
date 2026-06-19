import { useState } from "react";
import { api, downloadFile } from "../api";
import { useLoad } from "../hooks";
import { firstOfMonth, lastOfMonth, rupees, today } from "../format";
import { Badge, Card, Field, Money, Spinner, useToast } from "../ui";
import type { SettlementObligation, SettlementStatement } from "../types";

export default function Periods() {
  const toast = useToast();
  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const periods = useLoad(() => api.periods());
  const settlements = useLoad(() => api.settlements());

  const [start, setStart] = useState(firstOfMonth());
  const [end, setEnd] = useState(lastOfMonth());
  const [pay, setPay] = useState<{ stmt: number; ob: SettlementObligation } | null>(null);
  const [payForm, setPayForm] = useState({ from: "", to: "", date: today() });

  const parName = (id: number) => partners.data?.find((p) => p.id === id)?.name ?? `#${id}`;

  function reloadAll() { periods.reload(); settlements.reload(); }

  async function createPeriod(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createPeriod({ start_date: start, end_date: end });
      periods.reload();
      toast.show("Period opened", "ok");
    } catch (e2: any) { toast.show(e2?.message ?? "Failed", "error"); }
  }

  async function close(id: number) {
    if (!confirm("Close this period? Its entries will be locked and a settlement statement produced.")) return;
    try {
      await api.closePeriod(id);
      reloadAll();
      toast.show("Period closed & settled", "ok");
    } catch (e2: any) { toast.show(e2?.message ?? "Failed", "error"); }
  }

  async function recordPayment(e: React.FormEvent) {
    e.preventDefault();
    if (!pay) return;
    try {
      await api.recordSettlementPayment(pay.stmt, {
        obligation_id: pay.ob.id, from_account_id: Number(payForm.from), to_account_id: Number(payForm.to), date: payForm.date,
      });
      setPay(null);
      settlements.reload();
      toast.show("Settlement payment recorded", "ok");
    } catch (e2: any) { toast.show(e2?.message ?? "Failed", "error"); }
  }

  return (
    <>
      <h1>Close &amp; settle</h1>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card>
          <h2>Open a period</h2>
          <form onSubmit={createPeriod}>
            <div className="row">
              <Field label="Start"><input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
              <Field label="End"><input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
            </div>
            <button>Open period</button>
          </form>
        </Card>
        <Card>
          <h2>Periods</h2>
          {periods.loading ? <Spinner /> : periods.data?.length ? (
            <table>
              <tbody>
                {periods.data.map((p) => (
                  <tr key={p.id}>
                    <td>{p.start_date} → {p.end_date}</td>
                    <td><Badge tone={p.status === "open" ? "amber" : "gray"}>{p.status}</Badge></td>
                    <td className="num">
                      {p.status === "open"
                        ? <button className="sm" onClick={() => close(p.id)}>Close &amp; settle</button>
                        : <button className="ghost sm" onClick={() => downloadFile(`/exports/periods/${p.id}/summary.pdf`, `summary-${p.id}.pdf`)}>PDF</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="list-empty">No periods yet.</div>}
        </Card>
      </div>

      <h2>Settlement history</h2>
      {settlements.loading ? <Spinner /> : settlements.data?.length ? (
        settlements.data.map((s: SettlementStatement) => (
          <Card key={s.id} style={{ marginBottom: 14 }}>
            <div className="section-head">
              <h3>Statement #{s.id}</h3>
              <span className="muted">Net profit {rupees(s.profit)} · joint pool {rupees(s.joint_standing)} (standing)</span>
            </div>
            <table>
              <thead><tr><th>Partner</th><th className="num">Personal profit</th><th className="num">Settlement</th></tr></thead>
              <tbody>
                {s.balances.map((b) => (
                  <tr key={b.partner_id}>
                    <td>{parName(b.partner_id)}</td>
                    <td className="num">{rupees(b.personal_profit)}</td>
                    <td className="num">
                      {b.settlement_balance > 0 ? <Badge tone="red">pays {rupees(b.settlement_balance)}</Badge>
                        : b.settlement_balance < 0 ? <Badge tone="green">owed {rupees(-b.settlement_balance)}</Badge>
                        : <Badge tone="gray">even</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {s.obligations.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <h3>Who pays whom</h3>
                {s.obligations.map((o) => (
                  <div key={o.id} className="inline" style={{ justifyContent: "space-between", padding: "6px 0" }}>
                    <span>{parName(o.from_partner_id)} → {parName(o.to_partner_id)}: <Money n={o.amount} /></span>
                    {o.paid ? <Badge tone="green">paid</Badge>
                      : <button className="sm" onClick={() => { setPay({ stmt: s.id, ob: o }); setPayForm({ from: "", to: "", date: today() }); }}>Record payment</button>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))
      ) : <div className="list-empty">No settlements yet. Close a period to produce one.</div>}

      {pay && (
        <Card style={{ position: "fixed", bottom: 20, right: 20, width: 360, boxShadow: "var(--shadow)" }}>
          <div className="section-head"><h3>Record settlement payment</h3><button className="ghost sm" onClick={() => setPay(null)}>✕</button></div>
          <p className="muted" style={{ marginTop: 0 }}>{parName(pay.ob.from_partner_id)} pays {parName(pay.ob.to_partner_id)} {rupees(pay.ob.amount)}</p>
          <form onSubmit={recordPayment}>
            <Field label="From account"><select value={payForm.from} onChange={(e) => setPayForm({ ...payForm, from: e.target.value })} required><option value="">…</option>{accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
            <Field label="To account"><select value={payForm.to} onChange={(e) => setPayForm({ ...payForm, to: e.target.value })} required><option value="">…</option>{accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
            <Field label="Date"><input type="date" value={payForm.date} onChange={(e) => setPayForm({ ...payForm, date: e.target.value })} /></Field>
            <button>Record transfer</button>
          </form>
        </Card>
      )}
    </>
  );
}
