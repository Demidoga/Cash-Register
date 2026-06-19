import { createContext, useCallback, useContext, useState } from "react";
import { rupees } from "./format";

export function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div className="card" style={style}>{children}</div>;
}

export function Stat({ label, value, tone }: { label: string; value: number; tone?: "pos" | "neg" }) {
  return (
    <div className="card stat">
      <span className="label">{label}</span>
      <span className={`value ${tone ?? ""}`}>{rupees(value)}</span>
    </div>
  );
}

export function Money({ n }: { n: number }) {
  return <span style={{ color: n < 0 ? "var(--red)" : undefined }}>{rupees(n)}</span>;
}

export function Field({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      {label}
      {children}
    </label>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <div className="list-empty">{label ?? "Loading…"}</div>;
}

export function Badge({ tone, children }: { tone: "green" | "red" | "amber" | "gray"; children: React.ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

// --- tiny toast system -------------------------------------------------------

interface ToastValue { show: (msg: string, kind?: "ok" | "error") => void; }
const ToastCtx = createContext<ToastValue>({ show: () => {} });

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "error" } | null>(null);
  const show = useCallback((msg: string, kind: "ok" | "error" = "ok") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      {toast && <div className={`toast ${toast.kind}`}>{toast.msg}</div>}
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
