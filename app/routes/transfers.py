import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException

from app.db import get_conn
from app.models import TransferRequest, TransferResponse
from app.money import cents_to_str, to_cents

router = APIRouter()


@router.post("/transfers", status_code=201, response_model=TransferResponse)
def create_transfer(
    req: TransferRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # If this key has already been used, return the original response
    # without moving money again.
    if idempotency_key:
        existing = conn.execute(
            "SELECT id, from_balance_after, to_balance_after FROM transfers WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            return {
                "transfer_id": existing["id"],
                "from_balance": cents_to_str(existing["from_balance_after"]),
                "to_balance": cents_to_str(existing["to_balance_after"]),
            }
 
    if req.from_account == req.to_account:
        raise HTTPException(status_code=422, detail="from_account and to_account must differ")
 
    amount_cents = to_cents(req.amount)
    if amount_cents <= 0:
        raise HTTPException(status_code=422, detail="amount must be positive")
 
    src = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (req.from_account,)).fetchone()
    dst = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (req.to_account,)).fetchone()
    if src is None or dst is None:
        raise HTTPException(status_code=404, detail="account not found")
    if src["balance"] < amount_cents:
        raise HTTPException(status_code=409, detail="insufficient funds")
 
    new_src = src["balance"] - amount_cents
    new_dst = dst["balance"] + amount_cents
    transfer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
 
    try:
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_src, req.from_account))
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_dst, req.to_account))
        conn.execute(
            """INSERT INTO transfers
               (id, from_account, to_account, amount, created_at, idempotency_key,
                from_balance_after, to_balance_after)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (transfer_id, req.from_account, req.to_account, amount_cents, now,
             idempotency_key, new_src, new_dst),
        )
        conn.execute(
            "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) "
            "VALUES (?, 'transfer_out', ?, ?, ?)",
            (req.from_account, amount_cents, now, transfer_id),
        )
        conn.execute(
            "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) "
            "VALUES (?, 'transfer_in', ?, ?, ?)",
            (req.to_account, amount_cents, now, transfer_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Concurrent request used the same idempotency key and won the race;
        # roll back our own attempt and return the winner's response.
        conn.rollback()
        existing = conn.execute(
            "SELECT id, from_balance_after, to_balance_after FROM transfers WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            return {
                "transfer_id": existing["id"],
                "from_balance": cents_to_str(existing["from_balance_after"]),
                "to_balance": cents_to_str(existing["to_balance_after"]),
            }
        raise
 
    return {"transfer_id": transfer_id, "from_balance": cents_to_str(new_src), "to_balance": cents_to_str(new_dst)}
