import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { today } from "../format";
import { Card, Field } from "../ui";

interface PartnerRow { name: string; pct: number; }
interface AccountRow { name: string; kind: "personal" | "joint"; owner: number | ""; opening: number; }

export default function Setup() {
  const { refresh, logout, me } = useAuth();
  const [clinicName, setClinicName] = useState("Smile Clinic");
  const [currency, setCurrency] = useState("PKR");
  const [effectiveFrom, setEffectiveFrom] = useState(today());
  const [partners, setPartners] = useState<PartnerRow[]>([
    { name: "Saad", pct: 50 },
    { name: "Hassan", pct: 50 },
  ]);
  const [accounts, setAccounts] = useState<AccountRow[]>([
    { name: "Saad Cash", kind: "personal", owner: 0, opening: 0 },
    { name: "Hassan Cash", kind: "personal", owner: 1, opening: 0 },
    { name: "Joint", kind: "joint", owner: "", opening: 0 },
  ]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);

  const totalPct = partners.reduce((s, p) => s + Number(p.pct || 0), 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (totalPct !== 100) {
      setErr("Partner shares must add up to 100%.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.setup({
        clinic_name: clinicName,
        currency,
        effective_from: effectiveFrom,
        partners: partners.map((p) => ({ name: p.name, share_num: Math.round(p.pct), share_den: 100 })),
        accounts: accounts.map((a) => ({
          name: a.name,
          kind: a.kind,
          owner_partner_index: a.kind === "personal" ? Number(a.owner) : null,
          opening_balance: Math.round(a.opening),
        })),
      });
      await refresh();
    } catch (e2: any) {
      if (e2?.status === 409) setLocked(true);
      else setErr(e2?.message ?? "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  if (locked) {
    return (
      <div className="center-screen">
        <Card style={{ width: 440, maxWidth: "92vw" }}>
          <h2>This clinic is already set up</h2>
          <p className="muted">
            You’re signed in as <b>{me?.email}</b> but you’re not on the allowlist. Ask the clinic
            owner to invite you, then sign in again.
          </p>
          <button className="ghost" onClick={logout}>Sign out</button>
        </Card>
      </div>
    );
  }

  return (
    <div className="center-screen">
      <Card style={{ width: 640, maxWidth: "94vw" }}>
        <h1>Set up your clinic</h1>
        <p className="muted" style={{ marginTop: 0 }}>One-time configuration. You’ll be the owner.</p>
        <form onSubmit={submit}>
          <div className="row">
            <Field label="Clinic name"><input value={clinicName} onChange={(e) => setClinicName(e.target.value)} required /></Field>
            <Field label="Currency"><input value={currency} onChange={(e) => setCurrency(e.target.value)} /></Field>
            <Field label="Shares effective from"><input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} /></Field>
          </div>

          <div className="section-head"><h2>Partners</h2><small>Total: {totalPct}%</small></div>
          {partners.map((p, i) => (
            <div className="row" key={i} style={{ marginBottom: 8 }}>
              <input placeholder="Name" value={p.name}
                onChange={(e) => setPartners(partners.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} required />
              <input type="number" placeholder="Share %" value={p.pct}
                onChange={(e) => setPartners(partners.map((x, j) => j === i ? { ...x, pct: Number(e.target.value) } : x))} />
              {partners.length > 1 && (
                <button type="button" className="danger sm" style={{ flex: "0 0 auto" }}
                  onClick={() => setPartners(partners.filter((_, j) => j !== i))}>Remove</button>
              )}
            </div>
          ))}
          <button type="button" className="ghost sm" onClick={() => setPartners([...partners, { name: "", pct: 0 }])}>+ Add partner</button>

          <div className="section-head" style={{ marginTop: 18 }}><h2>Accounts</h2></div>
          {accounts.map((a, i) => (
            <div className="row" key={i} style={{ marginBottom: 8 }}>
              <input placeholder="Account name" value={a.name}
                onChange={(e) => setAccounts(accounts.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} required />
              <select value={a.kind}
                onChange={(e) => setAccounts(accounts.map((x, j) => j === i ? { ...x, kind: e.target.value as any, owner: e.target.value === "joint" ? "" : 0 } : x))}>
                <option value="personal">Personal</option>
                <option value="joint">Joint</option>
              </select>
              {a.kind === "personal" ? (
                <select value={a.owner}
                  onChange={(e) => setAccounts(accounts.map((x, j) => j === i ? { ...x, owner: Number(e.target.value) } : x))}>
                  {partners.map((p, pi) => <option key={pi} value={pi}>{p.name || `Partner ${pi + 1}`}</option>)}
                </select>
              ) : <div className="muted" style={{ alignSelf: "center" }}>shared</div>}
              <input type="number" placeholder="Opening" value={a.opening}
                onChange={(e) => setAccounts(accounts.map((x, j) => j === i ? { ...x, opening: Number(e.target.value) } : x))} />
              {accounts.length > 1 && (
                <button type="button" className="danger sm" style={{ flex: "0 0 auto" }}
                  onClick={() => setAccounts(accounts.filter((_, j) => j !== i))}>Remove</button>
              )}
            </div>
          ))}
          <button type="button" className="ghost sm"
            onClick={() => setAccounts([...accounts, { name: "", kind: "personal", owner: 0, opening: 0 }])}>+ Add account</button>

          {err && <div className="banner warn" style={{ marginTop: 16 }}>{err}</div>}
          <div style={{ marginTop: 18 }} className="inline">
            <button disabled={busy}>{busy ? "Creating…" : "Create clinic"}</button>
            <button type="button" className="ghost" onClick={logout}>Sign out</button>
          </div>
        </form>
      </Card>
    </div>
  );
}
