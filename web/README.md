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

The login screen has two modes, chosen automatically:

- **Supabase (real Google + email/password)** — active when `VITE_SUPABASE_URL`
  and `VITE_SUPABASE_ANON_KEY` are set. Supabase runs the Google OAuth flow and
  email/password auth, issues a JWT, and FastAPI verifies it. The app never sees
  a password.
- **Dev login** — the fallback when those vars are absent. Calls the backend
  `/dev/login` endpoint (email → signed JWT) so the whole app runs locally
  without a Supabase project.

### Enabling real Google sign-in

1. **Create a Supabase project** (free tier is fine). From **Project Settings →
   API** copy the **Project URL** and **anon/publishable key** into
   `web/.env.local` (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`). See
   `.env.example`.
2. **Backend secret.** From the same page copy the **JWT Secret** (the legacy
   HS256 secret) and set it as `JWT_SECRET` on the API. This is what lets
   FastAPI verify Supabase's tokens. Also set `DEV_LOGIN_ENABLED=false` in
   production so `/dev/login` returns 404.
3. **Google credential.** In Google Cloud Console create an **OAuth 2.0 Client
   ID** (Web application). Add Supabase's callback —
   `https://<your-project-ref>.supabase.co/auth/v1/callback` — as an authorized
   redirect URI. Copy the client ID + secret into Supabase under
   **Authentication → Providers → Google**, and enable the provider.
4. **Redirect URLs.** In Supabase **Authentication → URL Configuration** add
   your app origins (e.g. `http://localhost:5173` and your production URL) to the
   redirect allow-list — the app sends users back to `window.location.origin`.
5. **Allowlist the user.** A valid Google login is not enough on its own: the
   email must also have a Membership row in this app (PRD story 7), otherwise the
   API returns 403 "not on the clinic allowlist". Seed the first owner via the
   setup flow / a Membership row.

## Offline resilience (PRD 68-69)

The app is an installable PWA. The two quick-add flows (take payment / log
expense) hold an entry in `localStorage` if the network drops mid-save and retry
automatically when back online — a payment is never lost. A "pending sync" badge
shows the held count.
