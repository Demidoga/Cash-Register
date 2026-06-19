# Single-clinic in practice, multi-clinic-ready in schema

## Decision

V1 amends the PRD's "multi-tenant SaaS, architected general" stance. We build a **single-clinic app**, but keep one cheap architectural hook so going multi-clinic later is a migration, not a rewrite:

**Keep now:**
- One `Clinic` row, seeded once at setup.
- `clinic_id` on top-level tables, with queries scoped through one standard path.
- A simple **app-wide allowlist** — only invited people can log in.

**Defer until the app is actually sold to other clinics:**
- Postgres RLS / database-enforced isolation.
- The full cross-clinic tenant-isolation test suite.
- Public signup and "create a clinic workspace" onboarding.
- Per-clinic invitations.

## Why

The owner explicitly does not want to run a multi-clinic SaaS now, but "maybe someday." The expensive-to-retrofit part of multi-tenancy is the ownership column on every table + scoping every query — so we pay that tiny cost now (one column, an always-true filter). The genuinely heavy parts (RLS, isolation test matrix, signup/onboarding) don't change the schema and can be layered on later, so they wait. This avoids both gold-plating a business that may never exist and the painful retrofit if it does.

## Consequences

- The PRD user stories about creating/joining a clinic workspace and per-clinic invitation collapse into "log in via the allowlist" for V1.
- Tenant isolation is enforced only at the app layer in V1 (trivial with one clinic); RLS is a documented fast-follow gated on real multi-clinic use.
