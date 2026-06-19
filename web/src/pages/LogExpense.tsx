import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { today } from "../format";
import { Card, Field, Spinner, useToast } from "../ui";

export default function LogExpense() {
  const toast = useToast();
  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const categories = useLoad(() => api.categories());
  const cases = useLoad(() => api.cases());

  const [accountId, setAccountId] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  if (partners.loading || accounts.loading || categories.loading) return <Spinner />;
  const activeAccounts = (accounts.data ?? []).filter((a) => a.is_active);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api.logExpense({
        account_id: Number(accountId || activeAccounts[0]?.id),
        partner_id: Number(partnerId || partners.data?.[0]?.id),
        category_id: categoryId ? Number(categoryId) : null,
        case_id: caseId ? Number(caseId) : null,
        amount: Number(amount),
        date,
        note: note || null,
      });
      toast.show("queued" in res ? "Offline — expense held, will sync" : "Expense recorded", "ok");
      setAmount("");
      setNote("");
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Log an expense</h1>
      <Card style={{ maxWidth: 560 }}>
        <form onSubmit={submit}>
          <div className="row">
            <Field label="Amount (Rs)">
              <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} required />
            </Field>
            <Field label="Date">
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
          </div>
          <div className="row">
            <Field label="Paid by">
              <select value={partnerId} onChange={(e) => setPartnerId(e.target.value)}>
                {partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="From account">
              <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {activeAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>
          </div>
          <div className="row">
            <Field label="Category">
              <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                <option value="">— none —</option>
                {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Link to case (optional)">
              <select value={caseId} onChange={(e) => setCaseId(e.target.value)}>
                <option value="">— none —</option>
                {cases.data?.map((c) => <option key={c.id} value={c.id}>{c.procedure_name} #{c.id}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Note (optional)">
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <button disabled={busy}>{busy ? "Saving…" : "Record expense"}</button>
        </form>
      </Card>
    </>
  );
}
