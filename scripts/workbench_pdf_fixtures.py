"""Reproducible non-sensitive PDF qualification inputs; these are test data, not live proof."""

import io
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle


def _font() -> str:
    paths = (Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    font = next((path for path in paths if path.is_file()), None)
    if font is None:
        raise RuntimeError("A local Unicode font is required for EN/RU/UK PDF qualification")
    if "QualificationSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("QualificationSans", str(font)))
    return "QualificationSans"


def pdf_bytes(
    *,
    pages: int = 1,
    table: bool = False,
    rows: int = 8,
    mixed: bool = False,
    scanned: bool = False,
    two_columns: bool = False,
    language: str = "en",
) -> bytes:
    """Create an audited layout with independently known table rows, page labels and image content."""
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=A4, invariant=1)
    font = _font()
    for page in range(1, pages + 1):
        canvas.setFont(font, 18)
        if not scanned:
            canvas.drawString(45, 800, f"Evidence section {page}")
            canvas.setFont(font, 10)
            labels = {
                "en": "Verified text evidence",
                "ru": "Проверенный текст документа",
                "uk": "Перевірений текст документа",
            }
            canvas.drawString(45, 775, labels[language])
            canvas.drawString(45, 755, f"PageMarker{page} reports measured water output in litres.")
        if table:
            data = [["Station", "Volume (litres)", "Quality code"]]
            data += [
                [f"Station{page}R{row}", str(1000 * page + row * 7), f"QA{page}R{row}"] for row in range(1, rows + 1)
            ]
            grid = Table(data, colWidths=[160, 150, 160])
            grid.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), font),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ]
                )
            )
            _width, height = grid.wrapOn(canvas, 480, 650)
            canvas.setFont(font, 11)
            canvas.drawString(45, 725, f"Table {page}: audited water output")
            grid.drawOn(canvas, 45, 710 - height)
        elif two_columns:
            for index in range(12):
                canvas.setFont(font, 10)
                canvas.drawString(45, 700 - index * 18, f"Left section observation {index}.")
                canvas.drawString(320, 700 - index * 18, f"Right section observation {index}.")
        elif not scanned:
            for index in range(5):
                canvas.drawString(
                    45, 710 - index * 18, f"Observed sample {page}-{index} has a verified textual record."
                )
        if mixed or scanned:
            image = Image.new("RGB", (800, 260), "white")
            drawing = ImageDraw.Draw(image)
            drawing.rectangle((15, 40, 260, 200), outline="black", width=5)
            drawing.rectangle((540, 40, 785, 200), outline="black", width=5)
            drawing.line((260, 120, 540, 120), fill="black", width=8)
            drawing.polygon(((540, 120), (515, 105), (515, 135)), fill="black")
            drawing.text((55, 100), "UNOBSERVED START", fill="black")
            drawing.text((580, 100), "UNOBSERVED END", fill="black")
            canvas.drawImage(ImageReader(image), 45, 250, width=480, height=156)
        canvas.showPage()
    canvas.save()
    return stream.getvalue()


def build_corpus(directory: Path) -> list[Path]:
    """Produce ten positive inputs and separate explicit negative/mixed-visual cases."""
    directory.mkdir(parents=True, exist_ok=True)
    cases = [
        ("text-one", {}),
        ("text-five", {"pages": 5}),
        ("text-twenty", {"pages": 20}),
        ("two-columns", {"two_columns": True}),
        ("numeric-units", {"table": True}),
        ("long-table", {"table": True, "rows": 30}),
        ("cross-page-table", {"table": True, "pages": 2}),
        ("caption-table", {"table": True, "rows": 15}),
        ("russian", {"language": "ru"}),
        ("ukrainian", {"language": "uk"}),
        ("mixed-figure", {"mixed": True}),
    ]
    paths: list[Path] = []
    for name, parameters in cases:
        path = directory / f"{name}.pdf"
        path.write_bytes(pdf_bytes(**parameters))
        paths.append(path)
    scanned = directory / "scanned-negative.pdf"
    scanned.write_bytes(pdf_bytes(scanned=True))
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(paths[0].read_bytes())))
    writer.encrypt("qualification-only")
    writer.write(directory / "encrypted-negative.pdf")
    (directory / "corrupt-negative.pdf").write_bytes(b"%PDF-1.7\nnot a valid document\n%%EOF")
    return paths
