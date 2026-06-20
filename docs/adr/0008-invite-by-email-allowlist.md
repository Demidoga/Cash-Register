# Access by email allowlist; un-defer per-clinic invites

## Decision

The owner can grant another person access to the clinic by **adding their email** to the allowlist. This pulls "per-clinic invitations" forward from the deferred list in ADR-0005, but in the cheapest form that fits the existing auth:

**How an invite works:**
- Owner submits an email. The backend creates a `User` stub (email only, no `supabase_sub`/`full_name` yet) and a `Membership` linking that user to the clinic.
- **No email is sent and no token is issued.** The invitee gains access by signing in to Supabase (Google or email/password) with that email; `get_current_member` matches by email, finds the Membership, and lets them in. On first sign-in the stub is backfilled with `supabase_sub`/`full_name` from the JWT.
- The owner can **list** members (stubs without a `supabase_sub` show as *pending*) and **revoke** access (soft-delete the Membership). Re-inviting a revoked email **reactivates** the soft-deleted Membership rather than violating `uq_membership`.

**Access granted:** an invited Member gets the `partner` access tier — **full, co-equal access**, but is **not** a financial `Partner` (no settlement share, no `ShareWindow` change, settlement math untouched).

**Authorization:** the tiers (`owner | partner | staff`) remain **unenforced** in V1 with one exception — **only `owner` may invite, list, or revoke.** This is the app's first real role gate.

## Considered Options

- **Tokened, emailed invite link** (Invitation table, expiry, accept flow, an email integration) — rejected for V1: it adds infrastructure for a private two-doctor clinic where the owner can just tell the person to sign in.
- **Supabase native `inviteUserByEmail`** — rejected: ties us to Supabase email templates and still needs a webhook/first-login to create our `User`+`Membership`.
- **Invited user as a new financial `Partner`** — rejected: would force a new `ShareWindow`, dilute existing shares, and change every future settlement. Out of scope for "contribute to the register."

## Why

Authentication already proves email ownership (Supabase); the allowlist already authorizes by email. So "invite" collapses to "add a row to the allowlist" — no new trust machinery. Keeping the invitee out of the `Partner`/settlement model means a high-value but low-blast-radius feature. We accept that full co-equal access is broad, but the clinic is a tiny trusted partnership, and owner-gating the invite itself is the one guard that matters.

## Consequences

- `Membership.role`'s `partner` value is now overloaded: an **access tier**, distinct from the `Partner` entity (recorded in the glossary). Real per-tier permission enforcement is still deferred.
- A revoked user holding a still-valid Supabase JWT is blocked immediately at `get_current_member` (authorization, not authentication).
- Revoke must guard against removing the last owner / oneself.
- `get_current_member` still resolves a user's *first* Membership; harmless under the single-clinic invariant (ADR-0005) but must be revisited if a user is ever a member of two clinics.
- A future switch to tokened/emailed invites is a migration (new table + backfill), not a drop-in change.
