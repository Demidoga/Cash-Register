import { useState } from "react";
import { api, downloadFile } from "../api";
import { useLoad } from "../hooks";
import { rupees, today } from "../format";
import { Badge, Card, Field, Spinner, useToast } from "../ui";
import type { MovementType } from "../types";

const TYPE_TONE: Record<MovementType, "green" | "red" | "amber" | "gray"> = {
  income: "green", expense: "red", transfer: "gray", capital: "amber", drawing: "amber",
};

export default function Journal() {
  const toast = useToast();
  const accounts = useLoad(() => api.accounts());
  const partners = useLoad(() => api.partners());
  const cases = useLoad(() => api.cases());
  const [filter, setFilter] = useState("");
  const movements = useLoad(() => api.movements(filter ? `?type=${filter}` : ""), [filter]);

  const [kind, setKind] = useState<"transfer" | "capital" | "drawing" | "refund">("transfer");
  const [f, setF] = useState({ from: "", to: "", account: "", partner: "", case: "", amount: "", date: today(), note: "" });
  const [busy, setBusy] = useState(false);

  const accName = (id: number | null) => (id ? accounts.data?.find((a) => a.id === id)?.name ?? "" : "");
  const parName = (id: number | null) => (id ? partners.data?.find((p) => p.id === id)?.name ?? "" : "");

  async function voidMovement(id: number) {
    if (!confirm("Void this entry? It stays recoverable.")) return;
    try {
      await api.voidMovement(id);
      movements.reload();
      toast.show("Entry voided", "ok");
    } catch (e: any) {
      toast.show(e?.message ?? "Failed", "error");
    }
  }

  async function recordOther(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const amount = Number(f.amount);
    try {
      if (kind === "transfer") await api.transfer({ from_account_id: Number(f.from), to_account_id: Number(f.to), amount, partner_id: f.partner ? Number(f.partner) : null, date: f.date, note: f.note || null });
      else if (kind === "capital") await api.capital({ account_id: Number(f.account), partner_id: Number(f.partner), amount, date: f.date, note: f.note || null });
      else if (kind === "drawing") await api.drawing({ account_id: Number(f.account), partner_id: Number(f.partner), amount, date: f.date, note: f.note || null });
      else await api.refund({ case_id: Number(f.case), account_id: Number(f.account), partner_id: Number(f.partner), amount, date: f.date, note: f.note || null });
      setF({ ...f, amount: "", note: "" });
      movements.reload();
      toast.show("Recorded", "ok");
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-head">
        <h1>Journal</h1>
        <button className="ghost sm" onClick={() => downloadFile("/exports/journal.csv", "journal.csv")}>Export CSV</button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <h2>Record transfer / capital / drawing / refund</h2>
        <form onSubmit={recordOther}>
          <div className="row">
            <Field label="Type">
              <select value={kind} onChange={(e) => setKind(e.target.value as any)}>
                <option value="transfer">Transfer between accounts</option>
                <option value="capital">Capital contribution</option>
                <option value="drawing">Drawing</option>
                <option value="refund">Refund to patient</option>
              </select>
            </Field>
            <Field label="Amount (Rs)"><input type="number" min="1" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} required /></Field>
            <Field label="Date"><input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          </div>
          <div className="row">
            {kind === "transfer" ? (
              <>
                <Field label="From"><select value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} required><option value="">…</option>{accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
                <Field label="To"><select value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} required><option value="">…</option>{accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
              </>
            ) : (
              <Field label={kind === "capital" ? "Into account" : "From account"}>
                <select value={f.account} onChange={(e) => setF({ ...f, account: e.target.value })} required><option value="">…</option>{accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
              </Field>
            )}
            <Field label="Partner">
              <select value={f.partner} onChange={(e) => setF({ ...f, partner: e.target.value })} required={kind !== "transfer"}>
                <option value="">…</option>{partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            {kind === "refund" && (
              <Field label="Case"><select value={f.case} onChange={(e) => setF({ ...f, case: e.target.value })} required><option value="">…</option>{cases.data?.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.procedure_name}</option>)}</select></Field>
            )}
          </div>
          <Field label="Note"><input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          <button disabled={busy}>{busy ? "Saving…" : "Record"}</button>
        </form>
      </Card>

      <Card>
        <div className="section-head">
          <h2>Entries</h2>
          <select style={{ width: 180 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All types</option>
            {["income", "expense", "transfer", "capital", "drawing"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        {movements.loading ? <Spinner /> : movements.data?.length ? (
          <table>
            <thead><tr><th>Date</th><th>Type</th><th>Detail</th><th className="num">Amount</th><th></th></tr></thead>
            <tbody>
              {movements.data.map((m) => (
                <tr key={m.id}>
                  <td className="muted">{m.date}</td>
                  <td><Badge tone={TYPE_TONE[m.type]}>{m.type}</Badge></td>
                  <td className="muted">
                    {accName(m.from_account_id) && `from ${accName(m.from_account_id)} `}
                    {accName(m.to_account_id) && `to ${accName(m.to_account_id)} `}
                    {parName(m.partner_id) && `· ${parName(m.partner_id)}`}
                    {m.note ? ` · ${m.note}` : ""}
                  </td>
                  <td className="num">{rupees(m.amount)}</td>
                  <td className="num"><button className="danger sm" onClick={() => voidMovement(m.id)}>Void</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="list-empty">No entries.</div>}
      </Card>
    </>
  );
}
