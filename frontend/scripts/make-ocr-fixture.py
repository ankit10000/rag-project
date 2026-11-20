"""Create only the synthetic browser fixture; no DB, provider, or evaluation inputs."""
from pathlib import Path
import hashlib
import pymupdf

text = (
    "ASTER HARBOR VISITOR POLICY\n\n"
    "An Aster Harbor day pass costs 83 credits.\n"
    "The day pass remains valid for 17 days.\n"
    "Aster Harbor does not operate a fax service.\n"
)
native = pymupdf.open()
page = native.new_page(width=600, height=500)
page.insert_textbox(pymupdf.Rect(35, 45, 565, 460), text, fontsize=20, lineheight=1.5)
png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
scan = pymupdf.open()
page = scan.new_page(width=600, height=500)
page.insert_image(page.rect, stream=png)
assert not page.get_text().strip()
target = Path(__file__).resolve().parents[1] / "tests/fixtures/aster-scan.pdf"
target.parent.mkdir(exist_ok=True)
data = scan.tobytes()
if target.exists():
    raise SystemExit("Fixture already exists; refusing to replace it.")
target.write_bytes(data)
print(hashlib.sha256(data).hexdigest(), target)
scan.close()
native.close()
