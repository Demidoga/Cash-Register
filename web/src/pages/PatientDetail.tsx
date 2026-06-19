import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, downloadFile } from "../api";
import { useLoad } from "../hooks";
import { rupees } from "../format";
import { Badge, Card, Field, Money, Spinner, useToast } from "../ui";

export default function PatientDetail() {
  const { id } = useParams();
  const pid = Number(id);
  const toast = useToast();
  const patient = useLoad(() => api.patient(pid), [pid]);
  const procedures = useLoad(() => api.procedures());

  const [procName, setProcName] = useState("");
  const [procId, setProcId] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  async function addCase(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createCase({
        patient_id: pid,
        procedure_name: procName,
        procedure_id: procId ? Number(procId) : null,
        agreed_price: Number(price || 0),
      });
      setProcName(""); setProcId(""); setPrice("");
      patient.reload();
      toast.show("Case opened", "ok");
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function discount(caseId: number) {
    const v = prompt("Discount amount (Rs)?");
    if (!v) return;
    await api.discount(caseId, { amount: Number(v) });
    patient.reload();
    toast.show("Discount applied", "ok");
  }

  async function writeOff(caseId: number) {
    if (!confirm("Write off the remaining balance as bad debt?")) return;
    await api.writeOff(caseId, {});
    patient.reload();
    toast.show("Balance written off", "ok");
  }

  if (patient.loading || !patient.data) return <Spinner />;
  const p = patient.data;

  return (
    <>
      <div className="section-head">
        <h1>{p.name}</h1>
        <Link to="/patients">← All patients</Link>
      </div>
      <p className="muted" style={{ marginTop: -8 }}>{p.phone ?? "no phone"} · {p.notes ?? ""}</p>

      <div className="banner inline" style={{ justifyContent: "space-between" }}>
        <span>Total outstanding: <b>{rupees(p.total_outstanding)}</b></span>
        <span className="inline">
          <button className="ghost sm" onClick={() => downloadFile(`/exports/patients/${pid}/statement.csv`, `statement-${p.name}.csv`)}>CSV</button>
          <button className="ghost sm" onClick={() => downloadFile(`/exports/patients/${pid}/statement.pdf`, `statement-${p.name}.pdf`)}>PDF statement</button>
        </span>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <h2>Cases</h2>
        {p.cases.length ? (
          <table>
            <thead><tr><th>Procedure</th><th className="num">Agreed</th><th className="num">Outstanding</th><th></th></tr></thead>
            <tbody>
              {p.cases.map((c) => (
                <tr key={c.id}>
                  <td>{c.procedure_name}</td>
                  <td className="num">{rupees(c.agreed_price)}</td>
                  <td className="num">
                    {c.outstanding === 0 ? <Badge tone="green">settled</Badge>
                      : c.outstanding < 0 ? <Badge tone="amber">advance {rupees(-c.outstanding)}</Badge>
                      : <Money n={c.outstanding} />}
                  </td>
                  <td className="num inline" style={{ justifyContent: "flex-end" }}>
                    <button className="ghost sm" onClick={() => discount(c.id)}>Discount</button>
                    {c.outstanding > 0 && <button className="danger sm" onClick={() => writeOff(c.id)}>Write off</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="list-empty">No cases yet.</div>}
      </Card>

      <Card style={{ maxWidth: 560 }}>
        <h2>Open a case</h2>
        <form onSubmit={addCase}>
          <Field label="Procedure (from catalog, optional)">
            <select value={procId} onChange={(e) => {
              setProcId(e.target.value);
              const proc = procedures.data?.find((x) => x.id === Number(e.target.value));
              if (proc) { setProcName(proc.name); setPrice(String(proc.default_price)); }
            }}>
              <option value="">— type a name below —</option>
              {procedures.data?.map((x) => <option key={x.id} value={x.id}>{x.name} ({rupees(x.default_price)})</option>)}
            </select>
          </Field>
          <div className="row">
            <Field label="Procedure name"><input value={procName} onChange={(e) => setProcName(e.target.value)} required /></Field>
            <Field label="Agreed price (Rs)"><input type="number" min="0" value={price} onChange={(e) => setPrice(e.target.value)} required /></Field>
          </div>
          <button disabled={busy}>{busy ? "Saving…" : "Open case"}</button>
        </form>
      </Card>
    </>
  );
}
