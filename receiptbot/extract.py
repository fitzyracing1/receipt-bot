"""Regex/heuristic field extraction. Low-confidence fields are flagged."""
import re
from datetime import datetime

AMT = r"(-?\d{1,3}(?:[,.]\d{3})*[.,]\d{2}|\d+[.,]\d{2})"

CATEGORIES = {
    "food": ["restaurant", "cafe", "coffee", "bistro", "grill", "pizza", "burger",
             "espresso", "latte", "sandwich", "diner", "bakery", "kitchen", "food",
             "lunch", "dinner", "breakfast", "bar", "tip", "grocery", "market"],
    "travel": ["airline", "airways", "flight", "taxi", "cab", "uber", "lyft", "hotel",
               "inn", "fare", "parking", "train", "rail", "fuel", "gas", "boarding",
               "baggage", "mileage", "toll"],
    "office": ["office", "paper", "printer", "toner", "stapler", "pens", "notebook",
               "staples", "supplies", "ink", "folders", "desk"],
    "software": ["subscription", "software", "license", "saas", "cloud", "hosting"],
    "lodging": ["room", "night", "lodging", "suite", "resort"],
}

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_CODES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "INR", "MXN"]

DATE_PATTERNS = [
    (r"\b(\d{4})-(\d{2})-(\d{2})\b", "%Y-%m-%d"),
    (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", "%m/%d/%Y"),
    (r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b", "%m/%d/%y"),
    (r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", "%d.%m.%Y"),
    (r"\b([A-Z][a-z]{2,8})\.? (\d{1,2}),? (\d{4})\b", "%b %d %Y"),
    (r"\b(\d{1,2}) ([A-Z][a-z]{2,8}) (\d{4})\b", "%d %b %Y"),
]

SKIP_MERCHANT = re.compile(r"(\b(example|sample|receipt|invoice|tax|vat|date|total|subtotal|tel|phone)\b|www|http|\d{3}[- ]\d{3}|\d+[.,]\d{2}\b)", re.I)


def _amount(s):
    s = s.replace(" ", "")
    if s.count(".") > 1 and "," not in s:
        raise ValueError(s)
    if re.search(r",\d{2}$", s) and "." not in s[-3:]:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return round(float(s), 2)


DATE_KEYS = re.compile(r"(invoice date|date paid|order date|purchase date|transaction date|date of issue|^date\b)", re.I)


def _parse_date(text):
    # lines labelled as the invoice/order date win over billing periods etc.
    for line in text.splitlines():
        if DATE_KEYS.search(line.strip()):
            d = _parse_date_any(line)
            if d:
                return d
    return _parse_date_any(text)


def _parse_date_any(text):
    for pat, fmt in DATE_PATTERNS:
        for m in re.finditer(pat, text):
            g = m.groups()
            raw = " ".join(g) if "%b" in fmt else m.group(0)
            f = fmt
            if "%b" in fmt:
                raw = raw.replace(",", "")
                for ff in (fmt, fmt.replace("%b", "%B")):
                    try:
                        return datetime.strptime(raw[:len(raw)], ff).date().isoformat()
                    except ValueError:
                        pass
                continue
            try:
                d = datetime.strptime(raw, f).date()
                if 2000 <= d.year <= 2100:
                    return d.isoformat()
            except ValueError:
                continue
    return None


def _line_amount(lines, keywords, exclude=()):
    for line in reversed(lines):
        low = line.lower()
        if any(k in low for k in keywords) and not any(x in low for x in exclude):
            for a in reversed(re.findall(AMT, line)):
                try:
                    return _amount(a)
                except ValueError:
                    continue
    return None


def extract(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    review = []

    merchant = None
    for line in lines[:6]:
        if SKIP_MERCHANT.search(line) or len(re.sub(r"[^A-Za-z]", "", line)) < 3:
            continue
        merchant = re.sub(r"\s{2,}", " ", line).strip(" -*#")
        break
    if not merchant:
        review.append("merchant")

    date = _parse_date(text)
    if not date:
        review.append("date")

    total = None
    m = re.search(r"(?:amount paid|total paid)\D{0,20}" + AMT, text, re.I) or \
        re.search(r"\$\s?" + AMT + r"\s+paid\b", text, re.I)
    if m:
        try:
            total = _amount(m.group(1))
        except ValueError:
            total = None
    if total is None:
        total = _line_amount(lines, ["grand total", "total due", "amount due", "total"],
                             exclude=["subtotal", "sub total", "sub-total", "total tax",
                                      "excluding tax", "excl. tax", "before tax"])
    if total is None:
        amts = []
        for a in re.findall(AMT, text):
            try:
                amts.append(_amount(a))
            except ValueError:
                pass
        total = max(amts) if amts else None
        review.append("total")  # fallback guess, or missing

    tax = _line_amount(lines, ["tax", "vat", "gst", "hst"])
    if tax is None:
        review.append("tax")

    subtotal = _line_amount(lines, ["subtotal", "sub total", "sub-total"])
    if total is not None and subtotal is not None:
        tip = _line_amount(lines, ["tip", "gratuity"]) or 0.0
        if abs(subtotal + (tax or 0) + tip - total) > 0.02 and "total" not in review:
            review.append("total")

    currency = None
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            currency = code
            break
    if not currency:
        for sym, code in CURRENCY_SYMBOLS.items():
            if sym in text:
                currency = code
                break
    if not currency:
        currency = "USD"
        review.append("currency")

    low = text.lower()
    scores = {c: sum(len(re.findall(rf"\b{k}\b", low)) for k in kws) for c, kws in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    category = best if scores[best] > 0 else "other"
    if scores[best] == 0 or sorted(scores.values())[-2] == scores[best]:
        review.append("category")

    return {"merchant": merchant, "date": date, "total": total, "tax": tax,
            "currency": currency, "category": category, "needs_review": review}
