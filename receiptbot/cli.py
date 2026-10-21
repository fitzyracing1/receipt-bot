import argparse
import csv
import os
import re
import sys
from collections import defaultdict

from . import db
from .extract import extract
from .ocr import read_text


def cmd_add(a, con):
    path = os.path.abspath(a.receipt)
    text = read_text(path)
    rec = extract(text)
    eid = db.add(con, rec, path, text)
    print(f"Added expense #{eid}")
    for k in ["merchant", "date", "total", "tax", "currency", "category"]:
        flag = "  [needs_review]" if k in rec["needs_review"] else ""
        print(f"  {k:9}: {rec[k]}{flag}")
    return 0


def cmd_list(a, con):
    rs = db.rows(con)
    if not rs:
        print("No expenses.")
        return 0
    print(f"{'ID':>3}  {'DATE':10}  {'MERCHANT':24}  {'TOTAL':>10} CUR  {'CATEGORY':9} REVIEW")
    for r in rs:
        tot = f"{r['total']:.2f}" if r["total"] is not None else "?"
        print(f"{r['id']:>3}  {r['date'] or '?':10}  {(r['merchant'] or '?')[:24]:24}  {tot:>10} "
              f"{r['currency']:3}  {r['category']:9} {','.join(r['needs_review']) or '-'}")
    return 0


def cmd_export(a, con):
    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=db.FIELDS)
        w.writeheader()
        for r in db.rows(con):
            r["needs_review"] = ";".join(r["needs_review"])
            w.writerow(r)
    print(f"Exported to {a.csv}")
    return 0


def cmd_total(a, con):
    if a.month and not re.fullmatch(r"\d{4}-\d{2}", a.month):
        print("--month must be YYYY-MM", file=sys.stderr)
        return 2
    sums = defaultdict(float)
    for r in db.rows(con, a.month):
        if r["total"] is not None:
            sums[r["currency"]] += r["total"]
    label = a.month or "all time"
    if not sums:
        print(f"Total ({label}): 0.00")
    for cur, s in sorted(sums.items()):
        print(f"Total ({label}): {s:.2f} {cur}")
    return 0


def cmd_crawl(a, con):
    from . import crawler
    since = crawler.parse_since(a.since)
    msgs = crawler.load_dump(a.from_json)
    st = crawler.crawl(con, msgs, since=since)
    print(f"Scanned {st['scanned']} messages (since {a.since}): {st['receipts']} receipts, "
          f"{st['added']} added, {st['skipped_existing']} already logged, "
          f"{st["not_receipt"]} not receipts, {st["zero_amount"]} $0.00 invoices skipped, {st['out_of_range']} out of range")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="receiptbot", description="Local receipt-reading expense logger")
    p.add_argument("--db", help="SQLite path (default: $RECEIPTBOT_DB or ./expenses.db)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("receipt"); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("list"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("export"); s.add_argument("--csv", required=True); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("total"); s.add_argument("--month"); s.set_defaults(fn=cmd_total)
    s = sub.add_parser("crawl", help="log receipts from a JSON dump of fetched emails")
    s.add_argument("--since", default="90d")
    s.add_argument("--from-json", required=True, help="dump of messages fetched read-only from Gmail")
    s.set_defaults(fn=cmd_crawl)
    a = p.parse_args(argv)
    con = db.connect(a.db)
    try:
        return a.fn(a, con)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()
