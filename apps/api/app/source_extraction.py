import logging
from collections.abc import Generator
from pathlib import Path

from docx import Document
from pypdf import PdfReader

logger = logging.getLogger(__name__)

PAGES_PER_BATCH = 20


def extract_text_from_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text_from_docx(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()


def extract_text_from_pdf(path: Path) -> str:
    """Extract all text from a PDF at once (small files)."""
    return "\n".join(_iter_pdf_text(path))


def extract_pdf_pages_batched(path: Path, batch_size: int = PAGES_PER_BATCH) -> Generator[str, None, None]:
    """Yield text in batches of `batch_size` pages. Each yield is the text for that batch."""
    reader = PdfReader(str(path))
    total = len(reader.pages)
    logger.info("PDF extraction starting: %d pages, batch_size=%d", total, batch_size)

    batch_texts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            batch_texts.append(page.extract_text() or "")
        except Exception:
            logger.warning("PDF page %d extraction failed, skipping", i, exc_info=True)
            batch_texts.append("")

        if len(batch_texts) >= batch_size or i == total - 1:
            yield "\n".join(batch_texts)
            batch_texts = []


def _iter_pdf_text(path: Path) -> Generator[str, None, None]:
    reader = PdfReader(str(path))
    for page in reader.pages:
        yield page.extract_text() or ""


def extract_text(path: Path) -> str:
    extension = path.suffix.lower()
    if extension == ".txt":
        return extract_text_from_txt(path)
    if extension == ".docx":
        return extract_text_from_docx(path)
    if extension == ".pdf":
        return extract_text_from_pdf(path)
    raise ValueError(f"unsupported file type: {extension}")
