import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, PencilSimple, Trash, X } from "@phosphor-icons/react";
import { api, downloadFile } from "../api";
import { useLoad } from "../hooks";
import { rupees, today } from "../format";
import { Badge, Card, Field, Spinner, useToast } from "../ui";
import type { Movement, MovementType } from "../types";

const TYPE_TONE: Record<MovementType, "green" | "red" | "amber" | "gray"> = {
  income: "green", expense: "red", transfer: "gray", capital: "amber", drawing: "amber",
};

export default function Journal() {
  const toast = useToast();
  const navigate = useNavigate();
  const accounts = useLoad(() => api.accounts());
  const partners = useLoad(() => api.partners());
  const cases = useLoad(() => api.cases());
  const patients = useLoad(() => api.patients());
  const [filter, setFilter] = useState("");
  const movements = useLoad(() => api.movements(filter ? `?type=${filter}` : ""), [filter]);

  const [kind, setKind] = useState<"transfer" | "capital" | "drawing" | "refund">("transfer");
  const [f, setF] = useState({ from: "", to: "", account: "", partner: "", case: "", amount: "", date: today(), note: "" });
  const [busy, setBusy] = useState(false);

  // Inline correction of an existing entry — date/amount/note (PATCH /movements).
  const [editing, setEditing] = useState<number | null>(null);
  const [ef, setEf] = useState({ date: "", amount: "", note: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  const accName = (id: number | null) => (id ? accounts.data?.find((a) => a.id === id)?.name ?? "" : "");
  const parName = (id: number | null) => (id ? partners.data?.find((p) => p.id === id)?.name ?? "" : "");
  const caseName = (id: number | null) => (id ? cases.data?.find((c) => c.id === id)?.procedure_name ?? "" : "");
  // The full case label (procedure — patient), for the hover overlay.
  const caseFull = (id: number | null) => {
    const c = id ? cases.data?.find((x) => x.id === id) : undefined;
    if (!c) return "";
    const patient = patients.data?.find((p) => p.id === c.patient_id)?.name;
    return patient ? `${c.procedure_name} — ${patient}` : c.procedure_name;
  };
  // The money flow between accounts, e.g. "Cash → Joint" — used as a fallback so
  // a partner-less, note-less transfer is never blank.
  const flow = (m: Movement) => {
    const from = accName(m.from_account_id), to = accName(m.to_account_id);
    if (from && to) return `${from} → ${to}`;
    if (to) return `→ ${to}`;
    if (from) return `${from} →`;
    return "";
  };

  // What the Detail column leads with: the case type for income, otherwise who
  // the entry is attributed to plus its note.
  const inlineDetail = (m: Movement) => {
    if (m.type === "income") return caseName(m.case_id) || parName(m.partner_id) || flow(m) || "—";
    const parts = [parName(m.partner_id), m.note].filter(Boolean);
    return parts.length ? parts.join(" · ") : flow(m) || "—";
  };

  // The complete breakdown revealed on hover/focus.
  const detailRows = (m: Movement): [string, string][] => {
    const rows: [string, string][] = [];
    const who = parName(m.partner_id);
    if (who) rows.push([m.type === "income" ? "Collected by" : m.type === "expense" ? "Paid by" : "Partner", who]);
    const from = accName(m.from_account_id); if (from) rows.push(["From", from]);
    const to = accName(m.to_account_id); if (to) rows.push(["To", to]);
    const c = caseFull(m.case_id); if (c) rows.push(["Case", c]);
    if (m.note) rows.push(["Note", m.note]);
    rows.push(["Logged", new Date(m.created_at).toLocaleString()]);
    if (m.edited) rows.push(["Edited", new Date(m.updated_at).toLocaleString()]);
    return rows;
  };

  function startEdit(m: Movement) {
    if (m.type === "income") { navigate("/income", { state: { editMovement: m } }); return; }
    if (m.type === "expense") { navigate("/expense", { state: { editMovement: m } }); return; }
    setEditing(m.id);
    setEf({ date: m.date, amount: String(m.amount), note: m.note ?? "" });
  }

  async function saveEdit(id: number) {
    setSavingEdit(true);
    try {
      await api.editMovement(id, { date: ef.date, amount: Number(ef.amount), note: ef.note || null });
      setEditing(null);
      movements.reload();
      toast.show("Entry updated", "ok");
    } catch (e: any) {
      toast.show(e?.message ?? "Failed", "error");
    } finally {
      setSavingEdit(false);
    }
  }

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

      <div className="split">
      <Card>
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
          <table className="entries">
            <thead><tr><th>Date</th><th>Type</th><th>Detail</th><th className="num">Amount</th></tr></thead>
            <tbody>
              {movements.data.map((m) => (editing === m.id ? (
                <tr key={m.id}>
                  <td><input type="date" value={ef.date} onChange={(e) => setEf({ ...ef, date: e.target.value })} /></td>
                  <td><Badge tone={TYPE_TONE[m.type]}>{m.type}</Badge></td>
                  <td><input value={ef.note} placeholder="Note" onChange={(e) => setEf({ ...ef, note: e.target.value })} /></td>
                  <td className="num">
                    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", justifyContent: "flex-end" }}>
                      <input type="number" min="1" style={{ width: 96, textAlign: "right" }} value={ef.amount} onChange={(e) => setEf({ ...ef, amount: e.target.value })} />
                      <button type="button" className="icon-sm" aria-label="Save changes" title="Save" disabled={savingEdit} onClick={() => saveEdit(m.id)}><Check size={15} /></button>
                      <button type="button" className="ghost icon-sm" aria-label="Cancel" title="Cancel" disabled={savingEdit} onClick={() => setEditing(null)}><X size={15} /></button>
                    </span>
                  </td>
                </tr>
              ) : (
                <tr key={m.id}>
                  <td className="muted"><span className="row-slide">{m.date}</span></td>
                  <td>
                    <span className="row-slide" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      <Badge tone={TYPE_TONE[m.type]}>{m.type}</Badge>
                      {m.edited && (
                        <span title={`Edited ${new Date(m.updated_at).toLocaleString()}`}>
                          <Badge tone="amber">edited</Badge>
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="muted detail-cell" tabIndex={0}>
                    <span className="row-slide">{inlineDetail(m)}</span>
                    <div className="detail-pop" role="tooltip">
                      <div className="dp-head">
                        <span className="dp-type">{m.type}</span>
                        <span className="dp-amt">{rupees(m.amount)}</span>
                      </div>
                      <div className="dp-date">{m.date}</div>
                      <dl>
                        {detailRows(m).map(([k, v]) => (
                          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
                        ))}
                      </dl>
                    </div>
                  </td>
                  <td className="num actions-cell">
                    <span className="row-slide">{rupees(m.amount)}</span>
                    <span className="row-actions">
                      <button type="button" aria-label="Edit entry" title="Edit" onClick={() => startEdit(m)}><PencilSimple size={14} /></button>
                      <button type="button" className="void" aria-label="Void entry" title="Void" onClick={() => voidMovement(m.id)}><Trash size={14} /></button>
                    </span>
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        ) : <div className="list-empty">No entries.</div>}
      </Card>
      </div>
    </>
  );
}
