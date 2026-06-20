import { useMemo, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { rupees, today } from "../format";
import { Card, Field, Spinner, useToast } from "../ui";

const NEW = "new"; // sentinel for the "+ add new" option in the patient/case selects

export default function LogIncome() {
  const toast = useToast();
  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const patients = useLoad(() => api.patients());
  const cases = useLoad(() => api.cases());
  const procedures = useLoad(() => api.procedures());

  // who/which case the income is for — either an existing id, the NEW sentinel, or "" (unset)
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

  if (partners.loading || accounts.loading || cases.loading || patients.loading || procedures.loading)
    return <Spinner />;

  function reset() {
    setPatientSel(""); setCaseSel("");
    setNewName(""); setNewPhone("");
    setProcId(""); setProcName(""); setPrice("");
    setAmount(""); setNote("");
  }

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
      // 3. Record the income against that case.
      const res = await api.takePayment({
        case_id: caseId,
        account_id: Number(accountId || activeAccounts[0]?.id),
        partner_id: Number(partnerId || partners.data?.[0]?.id),
        amount: Number(amount),
        date,
        note: note || null,
      });
      if ("queued" in res) {
        toast.show("Offline — income held and will sync automatically", "ok");
      } else {
        toast.show(`Income recorded · case now ${rupees(res.case.outstanding)} outstanding`, "ok");
      }
      reset();
      patients.reload();
      cases.reload();
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Log income</h1>
      <Card style={{ maxWidth: 560 }}>
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
                  <option value="">— type a name below —</option>
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
          <button disabled={busy}>{busy ? "Saving…" : "Record income"}</button>
        </form>
      </Card>
    </>
  );
}
