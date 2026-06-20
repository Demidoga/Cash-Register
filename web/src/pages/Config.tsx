import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useLoad } from "../hooks";
import { rupees, today } from "../format";
import type { Member } from "../types";
import { Badge, Card, Field, Spinner, useToast } from "../ui";

export default function Config() {
  const toast = useToast();
  const { me } = useAuth();
  const partners = useLoad(() => api.partners());
  const accounts = useLoad(() => api.accounts());
  const categories = useLoad(() => api.categories());
  const procedures = useLoad(() => api.procedures());
  const employees = useLoad(() => api.employees());
  const shareWindows = useLoad(() => api.shareWindows());

  const fail = (e: any) => toast.show(e?.message ?? "Failed", "error");

  // accounts
  const [acc, setAcc] = useState({ name: "", kind: "joint", owner: "", opening: "" });
  async function addAccount(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createAccount({
        name: acc.name, kind: acc.kind,
        owner_partner_id: acc.kind === "personal" && acc.owner ? Number(acc.owner) : null,
        opening_balance: Number(acc.opening || 0),
      });
      setAcc({ name: "", kind: "joint", owner: "", opening: "" });
      accounts.reload();
    } catch (e2) { fail(e2); }
  }
  async function toggle(id: number, active: boolean) {
    try { await api.updateAccount(id, { is_active: !active }); accounts.reload(); } catch (e) { fail(e); }
  }

  // simple lists
  const [catName, setCatName] = useState("");
  const [proc, setProc] = useState({ name: "", price: "" });
  const [emp, setEmp] = useState({ name: "", role: "", salary: "" });

  // new share window
  const [eff, setEff] = useState(today());
  const [shares, setShares] = useState<Record<number, number>>({});
  async function addShareWindow(e: React.FormEvent) {
    e.preventDefault();
    const rows = (partners.data ?? []).map((p) => ({ partner_id: p.id, share_num: Math.round(shares[p.id] ?? 0), share_den: 100 }));
    try {
      await api.createShareWindow({ effective_from: eff, shares: rows });
      shareWindows.reload();
      toast.show("Share window added", "ok");
    } catch (e2) { fail(e2); }
  }
  const shareTotal = (partners.data ?? []).reduce((s, p) => s + (shares[p.id] ?? 0), 0);

  return (
    <>
      <h1>Configure</h1>

      {me?.role === "owner" && <MembersCard />}

      <Card style={{ marginBottom: 16 }}>
        <h2>Accounts</h2>
        {accounts.loading ? <Spinner /> : (
          <table>
            <thead><tr><th>Name</th><th>Kind</th><th className="num">Opening</th><th></th></tr></thead>
            <tbody>
              {accounts.data?.map((a) => (
                <tr key={a.id}>
                  <td>{a.name} {!a.is_active && <Badge tone="gray">disabled</Badge>}</td>
                  <td>{a.kind}{a.owner_partner_id ? ` · ${partners.data?.find((p) => p.id === a.owner_partner_id)?.name ?? ""}` : ""}</td>
                  <td className="num">{rupees(a.opening_balance)}</td>
                  <td className="num"><button className="ghost sm" onClick={() => toggle(a.id, a.is_active)}>{a.is_active ? "Disable" : "Enable"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form onSubmit={addAccount} className="row" style={{ marginTop: 12, alignItems: "flex-end" }}>
          <Field label="Name"><input value={acc.name} onChange={(e) => setAcc({ ...acc, name: e.target.value })} required /></Field>
          <Field label="Kind"><select value={acc.kind} onChange={(e) => setAcc({ ...acc, kind: e.target.value })}><option value="joint">joint</option><option value="personal">personal</option></select></Field>
          {acc.kind === "personal" && (
            <Field label="Owner"><select value={acc.owner} onChange={(e) => setAcc({ ...acc, owner: e.target.value })} required><option value="">…</option>{partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          )}
          <Field label="Opening"><input type="number" value={acc.opening} onChange={(e) => setAcc({ ...acc, opening: e.target.value })} /></Field>
          <button style={{ flex: "0 0 auto" }}>Add</button>
        </form>
      </Card>

      <div className="grid cols-2">
        <Card>
          <h2>Expense categories</h2>
          <ListChips items={categories.data?.map((c) => ({ id: c.id, label: c.name })) ?? []}
            onDelete={async (id) => { try { await api.deleteCategory(id); categories.reload(); } catch (e) { fail(e); } }} />
          <form className="inline" style={{ marginTop: 10 }} onSubmit={async (e) => { e.preventDefault(); try { await api.createCategory(catName); setCatName(""); categories.reload(); } catch (e2) { fail(e2); } }}>
            <input value={catName} onChange={(e) => setCatName(e.target.value)} placeholder="e.g. Rent" required />
            <button style={{ flex: "0 0 auto" }}>Add</button>
          </form>
        </Card>

        <Card>
          <h2>Procedure catalog</h2>
          {procedures.loading ? <Spinner /> : (
            <table><tbody>{procedures.data?.map((p) => (
              <tr key={p.id}><td>{p.name}</td><td className="num">{rupees(p.default_price)}</td><td className="num"><button className="danger sm" onClick={async () => { try { await api.deleteProcedure(p.id); procedures.reload(); } catch (e) { fail(e); } }}>✕</button></td></tr>
            ))}</tbody></table>
          )}
          <form className="row" style={{ marginTop: 10, alignItems: "flex-end" }} onSubmit={async (e) => { e.preventDefault(); try { await api.createProcedure({ name: proc.name, default_price: Number(proc.price || 0) }); setProc({ name: "", price: "" }); procedures.reload(); } catch (e2) { fail(e2); } }}>
            <Field label="Name"><input value={proc.name} onChange={(e) => setProc({ ...proc, name: e.target.value })} required /></Field>
            <Field label="Default price"><input type="number" value={proc.price} onChange={(e) => setProc({ ...proc, price: e.target.value })} /></Field>
            <button style={{ flex: "0 0 auto" }}>Add</button>
          </form>
        </Card>

        <Card>
          <h2>Employees</h2>
          {employees.loading ? <Spinner /> : (
            <table><tbody>{employees.data?.map((emp2) => (
              <tr key={emp2.id}><td>{emp2.name} <span className="muted">{emp2.role}</span></td><td className="num">{rupees(emp2.salary)}</td><td className="num"><button className="danger sm" onClick={async () => { try { await api.deleteEmployee(emp2.id); employees.reload(); } catch (e) { fail(e); } }}>✕</button></td></tr>
            ))}</tbody></table>
          )}
          <form className="row" style={{ marginTop: 10, alignItems: "flex-end" }} onSubmit={async (e) => { e.preventDefault(); try { await api.createEmployee({ name: emp.name, role: emp.role || null, salary: Number(emp.salary || 0) }); setEmp({ name: "", role: "", salary: "" }); employees.reload(); } catch (e2) { fail(e2); } }}>
            <Field label="Name"><input value={emp.name} onChange={(e) => setEmp({ ...emp, name: e.target.value })} required /></Field>
            <Field label="Role"><input value={emp.role} onChange={(e) => setEmp({ ...emp, role: e.target.value })} /></Field>
            <Field label="Salary"><input type="number" value={emp.salary} onChange={(e) => setEmp({ ...emp, salary: e.target.value })} /></Field>
            <button style={{ flex: "0 0 auto" }}>Add</button>
          </form>
        </Card>

        <Card>
          <h2>Profit shares (effective-dated)</h2>
          {shareWindows.loading ? <Spinner /> : (
            <table><tbody>{shareWindows.data?.map((w: any) => (
              <tr key={w.id}><td>from {w.effective_from}</td><td className="muted">{w.shares.map((s: any) => `${Math.round((s.share_num / s.share_den) * 100)}%`).join(" / ")}</td></tr>
            ))}</tbody></table>
          )}
          <form onSubmit={addShareWindow} style={{ marginTop: 10 }}>
            <Field label="Effective from"><input type="date" value={eff} onChange={(e) => setEff(e.target.value)} /></Field>
            {partners.data?.map((p) => (
              <Field key={p.id} label={`${p.name} %`}>
                <input type="number" value={shares[p.id] ?? ""} onChange={(e) => setShares({ ...shares, [p.id]: Number(e.target.value) })} />
              </Field>
            ))}
            <div className="inline">
              <button disabled={shareTotal !== 100}>Add window</button>
              <small className={shareTotal === 100 ? "muted" : "badge red"}>total {shareTotal}%</small>
            </div>
          </form>
        </Card>
      </div>
    </>
  );
}

// Owner-only allowlist management (ADR-0008). Add someone by email; they sign
// in to Supabase with that email to get access — no email is sent, no token.
function MembersCard() {
  const toast = useToast();
  const members = useLoad(() => api.members());
  const [email, setEmail] = useState("");
  const fail = (e: any) => toast.show(e?.message ?? "Failed", "error");

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await api.inviteMember(email.trim());
      setEmail("");
      members.reload();
      const msg =
        res.status === "already_member" ? `${res.member.email} is already a member`
        : res.status === "reactivated" ? `Access restored for ${res.member.email}`
        : `Invited ${res.member.email}`;
      toast.show(msg, "ok");
    } catch (e2) { fail(e2); }
  }

  async function revoke(m: Member) {
    if (!window.confirm(`Revoke access for ${m.full_name ?? m.email}?`)) return;
    try {
      await api.revokeMember(m.id);
      members.reload();
      toast.show("Access revoked", "ok");
    } catch (e) { fail(e); }
  }

  return (
    <Card style={{ marginBottom: 16 }}>
      <h2>Members</h2>
      <p className="muted" style={{ marginTop: -4 }}>
        Grant access by email. The person signs in with that email — no invite email is sent.
      </p>
      {members.loading ? <Spinner /> : (
        <table>
          <thead><tr><th>Member</th><th>Tier</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {members.data?.map((m) => (
              <tr key={m.id}>
                <td>{m.full_name ?? m.email}{m.full_name && <div className="muted">{m.email}</div>}</td>
                <td><Badge tone="gray">{m.role}</Badge></td>
                <td>{m.status === "pending" ? <Badge tone="amber">pending</Badge> : <Badge tone="green">active</Badge>}</td>
                <td className="num"><button className="danger sm" onClick={() => revoke(m)}>Revoke</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={invite} className="inline" style={{ marginTop: 12 }}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" required />
        <button style={{ flex: "0 0 auto" }}>Invite</button>
      </form>
    </Card>
  );
}

function ListChips({ items, onDelete }: { items: { id: number; label: string }[]; onDelete: (id: number) => void }) {
  if (!items.length) return <div className="list-empty">None yet.</div>;
  return (
    <div className="pill-row">
      {items.map((it) => (
        <span key={it.id} className="badge gray inline" style={{ gap: 6 }}>
          {it.label}<button className="ghost sm" style={{ padding: "0 4px" }} onClick={() => onDelete(it.id)}>✕</button>
        </span>
      ))}
    </div>
  );
}
