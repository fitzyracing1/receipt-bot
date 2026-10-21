import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EX = ROOT / "examples"


def run(db, *args):
    return subprocess.run([sys.executable, "-m", "receiptbot", "--db", str(db), *args],
                          capture_output=True, text=True, cwd=ROOT)


def test_cli_full_flow(tmp_path):
    db = tmp_path / "expenses.db"
    for n in ["cafe_receipt.png", "taxi_receipt.png", "office_receipt.png", "hotel_invoice.pdf"]:
        r = run(db, "add", str(EX / n))
        assert r.returncode == 0, r.stderr
        assert "Added expense" in r.stdout
    out = run(db, "list").stdout
    assert "Blue Bottle Cafe" in out and "Harbor View Hotel" in out
    t = run(db, "total", "--month", "2026-10").stdout
    assert "62.51 USD" in t and "EUR" not in t
    t = run(db, "total").stdout
    assert "99.88 EUR" in t and "302.40 GBP" in t
    csvp = tmp_path / "out.csv"
    assert run(db, "export", "--csv", str(csvp)).returncode == 0
    rows = list(csv.DictReader(open(csvp)))
    assert len(rows) == 4
    assert all(Path(r["receipt_path"]).exists() for r in rows)


def test_cli_errors(tmp_path):
    db = tmp_path / "e.db"
    assert run(db, "add", "nope.png").returncode == 1
    assert run(db, "total", "--month", "Oct").returncode == 2
    assert "No expenses" in run(db, "list").stdout


def test_env_db(tmp_path):
    import os
    env = dict(os.environ, RECEIPTBOT_DB=str(tmp_path / "env.db"))
    r = subprocess.run([sys.executable, "-m", "receiptbot", "add", str(EX / "cafe_receipt.png")],
                       env=env, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and (tmp_path / "env.db").exists()
