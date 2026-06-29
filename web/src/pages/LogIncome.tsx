import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";
import { rupees, today } from "../format";
import { Card, Field, MovementHistory, Spinner, useToast } from "../ui";
import type { Movement } from "../types";

const NEW = "new"; // sentinel for the "+ add new" option in the patient/case selects

export default function LogIncome() {
  const toast = useToast();
  const location = useLocation();

  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const patients = useLoad(() => api.patients());
  const cases = useLoad(() => api.cases());
  const procedures = useLoad(() => api.procedures());
  const history = useLoad(() => api.movements("?type=income"));

  const accName = (id: number | null) => (id ? accounts.data?.find((a) => a.id === id)?.name ?? "" : "");
  const parName = (id: number | null) => (id ? partners.data?.find((p) => p.id === id)?.name ?? "" : "");
  const caseName = (id: number | null) => (id ? cases.data?.find((c) => c.id === id)?.procedure_name ?? "" : "");

  // The movement being edited (null = recording a fresh entry). When set, the
  // form below doubles as the editor: every field is pre-filled and Save issues
  // a PATCH that overwrites the original instead of creating a new entry.
  const [editingId, setEditingId] = useState<number | null>(null);

  // who/which case the income is for: either an existing id, the NEW sentinel, or "" (unset)
  const [patientSel, setPatientSel] = useState("");
  const [caseSel, setCaseSel] = useState("");
  // inline "new patient" fields
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  // inline "new case" fields
  const [procId, setProcId] = useState("");
  const [procName, setProcName] = useState("");
  const [price, setPrice] = useState("");
  // the payment itself
  const [accountId, setAccountId] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [amount, setAmount] = useState("");
  const [discount, setDiscount] = useState("");
  const [date, setDate] = useState(today());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const isNewPatient = patientSel === NEW;
  const patientId = isNewPatient || patientSel === "" ? null : Number(patientSel);

  const patientCases = useMemo(
    () => (patientId ? (cases.data ?? []).filter((c) => c.patient_id === patientId) : []),
    [cases.data, patientId],
  );
  // A brand-new patient has no cases, so we always open one. An existing patient
  // with no cases also goes straight to the new-case fields.
  const isNewCase = isNewPatient || caseSel === NEW || (patientId !== null && patientCases.length === 0);

  const activeAccounts = (accounts.data ?? []).filter((a) => a.is_active);

  // Pull an existing income entry into the form for editing. Derives the patient
  // from the entry's case so the patient → case cascade lands on the right rows.
  function loadForEdit(m: Movement) {
    setEditingId(m.id);
    const c = (cases.data ?? []).find((x) => x.id === m.case_id);
    setPatientSel(c ? String(c.patient_id) : "");
    setCaseSel(m.case_id ? String(m.case_id) : "");
    setNewName(""); setNewPhone("");
    setProcId(""); setProcName(""); setPrice("");
    setAccountId(m.to_account_id ? String(m.to_account_id) : "");
    setPartnerId(m.partner_id ? String(m.partner_id) : "");
    setAmount(String(m.amount));
    setDiscount(m.discount ? String(m.discount) : ""); // the discount linked to this payment
    setDate(m.date);
    setNote(m.note ?? "");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function reset() {
    setEditingId(null);
    setPatientSel(""); setCaseSel("");
    setNewName(""); setNewPhone("");
    setProcId(""); setProcName(""); setPrice("");
    setAmount(""); setDiscount(""); setNote("");
    setDate(today());
  }

  // When navigated here from the Journal's edit button, load that entry once the
  // reference data it needs (cases/patients) has arrived.
  const editLoadedRef = useRef(false);
  useEffect(() => {
    const incoming = (location.state as { editMovement?: Movement } | null)?.editMovement;
    if (incoming && !editLoadedRef.current && cases.data && patients.data && accounts.data && partners.data) {
      editLoadedRef.current = true;
      loadForEdit(incoming);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, cases.data, patients.data, accounts.data, partners.data]);

  // Auto-fill the receiving account from the selected "Collected by" partner when
  // that partner has a linked personal account (set in Configure → Accounts →
  // Owner). It's only a smart default for new entries — never override the
  // account stored on the entry we're editing.
  useEffect(() => {
    if (editingId !== null) return;
    const pid = Number(partnerId || partners.data?.[0]?.id);
    const owned = (accounts.data ?? []).find((a) => a.is_active && a.owner_partner_id === pid);
    if (owned) setAccountId(String(owned.id));
  }, [partnerId, partners.data, accounts.data, editingId]);

  if (partners.loading || accounts.loading || cases.loading || patients.loading || procedures.loading)
    return <Spinner />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();

    // Validate the inline create paths before we touch the network.
    if (patientSel === "") return toast.show("Pick or add a patient first", "error");
    if (isNewPatient && !newName.trim()) return toast.show("Enter the new patient's name", "error");
    if (!isNewCase && caseSel === "") return toast.show("Pick or open a case", "error");
    if (isNewCase && !procName.trim()) return toast.show("Enter the procedure for the new case", "error");

    setBusy(true);
    try {
      // 1. Resolve the patient (create on the fly if new).
      let pid = patientId;
      if (isNewPatient) {
        const p = await api.createPatient({ name: newName.trim(), phone: newPhone || null, notes: null });
        pid = p.id;
      }
      // 2. Resolve the case (open one on the fly if new).
      let caseId: number;
      if (isNewCase) {
        const c = await api.createCase({
          patient_id: pid,
          procedure_name: procName.trim(),
          procedure_id: procId ? Number(procId) : null,
          agreed_price: Number(price || 0),
        });
        caseId = c.id;
      } else {
        caseId = Number(caseSel);
      }

      const disc = Number(discount) > 0 ? Number(discount) : null;

      // 3a. Editing: overwrite the original entry in place (PATCH). The discount
      //     is sent as an absolute amount, so the backend rewrites the discount
      //     linked to this payment (0 clears it) rather than stacking a new one.
      if (editingId !== null) {
        await api.editMovement(editingId, {
          case_id: caseId,
          to_account_id: Number(accountId || activeAccounts[0]?.id),
          partner_id: Number(partnerId || partners.data?.[0]?.id),
          amount: Number(amount),
          date,
          note: note || null,
          discount: disc ?? 0,
        });
        toast.show("Income updated", "ok");
        reset();
        patients.reload();
        cases.reload();
        history.reload();
        return;
      }

      // 3b. Recording fresh: take the payment (held offline if needed).
      const res = await api.takePayment({
        case_id: caseId,
        account_id: Number(accountId || activeAccounts[0]?.id),
        partner_id: Number(partnerId || partners.data?.[0]?.id),
        amount: Number(amount),
        date,
        note: note || null,
        // Optional: discount the case alongside the payment (omit when blank/0).
        discount: disc,
      });
      if ("queued" in res) {
        toast.show("Offline. Income held and will sync automatically", "ok");
      } else {
        toast.show(`Income recorded · case now ${rupees(res.case.outstanding)} outstanding`, "ok");
      }
      reset();
      patients.reload();
      cases.reload();
      if (!("queued" in res)) history.reload();
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>{editingId !== null ? "Edit income" : "Log income"}</h1>
      <div className="split">
      <Card>
        {editingId !== null && (
          <div className="edit-banner">
            Editing an existing entry — saving overwrites it.
            <button type="button" className="ghost sm" onClick={reset}>Cancel</button>
          </div>
        )}
        <form onSubmit={submit}>
          <Field label="Patient">
            <select
              value={patientSel}
              onChange={(e) => { setPatientSel(e.target.value); setCaseSel(""); }}
              required
            >
              <option value="" disabled>Select a patient…</option>
              {patients.data?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.phone ? ` · ${p.phone}` : ""}</option>
              ))}
              <option value={NEW}>＋ Add a new patient</option>
            </select>
          </Field>

          {isNewPatient && (
            <div className="row">
              <Field label="New patient name">
                <input value={newName} onChange={(e) => setNewName(e.target.value)} required />
              </Field>
              <Field label="Phone (optional)">
                <input value={newPhone} onChange={(e) => setNewPhone(e.target.value)} />
              </Field>
            </div>
          )}

          {/* Case picker: only an existing patient with at least one case gets to choose. */}
          {patientId !== null && patientCases.length > 0 && (
            <Field label="Case">
              <select value={caseSel} onChange={(e) => setCaseSel(e.target.value)} required>
                <option value="" disabled>Select a case…</option>
                {patientCases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.procedure_name} (owes {rupees(c.outstanding)})
                  </option>
                ))}
                <option value={NEW}>＋ Open a new case</option>
              </select>
            </Field>
          )}

          {isNewCase && (
            <>
              <h3 style={{ margin: "4px 0 0" }}>
                Open a case{isNewPatient && newName.trim() ? ` for ${newName.trim()}` : ""}
              </h3>
              <Field label="Procedure (from catalog, optional)">
                <select
                  value={procId}
                  onChange={(e) => {
                    setProcId(e.target.value);
                    const proc = procedures.data?.find((x) => x.id === Number(e.target.value));
                    if (proc) { setProcName(proc.name); setPrice(String(proc.default_price)); }
                  }}
                >
                  <option value="">Type a name below</option>
                  {procedures.data?.map((x) => (
                    <option key={x.id} value={x.id}>{x.name} ({rupees(x.default_price)})</option>
                  ))}
                </select>
              </Field>
              <div className="row">
                <Field label="Procedure name">
                  <input value={procName} onChange={(e) => setProcName(e.target.value)} required />
                </Field>
                <Field label="Agreed price (Rs)">
                  <input type="number" min="0" value={price} onChange={(e) => setPrice(e.target.value)} required />
                </Field>
              </div>
            </>
          )}

          <div className="row">
            <Field label="Amount (Rs)">
              <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} required />
            </Field>
            <Field label="Discount (Rs, optional)">
              <input type="number" min="0" value={discount} onChange={(e) => setDiscount(e.target.value)} />
            </Field>
            <Field label="Date">
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
          </div>
          <div className="row">
            <Field label="Collected by">
              <select value={partnerId} onChange={(e) => setPartnerId(e.target.value)}>
                {partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Into account">
              <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {activeAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Note (optional)">
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="row" style={{ gap: 8 }}>
            <button disabled={busy}>
              {busy ? "Saving…" : editingId !== null ? "Save changes" : "Record income"}
            </button>
            {editingId !== null && (
              <button type="button" className="ghost" onClick={reset}>Cancel</button>
            )}
          </div>
        </form>
      </Card>
      <MovementHistory
        title="Recent income"
        loading={history.loading}
        movements={history.data}
        empty="No income recorded yet."
        onEdit={loadForEdit}
        detail={(m) => [caseName(m.case_id), parName(m.partner_id), m.note].filter(Boolean).join(" · ") || "—"}
        fullDetail={(m) => {
          const rows: [string, string][] = [];
          const who = parName(m.partner_id); if (who) rows.push(["Collected by", who]);
          const to = accName(m.to_account_id); if (to) rows.push(["Into", to]);
          const c = caseName(m.case_id); if (c) rows.push(["Case", c]);
          if (m.note) rows.push(["Note", m.note]);
          rows.push(["Logged", new Date(m.created_at).toLocaleString()]);
          if (m.edited) rows.push(["Edited", new Date(m.updated_at).toLocaleString()]);
          return rows;
        }}
      />
      </div>
    </>
  );
}
