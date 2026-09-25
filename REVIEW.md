# REVIEW.md — PR #17 (Ledger sync + client search)

## Comments

**1. `app/routes/search.py:14` — blocker**
Problem: `name` is interpolated directly into the SQL string via an f-string (`LIKE '%{name}%'`), a textbook SQL injection vector — anyone hitting `/accounts/search` controls the query.
Fix: use a parameterized query, e.g. `conn.execute("SELECT id, client_name FROM accounts WHERE client_name LIKE ? ORDER BY client_name", (f"%{name}%",))`.

**2. `app/routes/search.py:17-18` — should-fix**
Problem: bare `except Exception: return {"results": []}` swallows every error, including bugs unrelated to "no results" (e.g. a broken query), and silently reports them as an empty result set to the caller.
Fix: remove the broad catch, or narrow it to the specific exception you expect and let anything else propagate/log.

**3. `app/routes/transfers.py` (added call to `post_transfer`) — blocker**
Problem: the ledger call happens *after* `conn.commit()`, with no error handling. If it raises after exhausting retries, the client gets an unhandled 500 even though the transfer already succeeded locally — no way to distinguish "failed" from "succeeded but ledger sync failed," and no compensating/retry-later mechanism.
Fix: either don't block the response on ledger sync (fire-and-forget with an async outbox/retry job) or catch the failure, still return success, and record the sync failure for reconciliation.

**4. `app/routes/transfers.py` (same call) — should-fix**
Problem: `post_transfer` isn't passed the request's `Idempotency-Key`, so a client retry (or the ledger's own network retry) can create duplicate ledger-side entries even though local dedupe prevents duplicate local transfers.
Fix: forward the idempotency key in the ledger payload.

**5. `app/services/ledger_client.py:12-21` (`with_retry`) — should-fix**
Problem: `time.sleep` inside a synchronous retry wrapper blocks the request-handling thread for up to ~3.5s total under ledger flakiness, directly inside `create_transfer`'s request path.
Fix: move retry/dispatch off the request path (background task/queue), or at minimum cap total retry time well below the client's timeout expectations.

**6. `app/services/ledger_client.py:30` — nit**
Problem: `datetime.now()` is naive (no tz), inconsistent with the rest of the codebase's UTC convention.
Fix: `datetime.now(timezone.utc).isoformat()`.

**7. `app/routes/transfers.py` (account_number lookup) — nit**
Problem: re-queries `accounts` for `account_number` after `src`/`dst` were already fetched earlier in the same function — redundant round trip.
Fix: select `account_number` in the original `src`/`dst` queries and reuse it.

## Decision
**Request changes** — #1 and #3 are blockers (security and data-consistency respectively) and need to be addressed before merge.
