from pathlib import Path

from docx import Document
from reportlab.pdfgen import canvas

from app.source_extraction import extract_text


def test_extract_text_from_txt(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("hello from txt", encoding="utf-8")
    text = extract_text(path)
    assert "hello from txt" in text


def test_extract_text_from_docx(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("hello from docx")
    document.save(str(path))

    text = extract_text(path)
    assert "hello from docx" in text


def test_extract_text_from_pdf(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, "hello from pdf")
    pdf.save()

    text = extract_text(path)
    assert "hello from pdf" in text
