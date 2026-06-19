import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Field } from "../ui";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("saad@smileclinic.test");
  const [name, setName] = useState("Saad");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email.trim().toLowerCase(), name.trim() || undefined);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <Card style={{ width: 380, maxWidth: "92vw" }}>
        <div className="brand" style={{ padding: "0 0 14px" }}>
          <span className="logo">₨</span>
          <span>Clinic Cash Register</span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          Sign in to your clinic. (Dev sign-in; production uses Google / email via Supabase.)
        </p>
        <form onSubmit={submit}>
          <Field label="Email">
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
          </Field>
          <Field label="Name (first time only)">
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          {err && <div className="banner warn">{err}</div>}
          <button disabled={busy} style={{ width: "100%" }}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </Card>
    </div>
  );
}
