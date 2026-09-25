import sqlite3

import pytest


def _seed_transactions(db_path, rows):
    """rows: list of (account_id, type, amount_cents, created_at_iso)"""
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO transactions (account_id, type, amount, created_at) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_unknown_account(client):
    assert client.get("/accounts/ACC-9999/transactions").status_code == 404


def test_invalid_type(client):
    r = client.get("/accounts/ACC-1001/transactions", params={"type": "bogus"})
    assert r.status_code == 422


def test_invalid_limit(client):
    assert client.get("/accounts/ACC-1001/transactions", params={"limit": 0}).status_code == 422
    assert client.get("/accounts/ACC-1001/transactions", params={"limit": 101}).status_code == 422


def test_invalid_cursor(client):
    r = client.get("/accounts/ACC-1001/transactions", params={"cursor": "not-valid-base64!!"})
    assert r.status_code == 400


def test_invalid_date(client):
    r = client.get("/accounts/ACC-1001/transactions", params={"from": "not-a-date"})
    assert r.status_code == 422


def test_basic_shape_and_newest_first(client, db_path):
    _seed_transactions(db_path, [
        ("ACC-1001", "deposit", 1000, "2026-08-01T10:00:00+00:00"),
        ("ACC-1001", "withdrawal", 500, "2026-08-02T10:00:00+00:00"),
    ])
    r = client.get("/accounts/ACC-1001/transactions")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["type"] == "withdrawal"  # newest first
    assert items[0]["amount"] == "5.00"
    assert items[1]["amount"] == "10.00"
    assert r.json()["next_cursor"] is None


def test_type_and_date_filters(client, db_path):
    _seed_transactions(db_path, [
        ("ACC-1001", "deposit", 1000, "2026-08-01T10:00:00+00:00"),
        ("ACC-1001", "withdrawal", 500, "2026-08-05T10:00:00+00:00"),
        ("ACC-1001", "deposit", 2000, "2026-08-10T10:00:00+00:00"),
    ])
    r = client.get("/accounts/ACC-1001/transactions", params={"type": "deposit"})
    assert [i["type"] for i in r.json()["items"]] == ["deposit", "deposit"]

    r = client.get("/accounts/ACC-1001/transactions", params={"from": "2026-08-02", "to": "2026-08-06"})
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "withdrawal"


def test_pagination_no_skip_or_repeat_with_duplicate_timestamps(client, db_path):
    # All rows share the same created_at -- the id tiebreaker must still
    # produce a stable, non-overlapping page split.
    _seed_transactions(db_path, [
        ("ACC-1001", "deposit", 100 * i, "2026-08-01T10:00:00+00:00")
        for i in range(1, 6)
    ])
    r1 = client.get("/accounts/ACC-1001/transactions", params={"limit": 2})
    page1 = r1.json()["items"]
    assert len(page1) == 2
    cursor = r1.json()["next_cursor"]
    assert cursor is not None

    r2 = client.get("/accounts/ACC-1001/transactions", params={"limit": 2, "cursor": cursor})
    page2 = r2.json()["items"]
    assert len(page2) == 2

    r3 = client.get("/accounts/ACC-1001/transactions", params={"limit": 2, "cursor": r2.json()["next_cursor"]})
    page3 = r3.json()["items"]
    assert len(page3) == 1
    assert r3.json()["next_cursor"] is None

    all_ids = [i["id"] for i in page1 + page2 + page3]
    assert len(all_ids) == len(set(all_ids)) == 5  # no repeats, none skipped


def test_pagination_unaffected_by_new_rows_inserted_mid_page(client, db_path):
    _seed_transactions(db_path, [
        ("ACC-1001", "deposit", 100, "2026-08-01T10:00:00+00:00"),
        ("ACC-1001", "deposit", 200, "2026-08-02T10:00:00+00:00"),
        ("ACC-1001", "deposit", 300, "2026-08-03T10:00:00+00:00"),
    ])
    r1 = client.get("/accounts/ACC-1001/transactions", params={"limit": 2})
    page1 = r1.json()["items"]
    cursor = r1.json()["next_cursor"]

    # A new, newer transaction arrives after the first page was fetched.
    _seed_transactions(db_path, [
        ("ACC-1001", "deposit", 999, "2026-08-04T10:00:00+00:00"),
    ])

    r2 = client.get("/accounts/ACC-1001/transactions", params={"limit": 2, "cursor": cursor})
    page2 = r2.json()["items"]

    # The cursor is anchored to the last row of page1, so the new row
    # (newer than everything already paged) must not appear on page2 and
    # nothing from page1 repeats.
    assert all(i["amount"] != "9.99" for i in page2)
    assert {i["id"] for i in page1}.isdisjoint({i["id"] for i in page2})
