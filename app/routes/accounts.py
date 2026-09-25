import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_conn
from app.money import cents_to_str

router = APIRouter()


@router.get("/accounts/{account_id}")
def get_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute(
        "SELECT id, client_name, balance FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {"id": row["id"], "client_name": row["client_name"], "balance": cents_to_str(row["balance"])}


@router.get("/accounts/{account_id}/positions")
def get_positions(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    # Single query joining positions to funds -- avoids the N+1 pattern of
    # issuing one SELECT per position. If the account has at least one
    # position this is the only query we need (its existence is implied by
    # the FK-backed row), keeping us at 1 SELECT for the common case.
    rows = conn.execute(
        """SELECT p.fund_code, p.units, f.name AS fund_name, f.nav
           FROM positions p JOIN funds f ON f.code = p.fund_code
           WHERE p.account_id = ?
           ORDER BY p.fund_code""",
        (account_id,),
    ).fetchall()
 
    if not rows:
        # No positions found -- could be a nonexistent account or simply an
        # account with none yet, so we still need to check (2nd SELECT).
        if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="account not found")
        return {"account_id": account_id, "positions": []}
 
    result = [
        {
            "fund_code": r["fund_code"],
            "fund_name": r["fund_name"],
            "units": f"{r['units']:.4f}",
            "market_value": f"{r['units'] * r['nav']:.2f}",
        }
        for r in rows
    ]
    return {"account_id": account_id, "positions": result}
 