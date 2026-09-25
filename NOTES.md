# NOTES.md

## What I don't trust
The cursor-pagination tiebreaker (`(created_at, id) < (?, ?)`) relies on SQLite's row-value comparison syntax — it works on 3.45.1 but I'd confirm the minimum SQLite version this service actually deploys against before shipping. I'd also double-check the `to_cents` rounding (`ROUND_HALF_UP`) against whatever rounding convention the bank's core ledger uses, since a mismatch there would cause reconciliation drift rather than a visible bug. The `positions.units`/`funds.nav` fields are still `REAL`; I didn't see a failing test around them, but float-based unit/NAV math is the same class of bug we just fixed for money, so I'd want a second look before trusting it at scale. Finally, my new transaction tests only seed data directly into SQLite rather than going through real deposit/withdrawal endpoints (which don't exist yet), so they verify the query logic but not any future write path into that table.

## AI use
I used Claude to help diagnose the failing test suite (money precision, the missing `from_balance_after`/`to_balance_after` columns, idempotency handling, and the N+1 query on `/positions`), to draft the transactions endpoint and its tests for TKT-212, and to review PR #17 for REVIEW.md. I read, ran, and verified everything against pytest myself before committing.
