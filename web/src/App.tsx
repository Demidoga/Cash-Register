import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Gauge, TrendUp, TrendDown, Users, Notebook, Scales, ChartBar, GearSix,
  ClockCounterClockwise, List, CloudArrowUp, SignOut,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useAuth } from "./auth";
import { queueLength } from "./api";
import { Spinner, ThemeToggle, ToastHost } from "./ui";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import LogIncome from "./pages/LogIncome";
import LogExpense from "./pages/LogExpense";
import Patients from "./pages/Patients";
import PatientDetail from "./pages/PatientDetail";
import Journal from "./pages/Journal";
import Periods from "./pages/Periods";
import Reports from "./pages/Reports";
import Config from "./pages/Config";
import Audit from "./pages/Audit";

type NavItem = readonly [path: string, label: string, icon: Icon];
const NAV_GROUPS: { label?: string; items: NavItem[] }[] = [
  { items: [["/", "Dashboard", Gauge]] },
  {
    label: "Record",
    items: [
      ["/income", "Log income", TrendUp],
      ["/expense", "Log expense", TrendDown],
      ["/journal", "Journal", Notebook],
    ],
  },
  {
    label: "Manage",
    items: [
      ["/patients", "Patients", Users],
      ["/periods", "Close & settle", Scales],
    ],
  },
  {
    label: "Admin",
    items: [
      ["/reports", "Reports", ChartBar],
      ["/config", "Configure", GearSix],
      ["/audit", "Audit trail", ClockCounterClockwise],
    ],
  },
];

function QueueIndicator() {
  const [n, setN] = useState(queueLength());
  useEffect(() => {
    const handler = (e: Event) => setN((e as CustomEvent).detail ?? queueLength());
    window.addEventListener("ccr:queue", handler);
    return () => window.removeEventListener("ccr:queue", handler);
  }, []);
  if (n === 0) return null;
  return (
    <span className="badge amber" title="Entries held offline, retrying automatically">
      <CloudArrowUp size={14} weight="bold" /> {n} pending sync
    </span>
  );
}

function Shell() {
  const { me, logout } = useAuth();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const close = () => setNavOpen(false);

  return (
    <div className="app">
      <div className={`scrim${navOpen ? " open" : ""}`} onClick={close} aria-hidden />

      <aside className={`sidebar${navOpen ? " open" : ""}`}>
        <div className="brand">
          <span className="logo">₨</span>
          <span>Cash Register</span>
        </div>
        <nav className="nav">
          {NAV_GROUPS.map((group, gi) => (
            <div key={gi}>
              {group.label && <div className="nav-label">{group.label}</div>}
              {group.items.map(([to, label, IconCmp]) => (
                <NavLink key={to} to={to} end={to === "/"} onClick={close}>
                  <IconCmp className="nav-icon" size={19} aria-hidden />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="spacer" />
        <div className="sidebar-foot">
          <div className="sidebar-user">
            <span className="email">{me?.email}</span>
            <span className="inline" style={{ justifyContent: "space-between" }}>
              <span className="badge gray">{me?.role}</span>
              <button className="ghost sm inline" onClick={logout}>
                <SignOut size={15} /> Sign out
              </button>
            </span>
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="topbar-left">
            <button className="icon-btn topbar-burger" onClick={() => setNavOpen(true)} aria-label="Open navigation">
              <List size={20} />
            </button>
            <span className="brand-mini">
              <span className="logo">₨</span> Cash Register
            </span>
          </div>
          <div className="topbar-right">
            <QueueIndicator />
            <ThemeToggle />
          </div>
        </div>

        <div className="view" key={location.pathname}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/income" element={<LogIncome />} />
            <Route path="/expense" element={<LogExpense />} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/patients/:id" element={<PatientDetail />} />
            <Route path="/journal" element={<Journal />} />
            <Route path="/periods" element={<Periods />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/config" element={<Config />} />
            <Route path="/audit" element={<Audit />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const { hasToken, me, loading, error } = useAuth();
  let body: React.ReactNode;
  if (!hasToken) body = <Login />;
  else if (loading) body = <div className="center-screen"><Spinner /></div>;
  else if (me) body = <Shell />;
  // A 401 means the bearer wasn't accepted (expired/dropped token) — that's a
  // re-auth case, not a missing clinic. Don't strand the user on Setup; the
  // auth layer is concurrently trying to refresh and re-mirror the token.
  else if (error?.status === 401) body = <Login />;
  else body = <Setup />; // genuinely authenticated but no clinic membership yet
  return <ToastHost>{body}</ToastHost>;
}
