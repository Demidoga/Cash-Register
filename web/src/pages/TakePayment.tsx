import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { rupees, today } from "../format";
import { Card, Field, Spinner, useToast } from "../ui";

export default function TakePayment() {
  const toast = useToast();
  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const patients = useLoad(() => api.patients());
  const cases = useLoad(() => api.cases());

  const [caseId, setCaseId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  if (partners.loading || accounts.loading || cases.loading || patients.loading) return <Spinner />;

  const patientName = (id: number) => patients.data?.find((p) => p.id === id)?.name ?? "Patient";
  const activeAccounts = (accounts.data ?? []).filter((a) => a.is_active);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api.takePayment({
        case_id: Number(caseId),
        account_id: Number(accountId || activeAccounts[0]?.id),
        partner_id: Number(partnerId || partners.data?.[0]?.id),
        amount: Number(amount),
        date,
        note: note || null,
      });
      if ("queued" in res) {
        toast.show("Offline — payment held and will sync automatically", "ok");
      } else {
        toast.show(`Payment recorded · case now ${rupees(res.case.outstanding)} outstanding`, "ok");
      }
      setAmount("");
      setNote("");
      cases.reload();
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Take a payment</h1>
      <Card style={{ maxWidth: 560 }}>
        {cases.data?.length ? (
          <form onSubmit={submit}>
            <Field label="Case">
              <select value={caseId} onChange={(e) => setCaseId(e.target.value)} required>
                <option value="" disabled>Select a case…</option>
                {cases.data.map((c) => (
                  <option key={c.id} value={c.id}>
                    {patientName(c.patient_id)} — {c.procedure_name} (owes {rupees(c.outstanding)})
                  </option>
                ))}
              </select>
            </Field>
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
            <button disabled={busy}>{busy ? "Saving…" : "Record payment"}</button>
          </form>
        ) : (
          <div className="list-empty">No open cases. Create a patient and case first.</div>
        )}
      </Card>
    </>
  );
}
