import json
import os
import sqlite3

SCHEMA = """CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merchant TEXT, date TEXT, total REAL, tax REAL, currency TEXT, category TEXT,
  needs_review TEXT NOT NULL DEFAULT '[]',
  receipt_path TEXT NOT NULL, raw_text TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  source_id TEXT, source_sender TEXT, source_subject TEXT)"""
SOURCE_COLS = ["source_id", "source_sender", "source_subject"]
FIELDS = ["id", "merchant", "date", "total", "tax", "currency", "category", "needs_review", "receipt_path",
          "source_id", "source_sender", "source_subject"]


def connect(path=None):
    path = path or os.environ.get("RECEIPTBOT_DB", "expenses.db")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(expenses)")}
    for c in SOURCE_COLS:  # migrate older DBs
        if c not in have:
            con.execute(f"ALTER TABLE expenses ADD COLUMN {c} TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_source ON expenses(source_id) WHERE source_id IS NOT NULL")
    return con


def has_source(con, source_id):
    return con.execute("SELECT 1 FROM expenses WHERE source_id=?", (source_id,)).fetchone() is not None


def add(con, rec, receipt_path, raw_text, source=None):
    source = source or {}
    cur = con.execute(
        "INSERT INTO expenses (merchant,date,total,tax,currency,category,needs_review,receipt_path,raw_text,"
        "source_id,source_sender,source_subject) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (rec["merchant"], rec["date"], rec["total"], rec["tax"], rec["currency"],
         rec["category"], json.dumps(rec["needs_review"]), receipt_path, raw_text,
         source.get("id"), source.get("sender"), source.get("subject")))
    con.commit()
    return cur.lastrowid


def rows(con, month=None):
    q = f"SELECT {','.join(FIELDS)} FROM expenses"
    args = ()
    if month:
        q += " WHERE date LIKE ?"
        args = (month + "-%",)
    out = []
    for r in con.execute(q + " ORDER BY date, id", args):
        d = dict(r)
        d["needs_review"] = json.loads(d["needs_review"])
        out.append(d)
    return out
