# PR.md

## What was wrong
- `/transfers` used raw float amounts, causing precision drift (e.g. ten `0.10` transfers left balances like `998.9999999999998`) and unformatted balance strings (`"750"` instead of `"750.00"`).
- The `INSERT INTO transfers` never populated `from_balance_after` / `to_balance_after`, violating the NOT NULL schema and failing every transfer.
- `Idempotency-Key` handling was unimplemented (`Header` wasn't even imported), so retried requests moved money twice.
- `/accounts/{id}/positions` issued one SELECT per position (N+1), instead of a single join.

## What I changed
- Added `app/money.py` to convert amounts to integer cents (`to_cents`) and format them back (`cents_to_str`), used consistently in `transfers.py` and `accounts.py`.
- Populated `from_balance_after`/`to_balance_after` on insert.
- Implemented idempotency: check for an existing `transfers` row by key first; catch the UNIQUE-constraint race via `IntegrityError` and return the winning response.
- Rewrote `/positions` as a single `JOIN` query.
- Added tests for the same-account transfer guard and the non-positive/zero-cents amount guard, both previously untested.

## What I chose not to change and why
- Left `positions.units`/`funds.nav` as `REAL` rather than migrating to integer-scaled types — out of scope for this ticket and no test exercised precision loss there.
