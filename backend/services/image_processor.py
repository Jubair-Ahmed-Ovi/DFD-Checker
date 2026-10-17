import base64, io
from pathlib import Path
from PIL import Image
import fitz

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _to_png_bytes(img: Image.Image) -> bytes:
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def convert_to_png_bytes(path: str) -> bytes:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        doc = fitz.open(path)
        if len(doc) == 0:
            raise ValueError("PDF has no pages.")
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        data = pix.tobytes("png")
        doc.close()
        return data
    if ext == ".svg":
        import cairosvg
        return cairosvg.svg2png(url=path, output_width=2200)
    if ext not in SUPPORTED_IMAGES:
        raise ValueError("Unsupported file format. Use PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF, SVG or PDF.")
    with Image.open(path) as img:
        return _to_png_bytes(img.convert("RGBA"))


def as_data_url(png_bytes: bytes) -> str:
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"
