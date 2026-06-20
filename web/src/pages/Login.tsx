import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Field } from "../ui";

export default function Login() {
  const { supabaseEnabled } = useAuth();
  return (
    <div className="center-screen">
      <Card style={{ width: 380, maxWidth: "92vw" }}>
        <div className="brand" style={{ padding: "0 0 14px" }}>
          <span className="logo">₨</span>
          <span>Clinic Cash Register</span>
        </div>
        {supabaseEnabled ? <SupabaseLogin /> : <DevLogin />}
      </Card>
    </div>
  );
}

// --- Production: Google + email/password via Supabase ------------------------

function SupabaseLogin() {
  const { signInWithGoogle, signInWithPassword, signUpWithPassword } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function google() {
    setBusy(true);
    setErr(null);
    try {
      await signInWithGoogle(); // redirects to Google
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Google sign-in failed");
      setBusy(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setNotice(null);
    try {
      if (mode === "signin") {
        await signInWithPassword(email.trim().toLowerCase(), password);
      } else {
        await signUpWithPassword(email.trim().toLowerCase(), password, name.trim() || undefined);
        setNotice("Check your inbox to confirm your email, then sign in.");
        setMode("signin");
      }
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        Sign in to your clinic.
      </p>

      <button className="ghost" disabled={busy} onClick={google} style={{ width: "100%" }}>
        <GoogleGlyph /> Continue with Google
      </button>

      <div className="divider">or</div>

      <form onSubmit={submit}>
        <Field label="Email">
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </Field>
        {mode === "signup" && (
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        )}
        <Field label="Password">
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
            minLength={6}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
          />
        </Field>
        {notice && <div className="banner">{notice}</div>}
        {err && <div className="banner warn">{err}</div>}
        <button disabled={busy} style={{ width: "100%" }}>
          {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
        </button>
      </form>

      <p className="muted" style={{ textAlign: "center", marginBottom: 0 }}>
        {mode === "signin" ? "No account yet? " : "Already have an account? "}
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setErr(null);
            setNotice(null);
            setMode(mode === "signin" ? "signup" : "signin");
          }}
        >
          {mode === "signin" ? "Create one" : "Sign in"}
        </a>
      </p>
    </>
  );
}

// --- Dev fallback: no Supabase configured -----------------------------------

function DevLogin() {
  const { devLogin } = useAuth();
  const [email, setEmail] = useState("saad@smileclinic.test");
  const [name, setName] = useState("Saad");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await devLogin(email.trim().toLowerCase(), name.trim() || undefined);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        Dev sign-in (Supabase not configured). Set VITE_SUPABASE_URL and
        VITE_SUPABASE_ANON_KEY to enable Google / email sign-in.
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
    </>
  );
}

function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden style={{ verticalAlign: "-3px", marginRight: 8 }}>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8a12 12 0 1 1 7.9-21l5.7-5.7A20 20 0 1 0 24 44a20 20 0 0 0 19.6-23.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8A12 12 0 0 1 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7A20 20 0 0 0 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2A12 12 0 0 1 12.7 28l-6.5 5A20 20 0 0 0 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3a12 12 0 0 1-4.1 5.6l6.2 5.2C40.9 35.9 44 30.5 44 24c0-1.2-.1-2.4-.4-3.5z" />
    </svg>
  );
}
