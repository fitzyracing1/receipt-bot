import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from receiptbot import db
from receiptbot.crawler import crawl, load_dump, is_receipt, parse_since, html_to_text, merchant_for

ROOT = Path(__file__).parent.parent
DUMP = ROOT / "examples" / "emails" / "example_emails.json"
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _crawl(tmp_path):
    con = db.connect(str(tmp_path / "c.db"))
    st = crawl(con, load_dump(DUMP), since=timedelta(days=90), now=NOW)
    return con, st


def test_crawl_stats_and_dedupe(tmp_path):
    con, st = _crawl(tmp_path)
    assert st["duplicates"] == 1          # ex-001 appears twice
    assert st["scanned"] == 7
    assert st["out_of_range"] == 1        # ex-007 is from January
    assert st["not_receipt"] == 2         # promo + failed payment
    assert st["zero_amount"] == 1         # $0.00 invoice
    assert st["receipts"] == 3 and st["added"] == 3


def test_crawl_fields(tmp_path):
    con, _ = _crawl(tmp_path)
    rows = {r["source_id"]: r for r in db.rows(con)}
    uber = rows["ex-001"]
    assert (uber["merchant"], uber["date"], uber["total"], uber["tax"], uber["currency"], uber["category"]) == \
        ("Uber", "2026-10-06", 19.87, 1.47, "USD", "travel")
    assert uber["source_sender"] == "receipts@uber.example.com"
    assert uber["receipt_path"] == "gmail:ex-001"
    bistro = rows["ex-002"]                # HTML body, European decimals
    assert (bistro["total"], bistro["tax"], bistro["currency"], bistro["category"]) == (14.40, 2.40, "EUR", "food")
    cloud = rows["ex-003"]                 # values come from the PDF attachment
    assert (cloud["merchant"], cloud["date"], cloud["total"], cloud["tax"]) == ("Cloudly", "2026-09-03", 21.60, 1.60)
    assert cloud["receipt_path"].endswith("example_invoice.pdf")


def test_crawl_is_incremental(tmp_path):
    con, _ = _crawl(tmp_path)
    st = crawl(con, load_dump(DUMP), since=timedelta(days=90), now=NOW)
    assert st["added"] == 0 and st["skipped_existing"] == 3
    assert len(db.rows(con)) == 3


def test_classifier():
    assert not is_receipt({"subject": "Billing Problem", "body": "$1.00"})[0]
    assert not is_receipt({"subject": "Your receipt", "body": "no amounts here"})[0]
    assert is_receipt({"subject": "Your Domino's Order", "body": "Total $12.00"})[0]


def test_helpers():
    assert parse_since("90d") == timedelta(days=90) and parse_since("2w") == timedelta(days=14)
    assert "Total 1.00" in html_to_text("<p>Total&nbsp;1.00</p>").replace("\xa0", " ")
    assert merchant_for({"subject": "Your receipt from Acme Corporation #1", "sender": "x@stripe.com"}) == "Acme"
    assert merchant_for({"subject": "Your Google Play Order Receipt from Jan 5", "sender": "googleplay-noreply@google.com"}) == "Google Play"


def test_cli_crawl(tmp_path):
    dbp = tmp_path / "e.db"
    run = lambda *a: subprocess.run([sys.executable, "-m", "receiptbot", "--db", str(dbp), *a],
                                    capture_output=True, text=True, cwd=ROOT)
    r = run("crawl", "--since", "3650d", "--from-json", str(DUMP))
    assert r.returncode == 0, r.stderr
    assert "4 added" in r.stdout          # wide window also picks up the January receipt
    assert "4 already logged" in run("crawl", "--since", "3650d", "--from-json", str(DUMP)).stdout
    assert run("crawl", "--since", "soon", "--from-json", str(DUMP)).returncode == 1


def test_old_db_migrates(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE expenses (id INTEGER PRIMARY KEY, merchant TEXT, date TEXT, total REAL, tax REAL,"
              " currency TEXT, category TEXT, needs_review TEXT NOT NULL DEFAULT '[]', receipt_path TEXT NOT NULL,"
              " raw_text TEXT, created_at TEXT)")
    c.commit(); c.close()
    con = db.connect(str(p))
    assert not db.has_source(con, "x")
