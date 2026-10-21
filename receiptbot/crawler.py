"""Crawl fetched email messages for receipts and log them.

The crawler works on a JSON *dump* of messages so it can run fully offline
(tests) or from messages fetched read-only from Gmail by an agent/connector.

Dump format::

  {"messages": [{"id": "...", "thread_id": "...", "sender": "...",
                 "subject": "...", "date": "2026-10-11T12:00:00Z",
                 "snippet": "...", "body": "plain text body",
                 "attachments": [{"filename": "r.pdf", "path": "/abs/r.pdf"}]}]}
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .extract import extract
from .ocr import IMAGE_EXT, read_text

# Gmail search queries used when fetching (documented here; the fetch itself
# happens through a read-only connector).
GMAIL_QUERIES = [
    'receipt OR invoice OR "order confirmation" OR "your order" OR "payment received" '
    'OR "thank you for your purchase"',
    "subject:receipt OR subject:invoice OR (has:attachment filename:pdf (receipt OR invoice)) "
    "OR category:purchases",
    "from:(amazon OR uber OR lyft OR paypal OR stripe OR apple OR google OR doordash OR grubhub "
    "OR instacart OR airbnb OR square OR venmo OR microsoft) (order OR receipt OR total OR payment OR invoice)",
]

POSITIVE = re.compile(
    r"\b(receipt|invoice|order confirmation|your order|order #|order number|payment received|"
    r"thank you for your (purchase|order)|your [\w']+ order|amount paid|you paid|payment confirmation)\b", re.I)
NEGATIVE = re.compile(
    r"(unsuccessful|failed|declined|billing problem|problem with your payment|update .*payment method|"
    r"payment method update|renew your|will be canceled|cancellation|save up to|\d+% off|security alert|"
    r"statement available|terms of service|terms and conditions|pre-?order|sign in|new login|"
    r"added a (new )?card|unpaid invoice|final warning|reminder|is ready for printing|"
    r"could be the next winner|chance to win)", re.I)

MERCHANT_FROM_SUBJECT = [
    re.compile(r"receipt from ([A-Z][\w&.' -]+?)(?: #| \d|$)", re.I),
    re.compile(r"^your ([A-Z][\w&.' -]+?) (?:order|invoice|receipt)\b", re.I),
    re.compile(r"^([A-Z][\w&.' -]+?) (?:API )?invoice\b", re.I),
]
KNOWN_SENDERS = {
    "googleplay": "Google Play", "microsoft": "Microsoft",
    "amazon": "Amazon", "uber": "Uber", "lyft": "Lyft", "paypal": "PayPal", "apple": "Apple",
    "doordash": "DoorDash", "stripe": "Stripe",
}
SENDER_CATEGORY = {
    "Google Play": "software", "Microsoft": "software",
    "DoorDash": "food", "Uber": "travel", "Lyft": "travel",
}


def parse_since(s):
    m = re.fullmatch(r"(\d+)([dwm])", s or "")
    if not m:
        raise ValueError("--since must look like 90d, 12w or 3m")
    n, u = int(m.group(1)), m.group(2)
    return timedelta(days=n * {"d": 1, "w": 7, "m": 30}[u])


def html_to_text(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return "\n".join(re.sub(r"[ \t\xa0]+", " ", l).strip() for l in s.splitlines() if l.strip())


def _parse_dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_receipt(msg):
    """Return (bool, reason). Subject decides most cases; body must contain an amount."""
    subj = msg.get("subject", "") or ""
    head = subj + " " + (msg.get("snippet") or "")
    if NEGATIVE.search(subj):
        return False, "negative subject"
    has_pdf = any(a.get("filename", "").lower().endswith(".pdf") for a in msg.get("attachments", []))
    if not (POSITIVE.search(head) or (has_pdf and re.search(r"receipt|invoice", head, re.I))):
        return False, "no receipt keywords"
    body = msg.get("body") or ""
    if not re.search(r"\d[.,]\d{2}\b", body) and not msg.get("attachments"):
        return False, "no amount in body"
    return True, "ok"


PROCESSORS = {"stripe", "paypal", "square"}
MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}


def merchant_for(msg):
    subj = msg.get("subject", "")
    sender = (msg.get("sender") or "").lower()
    for k, v in KNOWN_SENDERS.items():
        if k in sender and k not in PROCESSORS:
            return v
    for rx in MERCHANT_FROM_SUBJECT:
        m = rx.search(subj)
        if m:
            name = m.group(1).strip()
            low = name.lower()
            for k, v in KNOWN_SENDERS.items():
                if k in low.replace(" ", "").replace("'", ""):
                    return v
            if low not in {"order", "the", "a"} and low[:3] not in MONTHS:
                return re.sub(r"\s+(Corporation|Corp\.?|Inc\.?|LLC|Ltd\.?)$", "", name)
    sender = (msg.get("sender") or "").lower()
    for k, v in KNOWN_SENDERS.items():
        if k in sender:
            return v
    return None


def analyse(msg):
    """Extract a receipt record from a message (body first, attachments override)."""
    att_texts = []
    for att in msg.get("attachments", []):
        p = att.get("path")
        if p and Path(p).exists() and (str(p).lower().endswith(".pdf") or Path(p).suffix.lower() in IMAGE_EXT):
            try:
                att_texts.append(read_text(p))
            except Exception:
                pass
    body = msg.get("body") or ""
    if "<" in body and ">" in body and re.search(r"</\w+>", body):
        body = html_to_text(body)
    # Attachments (the actual invoice/receipt) win; the email body is a fallback.
    rec = None
    text = body
    if att_texts:
        text = "\n".join(att_texts)
        rec = extract(text)
        if rec["total"] is None or "total" in rec["needs_review"]:
            rec = None
    if rec is None:
        text = body if not att_texts else body + "\n" + "\n".join(att_texts)
        rec = extract(body) if body.strip() else extract(text)
    review = set(rec["needs_review"])
    sent = _parse_dt(msg.get("date"))
    if rec["date"] and sent and rec["date"] > (sent + timedelta(days=1)).date().isoformat():
        rec["date"] = sent.date().isoformat()   # a receipt can't be dated after it was emailed

    m = merchant_for(msg)
    if m:
        rec["merchant"] = m
        review.discard("merchant")
    if not rec["date"]:
        d = _parse_dt(msg.get("date"))
        if d:
            rec["date"] = d.date().isoformat()
            review.discard("date")
    if rec["merchant"] in SENDER_CATEGORY:
        rec["category"] = SENDER_CATEGORY[rec["merchant"]]
        review.discard("category")
    if rec["tax"] is None and "tax" in review:
        review.discard("tax")      # many e-receipts have no tax line; record as None, not a guess
        rec["tax"] = None
    rec["needs_review"] = sorted(review)
    rec["raw_text"] = text
    return rec


def crawl(con, messages, since=None, now=None):
    from . import db
    now = now or datetime.now(timezone.utc)
    cutoff = now - since if since else None
    seen_ids = set()
    stats = {"scanned": 0, "receipts": 0, "added": 0, "skipped_existing": 0,
             "not_receipt": 0, "out_of_range": 0, "duplicates": 0, "zero_amount": 0, "added_ids": []}
    for msg in messages:
        mid = msg.get("id")
        if not mid or mid in seen_ids:
            stats["duplicates"] += 1
            continue
        seen_ids.add(mid)
        stats["scanned"] += 1
        d = _parse_dt(msg.get("date"))
        if cutoff and d and d < cutoff:
            stats["out_of_range"] += 1
            continue
        ok, _ = is_receipt(msg)
        if not ok:
            stats["not_receipt"] += 1
            continue
        if db.has_source(con, mid):
            stats["receipts"] += 1
            stats["skipped_existing"] += 1
            continue
        rec = analyse(msg)
        if rec["total"] == 0:
            stats["zero_amount"] += 1   # $0.00 invoice: nothing was spent, don't log an expense
            continue
        stats["receipts"] += 1
        atts = [a["path"] for a in msg.get("attachments", []) if a.get("path")]
        path = atts[0] if atts else f"gmail:{mid}"
        eid = db.add(con, rec, path, rec.pop("raw_text"),
                     source={"id": mid, "sender": msg.get("sender"), "subject": msg.get("subject")})
        stats["added"] += 1
        stats["added_ids"].append(eid)
    return stats


def load_dump(path):
    """Load a dump; relative attachment paths resolve against the dump's directory, then cwd."""
    base = Path(path).resolve().parent
    data = json.loads(Path(path).read_text())
    msgs = data["messages"] if isinstance(data, dict) else data
    for m in msgs:
        for a in m.get("attachments", []):
            p = a.get("path")
            if p and not Path(p).is_absolute():
                cand = base / Path(p).name
                a["path"] = str(cand if cand.exists() else Path(p).resolve())
    return msgs
