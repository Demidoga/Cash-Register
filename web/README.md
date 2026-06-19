# Clinic Cash Register — Web (PWA)

React + Vite installable PWA that consumes the FastAPI backend. Covers the full
V1: onboarding, the two quick-add flows (with an offline hold-and-retry queue),
patients/cases, dashboard intelligence, close & settle, corrections, reports,
exports, and the audit trail.

## Develop

```bash
cd web
npm install
npm run dev        # http://localhost:5173, proxies /api -> http://localhost:8000
```

Point the proxy at a different API with `VITE_API_TARGET=http://host:port npm run dev`,
or set `VITE_API_BASE` to call an absolute API URL directly.

## Build

```bash
npm run build      # type-checks then emits dist/ (with PWA service worker + manifest)
npm run preview
```

## Auth

Dev uses the backend `/dev/login` endpoint (email → signed JWT) so the whole app
runs locally without Supabase. In production, swap the login screen for Supabase
Google / email auth and disable `DEV_LOGIN_ENABLED` on the API.

## Offline resilience (PRD 68-69)

The app is an installable PWA. The two quick-add flows (take payment / log
expense) hold an entry in `localStorage` if the network drops mid-save and retry
automatically when back online — a payment is never lost. A "pending sync" badge
shows the held count.
