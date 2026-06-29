import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PencilSimple, Trash } from "@phosphor-icons/react";
import { api, downloadFile } from "../api";
import { useLoad } from "../hooks";
import { rupees } from "../format";
import { Badge, Card, Field, Modal, Money, Spinner, useToast } from "../ui";
import type { Case } from "../types";

export default function PatientDetail() {
  const { id } = useParams();
  const pid = Number(id);
  const navigate = useNavigate();
  const toast = useToast();
  const patient = useLoad(() => api.patient(pid), [pid]);
  const procedures = useLoad(() => api.procedures());

  // Delete is friction + undo: a confirm, then a soft-delete the toast can
  // reverse. Cases go down with the patient and come back on restore (the cash
  // movements stay on the books either way). We leave for the list on delete and
  // return to the dashboard on undo.
  async function deletePatient() {
    const name = patient.data?.name ?? "this patient";
    if (!confirm(`Delete ${name}? Their cases are removed too — you can undo this.`)) return;
    try {
      await api.deletePatient(pid);
      navigate("/patients");
      toast.show("Patient deleted", "ok", {
        label: "Undo",
        onClick: async () => {
          try {
            await api.restorePatient(pid);
            navigate(`/patients/${pid}`);
            toast.show("Patient restored", "ok");
          } catch (e: any) {
            toast.show(e?.message ?? "Restore failed", "error");
          }
        },
      });
    } catch (e: any) {
      toast.show(e?.message ?? "Failed", "error");
    }
  }

  const [procName, setProcName] = useState("");
  const [procId, setProcId] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  // The case being edited (null = modal closed) plus its working copy. The
  // catalog picker fills name/price like the create form; `procedure_id` is sent
  // only when a catalog entry is picked here, so an untouched edit never relinks.
  const [editCase, setEditCase] = useState<Case | null>(null);
  const [ef, setEf] = useState({ procedure_name: "", procedure_id: "", agreed_price: "", status: "open" });
  const [savingCase, setSavingCase] = useState(false);
  const [discountAmt, setDiscountAmt] = useState("");
  const [adjBusy, setAdjBusy] = useState(false);

  function openEdit(c: Case) {
    setEditCase(c);
    setEf({ procedure_name: c.procedure_name, procedure_id: "", agreed_price: String(c.agreed_price), status: c.status });
    setDiscountAmt("");
  }

  async function saveCase(e: React.FormEvent) {
    e.preventDefault();
    if (!editCase) return;
    setSavingCase(true);
    try {
      await api.editCase(editCase.id, {
        procedure_name: ef.procedure_name,
        agreed_price: Number(ef.agreed_price || 0),
        status: ef.status,
        ...(ef.procedure_id ? { procedure_id: Number(ef.procedure_id) } : {}),
      });
      setEditCase(null);
      patient.reload();
      toast.show("Case updated", "ok");
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setSavingCase(false);
    }
  }

  async function applyDiscount() {
    if (!editCase || !discountAmt) return;
    setAdjBusy(true);
    try {
      const updated = await api.discount(editCase.id, { amount: Number(discountAmt) });
      setEditCase(updated);  // refresh outstanding shown in the dialog
      setDiscountAmt("");
      patient.reload();
      toast.show("Discount applied", "ok");
    } catch (e: any) {
      toast.show(e?.message ?? "Failed", "error");
    } finally {
      setAdjBusy(false);
    }
  }

  async function writeOffCase() {
    if (!editCase) return;
    if (!confirm("Write off the remaining balance as bad debt?")) return;
    setAdjBusy(true);
    try {
      const updated = await api.writeOff(editCase.id, {});
      setEditCase(updated);
      patient.reload();
      toast.show("Balance written off", "ok");
    } catch (e: any) {
      toast.show(e?.message ?? "Failed", "error");
    } finally {
      setAdjBusy(false);
    }
  }

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
                    <button className="ghost sm inline" onClick={() => openEdit(c)}>
                      <PencilSimple size={14} /> Edit
                    </button>
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
              <option value="">Type a name below</option>
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

      <div style={{ display: "flex", justifyContent: "center", marginTop: 64 }}>
        <button className="danger inline" onClick={deletePatient}>
          <Trash size={15} /> Delete Record
        </button>
      </div>

      {editCase && (
        <Modal title="Edit case" onClose={() => setEditCase(null)}>
          <form onSubmit={saveCase}>
            <Field label="Procedure (from catalog, optional)">
              <select value={ef.procedure_id} onChange={(e) => {
                const proc = procedures.data?.find((x) => x.id === Number(e.target.value));
                setEf({
                  ...ef,
                  procedure_id: e.target.value,
                  ...(proc ? { procedure_name: proc.name, agreed_price: String(proc.default_price) } : {}),
                });
              }}>
                <option value="">Keep current / type below</option>
                {procedures.data?.map((x) => <option key={x.id} value={x.id}>{x.name} ({rupees(x.default_price)})</option>)}
              </select>
            </Field>
            <div className="row">
              <Field label="Procedure name"><input value={ef.procedure_name} onChange={(e) => setEf({ ...ef, procedure_name: e.target.value })} required /></Field>
              <Field label="Agreed price (Rs)"><input type="number" min="0" value={ef.agreed_price} onChange={(e) => setEf({ ...ef, agreed_price: e.target.value })} required /></Field>
            </div>
            <Field label="Status">
              <select value={ef.status} onChange={(e) => setEf({ ...ef, status: e.target.value })}>
                <option value="open">open</option>
                <option value="closed">closed</option>
              </select>
            </Field>
            <button disabled={savingCase}>{savingCase ? "Saving…" : "Save changes"}</button>
          </form>

          <div className="divider">Adjustments</div>
          <div className="banner inline" style={{ justifyContent: "space-between" }}>
            <span>Outstanding</span>
            <b>
              {editCase.outstanding === 0 ? <Badge tone="green">settled</Badge>
                : editCase.outstanding < 0 ? <Badge tone="amber">advance {rupees(-editCase.outstanding)}</Badge>
                : <Money n={editCase.outstanding} />}
            </b>
          </div>
          <div className="row" style={{ alignItems: "flex-end" }}>
            <Field label="Discount (Rs)"><input type="number" min="1" value={discountAmt} onChange={(e) => setDiscountAmt(e.target.value)} /></Field>
            <button type="button" className="ghost" disabled={adjBusy || !discountAmt} onClick={applyDiscount}>Apply discount</button>
          </div>
          {editCase.outstanding > 0 && (
            <button type="button" className="danger" style={{ marginTop: 10 }} disabled={adjBusy} onClick={writeOffCase}>
              Write off remaining balance
            </button>
          )}
        </Modal>
      )}
    </>
  );
}
