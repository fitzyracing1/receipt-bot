# receipt-bot

A small, local-only receipt-reading expense logger inspired by Expensify's SmartScan.
OCR with Tesseract, text PDFs with `pdftotext`, field extraction with plain regex/heuristics.
No paid APIs, no network.

## Install
```bash
sudo apt-get install tesseract-ocr poppler-utils
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Usage
```bash
python -m receiptbot add examples/cafe_receipt.png   # OCR + extract + store
python -m receiptbot add examples/hotel_invoice.pdf  # text PDF via pdftotext
python -m receiptbot list
python -m receiptbot export --csv out.csv
python -m receiptbot total                 # per-currency totals
python -m receiptbot total --month 2026-10
```
Database: `./expenses.db` by default; override with `--db PATH` or `RECEIPTBOT_DB`.

## What gets extracted
merchant, date (ISO), total, tax, currency, category (food / travel / office / software / lodging / other),
plus the absolute path to the original receipt and the raw OCR text.

Fields the heuristics aren't confident about go in `needs_review` instead of being guessed silently, e.g.
no total line found (largest amount used as a fallback), subtotal + tax + tip doesn't add up to the total,
no currency marker (defaults to USD), or no clear/tied category.

## Examples
`examples/` holds **synthetic EXAMPLE DATA** receipts (3 PNGs + 1 text PDF). Regenerate with
`python examples/make_examples.py`.

## Tests
```bash
.venv/bin/python -m pytest -q
```
All tests are lit when the suite passes; any dark test means a failure. Tesseract must be installed.

## License
MIT, see `LICENSE`.

## Crawling Gmail for receipts
`crawl` scans email messages for receipts, extracts fields from the body and from PDF/image
attachments (attachments win when they parse), and logs them with their source
(`source_id` = Gmail message id, `source_sender`, `source_subject`). Messages already logged are
skipped, so reruns are incremental. Duplicate message ids in one run are counted once.

```bash
python -m receiptbot crawl --since 90d --from-json out/gmail-dump.json
python -m receiptbot export --csv out/gmail-receipts.csv
```

Fetching is done read-only through a Gmail connector (search, read message, download attachment).
Nothing sends, deletes, labels or modifies mail. The fetched messages are written to a JSON dump
(format in `receiptbot/crawler.py`), and the crawler runs offline on that dump. The queries used are
in `crawler.GMAIL_QUERIES`.

Classification: the subject/snippet must look like a receipt (receipt, invoice, order confirmation,
your order, payment received, ...). Promos, failed or declined payments, billing problems, renewals,
security alerts and similar are rejected, and the body or an attachment must contain an amount.
$0.00 invoices are counted but not logged as expenses. `--since` accepts `90d`, `12w` or `3m`.

Offline example emails (EXAMPLE DATA) are in `examples/emails/`. `out/` holds real crawl output
and is git-ignored.
