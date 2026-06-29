import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";
import { today } from "../format";
import { Card, Field, MovementHistory, Spinner, useToast } from "../ui";
import type { Movement } from "../types";

export default function LogExpense() {
  const toast = useToast();
  const location = useLocation();

  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const categories = useLoad(() => api.categories());
  const cases = useLoad(() => api.cases());
  const history = useLoad(() => api.movements("?type=expense"));

  const accName = (id: number | null) => (id ? accounts.data?.find((a) => a.id === id)?.name ?? "" : "");
  const parName = (id: number | null) => (id ? partners.data?.find((p) => p.id === id)?.name ?? "" : "");

  // The movement being edited (null = recording a fresh entry). When set, the
  // form doubles as the editor: every field is pre-filled and Save issues a
  // PATCH that overwrites the original instead of creating a new entry.
  const [editingId, setEditingId] = useState<number | null>(null);

  const [accountId, setAccountId] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  // Pull an existing expense entry into the form for editing.
  function loadForEdit(m: Movement) {
    setEditingId(m.id);
    setAccountId(m.from_account_id ? String(m.from_account_id) : "");
    setPartnerId(m.partner_id ? String(m.partner_id) : "");
    setCategoryId(m.category_id ? String(m.category_id) : "");
    setCaseId(m.case_id ? String(m.case_id) : "");
    setAmount(String(m.amount));
    setDate(m.date);
    setNote(m.note ?? "");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Clear the form back to a fresh-entry state (used on cancel and after an edit).
  function clearForm() {
    setEditingId(null);
    setCategoryId(""); setCaseId("");
    setAmount(""); setNote("");
    setDate(today());
  }

  // When navigated here from the Journal's edit button, load that entry once the
  // reference data it needs has arrived.
  const editLoadedRef = useRef(false);
  useEffect(() => {
    const incoming = (location.state as { editMovement?: Movement } | null)?.editMovement;
    if (incoming && !editLoadedRef.current && accounts.data && partners.data && categories.data && cases.data) {
      editLoadedRef.current = true;
      loadForEdit(incoming);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, accounts.data, partners.data, categories.data, cases.data]);

  // Auto-fill the spending account from the selected "Paid by" partner when that
  // partner has a linked personal account (set in Configure → Accounts → Owner).
  // It's only a smart default for new entries — never override the account stored
  // on the entry we're editing.
  useEffect(() => {
    if (editingId !== null) return;
    const pid = Number(partnerId || partners.data?.[0]?.id);
    const owned = (accounts.data ?? []).find((a) => a.is_active && a.owner_partner_id === pid);
    if (owned) setAccountId(String(owned.id));
  }, [partnerId, partners.data, accounts.data, editingId]);

  if (partners.loading || accounts.loading || categories.loading) return <Spinner />;
  const activeAccounts = (accounts.data ?? []).filter((a) => a.is_active);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      // Editing: overwrite the original entry in place (PATCH).
      if (editingId !== null) {
        await api.editMovement(editingId, {
          from_account_id: Number(accountId || activeAccounts[0]?.id),
          partner_id: Number(partnerId || partners.data?.[0]?.id),
          category_id: categoryId ? Number(categoryId) : null,
          case_id: caseId ? Number(caseId) : null,
          amount: Number(amount),
          date,
          note: note || null,
        });
        toast.show("Expense updated", "ok");
        clearForm();
        history.reload();
        return;
      }

      // Recording fresh (held offline if needed).
      const res = await api.logExpense({
        account_id: Number(accountId || activeAccounts[0]?.id),
        partner_id: Number(partnerId || partners.data?.[0]?.id),
        category_id: categoryId ? Number(categoryId) : null,
        case_id: caseId ? Number(caseId) : null,
        amount: Number(amount),
        date,
        note: note || null,
      });
      toast.show("queued" in res ? "Offline. Expense held, will sync" : "Expense recorded", "ok");
      setAmount("");
      setNote("");
      if (!("queued" in res)) history.reload();
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>{editingId !== null ? "Edit expense" : "Log an expense"}</h1>
      <div className="split">
      <Card>
        {editingId !== null && (
          <div className="edit-banner">
            Editing an existing entry — saving overwrites it.
            <button type="button" className="ghost sm" onClick={clearForm}>Cancel</button>
          </div>
        )}
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
                <option value="">None</option>
                {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Link to case (optional)">
              <select value={caseId} onChange={(e) => setCaseId(e.target.value)}>
                <option value="">None</option>
                {cases.data?.map((c) => <option key={c.id} value={c.id}>{c.procedure_name} #{c.id}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Note (optional)">
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="row" style={{ gap: 8 }}>
            <button disabled={busy}>
              {busy ? "Saving…" : editingId !== null ? "Save changes" : "Record expense"}
            </button>
            {editingId !== null && (
              <button type="button" className="ghost" onClick={clearForm}>Cancel</button>
            )}
          </div>
        </form>
      </Card>
      <MovementHistory
        title="Recent expenses"
        loading={history.loading}
        movements={history.data}
        empty="No expenses recorded yet."
        onEdit={loadForEdit}
        detail={(m) => {
          const parts = [parName(m.partner_id), m.note].filter(Boolean);
          return parts.length ? parts.join(" · ") : accName(m.from_account_id) || "—";
        }}
        fullDetail={(m) => {
          const rows: [string, string][] = [];
          const who = parName(m.partner_id); if (who) rows.push(["Paid by", who]);
          const from = accName(m.from_account_id); if (from) rows.push(["From", from]);
          const cn = cases.data?.find((c) => c.id === m.case_id)?.procedure_name;
          if (cn) rows.push(["Case", cn]);
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
