// Typed API client. Holds the JWT, scopes every request, and — for the two
// quick-add flows — holds an entry locally and retries it if the network drops
// mid-save (PRD story 68), so a payment is never lost.

import type {
  Account, AuditLog, Case, Category, CategoryTotal, CollectorTotal, DashboardSummary,
  Employee, Me, Movement, MovementType, PartnerContribution, Partner, Patient, PatientDetail,
  Period, Procedure, ProcedureStat, Receivables, Reminder, SettlementStatement, TrendPoint,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string) || "/api";
const TOKEN_KEY = "ccr_token";
const QUEUE_KEY = "ccr_offline_queue";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new CustomEvent("ccr:unauthorized"));
    throw new ApiError(401, "Session expired — please sign in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- offline hold-and-retry queue (quick-add only) ---------------------------

interface QueuedEntry { id: string; label: string; path: string; body: unknown; }

function readQueue(): QueuedEntry[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}
function writeQueue(items: QueuedEntry[]) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
  window.dispatchEvent(new CustomEvent("ccr:queue", { detail: items.length }));
}
export function queueLength(): number {
  return readQueue().length;
}

// Returns { queued: true } if the network was unavailable and the entry was held.
async function postQuickAdd<T>(label: string, path: string, body: unknown): Promise<T | { queued: true }> {
  try {
    return await request<T>("POST", path, body);
  } catch (err) {
    // Only a genuine network failure is held; real API errors (4xx) surface.
    if (err instanceof ApiError) throw err;
    const items = readQueue();
    items.push({ id: crypto.randomUUID(), label, path, body });
    writeQueue(items);
    return { queued: true };
  }
}

export async function flushQueue(): Promise<number> {
  let items = readQueue();
  if (items.length === 0 || !getToken()) return 0;
  let flushed = 0;
  for (const item of [...items]) {
    try {
      await request("POST", item.path, item.body);
      items = items.filter((i) => i.id !== item.id);
      writeQueue(items);
      flushed++;
    } catch (err) {
      if (err instanceof ApiError) {
        // A held entry the server rejects can never succeed — drop it.
        items = items.filter((i) => i.id !== item.id);
        writeQueue(items);
      } else {
        break; // still offline; try again later
      }
    }
  }
  return flushed;
}

export function startQueueRetry() {
  const tick = () => void flushQueue();
  window.addEventListener("online", tick);
  setInterval(tick, 15000);
  tick();
}

// --- typed endpoints ---------------------------------------------------------

export const api = {
  // auth
  devLogin: (email: string, name?: string) =>
    request<{ access_token: string }>("POST", "/dev/login", { email, name }),
  me: () => request<Me>("GET", "/me"),
  setup: (body: unknown) => request<{ clinic_id: number }>("POST", "/setup", body),

  // config
  partners: () => request<Partner[]>("GET", "/partners"),
  accounts: () => request<Account[]>("GET", "/accounts"),
  createAccount: (body: unknown) => request<Account>("POST", "/accounts", body),
  updateAccount: (id: number, body: unknown) => request<Account>("PATCH", `/accounts/${id}`, body),
  categories: () => request<Category[]>("GET", "/categories"),
  createCategory: (name: string) => request<Category>("POST", "/categories", { name }),
  deleteCategory: (id: number) => request<void>("DELETE", `/categories/${id}`),
  procedures: () => request<Procedure[]>("GET", "/procedures"),
  createProcedure: (body: unknown) => request<Procedure>("POST", "/procedures", body),
  deleteProcedure: (id: number) => request<void>("DELETE", `/procedures/${id}`),
  employees: () => request<Employee[]>("GET", "/employees"),
  createEmployee: (body: unknown) => request<Employee>("POST", "/employees", body),
  deleteEmployee: (id: number) => request<void>("DELETE", `/employees/${id}`),
  shareWindows: () => request<any[]>("GET", "/share-windows"),
  createShareWindow: (body: unknown) => request<any>("POST", "/share-windows", body),

  // patients & cases
  patients: () => request<Patient[]>("GET", "/patients"),
  patient: (id: number) => request<PatientDetail>("GET", `/patients/${id}`),
  createPatient: (body: unknown) => request<Patient>("POST", "/patients", body),
  cases: () => request<Case[]>("GET", "/cases"),
  caseById: (id: number) => request<Case>("GET", `/cases/${id}`),
  createCase: (body: unknown) => request<Case>("POST", "/cases", body),
  discount: (id: number, body: unknown) => request<Case>("POST", `/cases/${id}/discount`, body),
  writeOff: (id: number, body: unknown) => request<Case>("POST", `/cases/${id}/write-off`, body),

  // money entry (quick-add held offline)
  takePayment: (body: unknown) => postQuickAdd<{ movement: Movement; case: Case }>("payment", "/payments", body),
  logExpense: (body: unknown) => postQuickAdd<Movement>("expense", "/expenses", body),
  transfer: (body: unknown) => request<Movement>("POST", "/transfers", body),
  capital: (body: unknown) => request<Movement>("POST", "/capital", body),
  drawing: (body: unknown) => request<Movement>("POST", "/drawings", body),
  refund: (body: unknown) => request<Movement>("POST", "/refunds", body),
  movements: (q = "") => request<Movement[]>("GET", `/movements${q}`),
  editMovement: (id: number, body: unknown) => request<Movement>("PATCH", `/movements/${id}`, body),
  voidMovement: (id: number) => request<void>("DELETE", `/movements/${id}`),
  restoreMovement: (id: number) => request<Movement>("POST", `/movements/${id}/restore`),

  // periods & settlement
  periods: () => request<Period[]>("GET", "/periods"),
  createPeriod: (body: unknown) => request<Period>("POST", "/periods", body),
  closePeriod: (id: number) => request<SettlementStatement>("POST", `/periods/${id}/close`),
  settlements: () => request<SettlementStatement[]>("GET", "/settlements"),
  settlement: (id: number) => request<SettlementStatement>("GET", `/settlements/${id}`),
  recordSettlementPayment: (id: number, body: unknown) =>
    request<Movement>("POST", `/settlements/${id}/payments`, body),

  // dashboard, reports, reminders
  dashboard: () => request<DashboardSummary>("GET", "/dashboard/summary"),
  pnl: (q = "") => request<{ income: number; expense: number; net_profit: number }>("GET", `/reports/pnl${q}`),
  byCategory: () => request<CategoryTotal[]>("GET", "/reports/by-category"),
  byProcedure: () => request<ProcedureStat[]>("GET", "/reports/by-procedure"),
  byCollector: () => request<CollectorTotal[]>("GET", "/reports/by-collector"),
  receivables: () => request<Receivables>("GET", "/reports/receivables"),
  trends: () => request<TrendPoint[]>("GET", "/reports/trends"),
  perPartner: () => request<PartnerContribution[]>("GET", "/reports/per-partner"),
  reminders: () => request<Reminder[]>("GET", "/reminders"),
  auditLogs: () => request<AuditLog[]>("GET", "/audit-logs"),
};

// Authenticated file download (exports carry the bearer token).
export async function downloadFile(path: string, filename: string) {
  const res = await fetch(BASE + path, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export type { MovementType };
