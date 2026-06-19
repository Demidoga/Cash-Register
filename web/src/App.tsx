import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { queueLength } from "./api";
import { Spinner, ToastHost } from "./ui";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import TakePayment from "./pages/TakePayment";
import LogExpense from "./pages/LogExpense";
import Patients from "./pages/Patients";
import PatientDetail from "./pages/PatientDetail";
import Journal from "./pages/Journal";
import Periods from "./pages/Periods";
import Reports from "./pages/Reports";
import Config from "./pages/Config";
import Audit from "./pages/Audit";

const NAV = [
  ["/", "Dashboard", "▦"],
  ["/pay", "Take payment", "＋"],
  ["/expense", "Log expense", "−"],
  ["/patients", "Patients", "☺"],
  ["/journal", "Journal", "≣"],
  ["/periods", "Close & settle", "⇄"],
  ["/reports", "Reports", "📈"],
  ["/config", "Configure", "⚙"],
  ["/audit", "Audit trail", "🛈"],
] as const;

function QueueIndicator() {
  const [n, setN] = useState(queueLength());
  useEffect(() => {
    const handler = (e: Event) => setN((e as CustomEvent).detail ?? queueLength());
    window.addEventListener("ccr:queue", handler);
    return () => window.removeEventListener("ccr:queue", handler);
  }, []);
  if (n === 0) return null;
  return <span className="badge amber" title="Entries held offline, retrying">{n} pending sync</span>;
}

function Shell() {
  const { me, logout } = useAuth();
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">₨</span>
          <span>Cash Register</span>
        </div>
        <nav className="nav">
          {NAV.map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <span aria-hidden>{icon}</span> {label}
            </NavLink>
          ))}
        </nav>
        <div className="spacer" />
        <div style={{ padding: 8, fontSize: "0.8rem" }} className="muted">
          {me?.email}
          <br />
          <span className="badge gray">{me?.role}</span>
        </div>
        <button className="ghost sm" onClick={logout}>Sign out</button>
      </aside>
      <main className="main">
        <div className="topbar">
          <div />
          <QueueIndicator />
        </div>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/pay" element={<TakePayment />} />
          <Route path="/expense" element={<LogExpense />} />
          <Route path="/patients" element={<Patients />} />
          <Route path="/patients/:id" element={<PatientDetail />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/periods" element={<Periods />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/config" element={<Config />} />
          <Route path="/audit" element={<Audit />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const { hasToken, me, loading } = useAuth();
  let body: React.ReactNode;
  if (!hasToken) body = <Login />;
  else if (loading) body = <div className="center-screen"><Spinner /></div>;
  else if (me) body = <Shell />;
  else body = <Setup />; // authenticated but no clinic membership yet
  return <ToastHost>{body}</ToastHost>;
}
