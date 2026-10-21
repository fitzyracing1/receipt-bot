from pathlib import Path
import pytest
from receiptbot.ocr import read_text
from receiptbot.extract import extract

EX = Path(__file__).parent.parent / "examples"
EXPECTED = {
    "cafe_receipt.png": ("Blue Bottle Cafe", "2026-10-03", 15.93, 1.18, "USD", "food"),
    "taxi_receipt.png": ("Metro Taxi Co", "2026-10-12", 46.58, 3.08, "USD", "travel"),
    "office_receipt.png": ("Paper Trail Office Supply", "2026-09-28", 99.88, 7.40, "EUR", "office"),
    "hotel_invoice.pdf": ("Harbor View Hotel", "2026-09-15", 302.40, 32.40, "GBP", "travel"),
}


@pytest.mark.parametrize("name", EXPECTED)
def test_example_extraction(name):
    r = extract(read_text(EX / name))
    assert (r["merchant"], r["date"], r["total"], r["tax"], r["currency"], r["category"]) == EXPECTED[name]
    assert r["needs_review"] == []


def test_flags_missing_fields():
    r = extract("???\n12.00\n7.50\n")
    for f in ["merchant", "date", "total", "tax", "currency", "category"]:
        assert f in r["needs_review"]
    assert r["total"] == 12.00  # fallback guess, flagged


def test_flags_inconsistent_total():
    r = extract("Joe's Diner\n2026-01-02\nSubtotal 10.00\nTax 1.00\nTotal $50.00\n")
    assert "total" in r["needs_review"]


def test_date_formats_and_european_amount():
    r = extract("Le Bistro\n03.02.2026\nTVA 1,20\nTotal EUR 12,50\n")
    assert r["date"] == "2026-02-03" and r["total"] == 12.50 and r["currency"] == "EUR"


def test_unsupported_type(tmp_path):
    f = tmp_path / "x.doc"; f.write_text("hi")
    with pytest.raises(ValueError):
        read_text(f)
