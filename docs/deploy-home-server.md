# Deploy on a home Debian server — free (Tailscale Funnel)

Run the app on a Debian box at home, reachable from anywhere over HTTPS, for
**$0**: no domain, no open router ports, no certificates to manage.

## Is this really free?

| Piece | Cost |
| --- | --- |
| The server | Yours (just electricity). |
| Database + login (**Supabase** free tier) | Free. 500 MB is years of cash records; real logins included. A free project only sleeps after **7 days untouched** — daily clinic use never hits that, and if it ever does you un-pause it in one click, data intact. |
| Public HTTPS address (**Tailscale** free plan) | Free. Gives a stable `https://…ts.net` address via Funnel. |

Total: **$0.**

## What you end up with

```
partner → https://<server>.<tailnet>.ts.net → Tailscale edge (does HTTPS)
        → Funnel (no open ports, home IP hidden) → tailscaled on the server
        → web container (serves the app, proxies /api) → api container → Supabase
```

Two containers run (`api`, `web`); **Tailscale runs on the host**, not as a
container. The database and login live in Supabase — there is no database
container.

## Before you start, gather

- A **Debian server** you can SSH into.
- Your **Supabase values** (project ready): the **pooler** connection string
  (Project Settings → Database → *Connection pooling*, session mode, port 5432 —
  **not** the direct one), plus the **project URL** and **anon key** (Project
  Settings → API).
- **No domain needed.**

---

## 1. Install Docker on the server

```bash
curl -fsSL https://get.docker.com | sh      # Docker Engine + compose plugin
sudo usermod -aG docker "$USER"             # run docker without sudo
newgrp docker                               # apply the group now (or re-login)
docker compose version                      # sanity check
```

## 2. Get the code onto the server

```bash
git clone <your-repo-url> CashRegister
cd CashRegister
```

## 3. Fill in the environment file

```bash
cp .env.example .env
```

Edit `.env`:

| Key | Value |
| --- | --- |
| `DATABASE_URL` | Supabase **pooler** string (session mode, port 5432). |
| `JWT_SECRET` | `openssl rand -hex 32`, **or** your Supabase JWT secret. |
| `DEV_LOGIN_ENABLED` | `false` — must stay false in a real deployment. |
| `SUPABASE_URL` | Your Supabase project URL (lets the API verify real logins). |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | Your project URL + anon key. |
| `CLOUDFLARE_TUNNEL_TOKEN` | **Leave blank** — only used for the custom-domain alternative below. |

> The two `VITE_` values are **baked into the frontend at build time**. If you
> change them later, rebuild: `docker compose up -d --build web`.

## 4. Build and start the app

```bash
docker compose up -d --build     # starts api + web (cloudflared stays off)
docker compose ps                # both Up?
```

On first boot the API runs `alembic upgrade head` and creates the schema in
Supabase. At this point the app is live only on the server's loopback
(`127.0.0.1:80`) — Tailscale puts it online next.

## 5. Put it online with Tailscale Funnel

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                # opens a login link — sign in (Google/GitHub/email)
```

In the Tailscale admin console (login.tailscale.com/admin) → **DNS**: turn on
**MagicDNS** and **HTTPS Certificates** (both needed for the `ts.net` cert).

Then expose port 80 publicly:

```bash
sudo tailscale funnel --bg 80    # follow any link it prints to enable Funnel once
sudo tailscale funnel status     # shows your public https://<host>.<tailnet>.ts.net URL
```

That URL is your app — stable, HTTPS, openable from any phone or laptop. (If your
Tailscale version dislikes the flags, `tailscale funnel --help` shows its syntax.)

## 6. First-run setup

1. Open `https://<host>.<tailnet>.ts.net`. HTTPS is live, so PWA "install" and
   the offline-save queue work.
2. In **Supabase** → Authentication → URL Configuration, add that same URL to
   **Site URL** and **Redirect URLs** so Google/email sign-in returns to the app.
3. Sign in and run **/setup** — the first user to do so becomes the **owner**,
   who can then invite the other partners by email.

---

## Alternatives

**Keep it private instead of public** — only your own devices can reach it
(each partner installs the free Tailscale app and signs into your tailnet; free
plan allows 3 users):

```bash
sudo tailscale serve --bg 80     # instead of `funnel`
```

**Use a custom domain instead of the `*.ts.net` name** — switch to the Cloudflare
tunnel (needs a domain on Cloudflare; costs a few $/yr). Set
`CLOUDFLARE_TUNNEL_TOKEN` in `.env`, point the tunnel's public hostname at
`http://web:80` in the Cloudflare dashboard, then:

```bash
docker compose --profile tunnel up -d --build
```

## Day-to-day

```bash
docker compose logs -f api                    # backend logs
git pull && docker compose up -d --build      # ship a new version
docker compose down                           # stop the app
sudo tailscale funnel status                  # check the public URL
sudo tailscale funnel reset                   # take it offline
```

## Notes & gotchas

- **No router ports are opened.** Tailscale only makes outbound connections, and
  `web` is bound to `127.0.0.1`, so the LAN can't reach it directly either.
- **Backups live in Supabase**, not on the home server. Supabase has automated
  backups; you can also `pg_dump` the pooler string on a schedule.
- **Keep it patched:** `sudo apt update && sudo apt upgrade` on the host, and
  re-pull images now and then (`docker compose pull && docker compose up -d`).
- **`DEV_LOGIN_ENABLED` must be `false`** in any real deployment.
