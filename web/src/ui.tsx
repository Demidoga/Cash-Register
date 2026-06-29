import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Moon, PencilSimple, Sun, X } from "@phosphor-icons/react";
import { rupees } from "./format";
import type { Movement } from "./types";

export function Card({ children, className, style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return <div className={`card${className ? ` ${className}` : ""}`} style={style}>{children}</div>;
}

export function Stat({
  label, value, tone, icon, hint,
}: {
  label: string; value: number; tone?: "pos" | "neg";
  icon?: React.ReactNode; hint?: string;
}) {
  const iconTone = tone === "pos" ? "pos" : tone === "neg" ? "neg" : "accent";
  return (
    <div className="card stat">
      <div className="stat-top">
        <span className="label">{label}</span>
        {icon && <span className={`stat-icon ${iconTone}`} aria-hidden>{icon}</span>}
      </div>
      <span className={` value ${tone ?? ""}`}>{rupees(value)}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Money({ n }: { n: number }) {
  return <span style={{ color: n < 0 ? "var(--neg)" : undefined, fontVariantNumeric: "tabular-nums" }}>{rupees(n)}</span>;
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

// Loading placeholder: a skeleton that mirrors content shape (no spinners).
export function Spinner({ label }: { label?: string }) {
  return (
    <div className="skeleton" role="status" aria-busy="true" aria-label={label ?? "Loading"}>
      <div className="skeleton-bar w-60" />
      <div className="skeleton-bar w-80" />
      <div className="skeleton-bar w-40" />
    </div>
  );
}

export function Badge({ tone, children }: { tone: "green" | "red" | "amber" | "gray"; children: React.ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

// A compact, read-only "recent entries" panel: the history that sits beside the
// quick-add forms (log income / log expense). `detail` renders the per-row
// description; `fullDetail` (optional) provides the hover overlay rows.
export function MovementHistory({
  title, loading, movements, detail, fullDetail, empty, onEdit,
}: {
  title: string;
  loading: boolean;
  movements: Movement[] | null;
  detail: (m: Movement) => React.ReactNode;
  fullDetail?: (m: Movement) => [string, string][];
  empty: string;
  // When provided, each row gets an edit button that loads it back into the form.
  onEdit?: (m: Movement) => void;
}) {
  return (
    <Card>
      <div className="section-head"><h2>{title}</h2></div>
      {loading ? (
        <Spinner />
      ) : movements?.length ? (
        <table className="history-table entries">
          <thead><tr><th>Date</th><th>Detail</th><th className="num">Amount</th></tr></thead>
          <tbody>
            {movements.map((m) => (
              <tr key={m.id}>
                <td className="muted">{m.date}</td>
                <td className={`muted${fullDetail ? " detail-cell" : ""}`} tabIndex={fullDetail ? 0 : undefined}>
                  {detail(m)}
                  {fullDetail && (
                    <div className="detail-pop" role="tooltip">
                      <div className="dp-head">
                        <span className="dp-type">{m.type}</span>
                        <span className="dp-amt">{rupees(m.amount)}</span>
                      </div>
                      <div className="dp-date">{m.date}</div>
                      <dl>
                        {fullDetail(m).map(([k, v]) => (
                          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
                        ))}
                      </dl>
                    </div>
                  )}
                </td>
                <td className={`num${onEdit ? " actions-cell" : ""}`}>
                  <span className={onEdit ? "row-slide" : undefined}>{rupees(m.amount)}</span>
                  {onEdit && (
                    <span className="row-actions">
                      <button type="button" aria-label="Edit entry" title="Edit" onClick={() => onEdit(m)}>
                        <PencilSimple size={14} />
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="list-empty">{empty}</div>
      )}
    </Card>
  );
}

// --- theme (light / dark, defaulting to system) ------------------------------

function storedTheme(): "light" | "dark" | null {
  try {
    const v = localStorage.getItem("ccr:theme");
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}
function systemTheme(): "light" | "dark" {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => storedTheme() ?? systemTheme());

  // When the user has no explicit preference, follow OS changes live.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { if (!storedTheme()) setTheme(systemTheme()); };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      try { localStorage.setItem("ccr:theme", next); } catch { /* ignore */ }
      document.documentElement.dataset.theme = next;
      return next;
    });
  }, []);

  return { theme, toggle };
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
    >
      {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
    </button>
  );
}

// --- tiny toast system -------------------------------------------------------

// An optional action turns the toast into an "undo"-style affordance.
interface ToastAction { label: string; onClick: () => void; }
interface ToastValue { show: (msg: string, kind?: "ok" | "error", action?: ToastAction) => void; }
const ToastCtx = createContext<ToastValue>({ show: () => {} });

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "error"; action?: ToastAction } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const show = useCallback((msg: string, kind: "ok" | "error" = "ok", action?: ToastAction) => {
    if (timer.current) clearTimeout(timer.current);
    setToast({ msg, kind, action });
    // An actionable toast (e.g. Undo) lingers longer so it can be acted on.
    timer.current = setTimeout(() => setToast(null), action ? 7000 : 3200);
  }, []);
  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      {toast && (
        <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
          <span className="toast-dot" aria-hidden />
          {toast.msg}
          {toast.action && (
            <button
              type="button"
              className="toast-action"
              onClick={() => { setToast(null); toast.action!.onClick(); }}
            >
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

// --- modal (centered dialog over a dimming scrim) ----------------------------

export function Modal({
  title, onClose, children,
}: { title: string; onClose: () => void; children: React.ReactNode }) {
  // Esc closes; clicking the scrim (but not the panel) closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal card" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="section-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
