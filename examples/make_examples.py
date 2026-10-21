"""Generate EXAMPLE receipts (fake data) for demos and tests."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

RECEIPTS = {
    "cafe_receipt.png": [
        "Blue Bottle Cafe", "123 Market St, Springfield", "*** EXAMPLE DATA ***",
        "Date: 2026-10-03  08:14", "", "Latte              4.50", "Breakfast Sandwich 7.25",
        "Espresso           3.00", "Subtotal          14.75", "Tax                1.18",
        "Total        USD  15.93", "Thank you!"],
    "taxi_receipt.png": [
        "Metro Taxi Co", "*** EXAMPLE DATA ***", "Date: 10/12/2026", "Trip fare         32.00",
        "Airport toll       6.50", "Subtotal          38.50", "Tax                3.08",
        "Tip                5.00", "Total            $46.58", "Driver #4471"],
    "office_receipt.png": [
        "Paper Trail Office Supply", "*** EXAMPLE DATA ***", "Sep 28, 2026",
        "Printer paper     24.99", "Toner             59.00", "Stapler            8.49",
        "Subtotal          92.48", "VAT                7.40", "Total EUR         99.88"],
}
PDF = ("hotel_invoice.pdf", [
    "Harbor View Hotel", "EXAMPLE DATA - not a real invoice", "Invoice date: 2026-09-15",
    "Room - 2 nights          240.00", "Parking                   30.00",
    "Subtotal                 270.00", "Tax                       32.40",
    "Total Due  GBP           302.40"])


def make_png(name, lines):
    font = ImageFont.truetype(FONT, 28)
    img = Image.new("RGB", (720, 60 + 44 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((30, 30 + 44 * i), line, fill="black", font=font)
    img.save(HERE / name)


def make_pdf(name, lines):
    c = canvas.Canvas(str(HERE / name), pagesize=(420, 400))
    c.setFont("Courier", 12)
    for i, line in enumerate(lines):
        c.drawString(30, 360 - 20 * i, line)
    c.save()


if __name__ == "__main__":
    for n, l in RECEIPTS.items():
        make_png(n, l)
    make_pdf(*PDF)
    print("examples generated")
