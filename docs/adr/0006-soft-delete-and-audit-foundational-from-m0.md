# Soft-delete and audit-stamping are foundational from Milestone 0

## Decision

Soft-deletes, the audit log, and `clinic_id` scoping are **data-model patterns baked into the first migration**, not features deferred to their own milestones. Every table is soft-delete-capable (`deleted_at`) and every write is audit-stamped (who/what/when) from day one — even though the user-facing surfaces (void/restore UI and the audit viewer in Milestone 6, exports in Milestone 8) ship much later.

## Why

Retrofitting "every write is soft and audited" into a live ledger is painful and error-prone, and — worse — an audit trail that starts late has permanent gaps: entries made before the trail existed can never be reconstructed. For a system whose whole value proposition is a trustworthy, recoverable record, the trail must be complete from the very first real entry. The cost of including these patterns from the first migration is small; the cost of adding them later is exactly the kind of rework we avoided by keeping `clinic_id`.

## Consequences

- Milestone 0's schema and write path include `deleted_at`, audit-stamping, and `clinic_id` from the start.
- Later milestones build only the *surfaces* over this foundation (restore, audit viewer, exports), not the foundation itself.
