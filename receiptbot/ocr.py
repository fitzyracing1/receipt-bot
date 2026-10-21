"""Turn a receipt file (image or PDF) into text."""
import shutil
import subprocess
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}


def read_text(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(p)
    if ext in IMAGE_EXT:
        return _ocr_image(p)
    if ext == ".txt":
        return p.read_text()
    raise ValueError(f"unsupported file type: {ext}")


def _pdf_text(p):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext (poppler-utils) not installed")
    out = subprocess.run(["pdftotext", "-layout", str(p), "-"],
                         capture_output=True, text=True, check=True).stdout
    if out.strip():
        return out
    # scanned PDF: rasterise and OCR
    if shutil.which("pdftoppm"):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["pdftoppm", "-png", "-r", "300", str(p), f"{d}/pg"], check=True)
            return "\n".join(_ocr_image(x) for x in sorted(Path(d).glob("pg*.png")))
    return out


def _ocr_image(p):
    import pytesseract
    from PIL import Image, ImageOps
    img = ImageOps.grayscale(Image.open(p))
    if img.width < 1000:
        f = 1000 / img.width
        img = img.resize((int(img.width * f), int(img.height * f)))
    return pytesseract.image_to_string(img, config="--psm 6")
