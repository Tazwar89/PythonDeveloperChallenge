import base64
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_conn
from app.money import cents_to_str

router = APIRouter()

VALID_TYPES = {"deposit", "withdrawal", "transfer_in", "transfer_out"}


def _encode_cursor(created_at: str, txn_id: int) -> str:
    raw = f"{created_at}|{txn_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_str, id_str = raw.rsplit("|", 1)
        return created_at_str, int(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid cursor")


@router.get("/accounts/{account_id}/transactions")
def get_transactions(
    account_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if type is not None and type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {sorted(VALID_TYPES)}")

    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="account not found")

    query = "SELECT id, type, amount, created_at FROM transactions WHERE account_id = ?"
    params: list = [account_id]

    if type is not None:
        query += " AND type = ?"
        params.append(type)
    if from_ is not None:
        query += " AND date(created_at) >= ?"
        params.append(from_.isoformat())
    if to is not None:
        query += " AND date(created_at) <= ?"
        params.append(to.isoformat())
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        # Row-value comparison: strictly "older" than the last item seen,
        # with id as a tiebreaker for rows sharing a timestamp (seed data
        # does this a lot -- ORDER BY created_at alone is not stable).
        query += " AND (created_at, id) < (?, ?)"
        params.extend([cursor_created_at, cursor_id])

    # Fetch one extra row to know whether a next page exists, without a
    # separate COUNT query.
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit + 1)

    rows = conn.execute(query, params).fetchall()

    has_more = len(rows) > limit
    page = rows[:limit]

    next_cursor = _encode_cursor(page[-1]["created_at"], page[-1]["id"]) if has_more else None

    items = [
        {
            "id": r["id"],
            "type": r["type"],
            "amount": cents_to_str(r["amount"]),
            "created_at": r["created_at"],
        }
        for r in page
    ]
    return {"items": items, "next_cursor": next_cursor}
