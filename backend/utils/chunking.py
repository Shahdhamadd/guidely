"""Turning a document file into text, then into chunks small enough to embed."""

from pypdf import PdfReader

from utils.config import CHUNK_WORDS, SUPPORTED_TYPES
from utils.errors import AppError


def parse_file(path):
    """Return the plain text of a .txt, .md or .pdf file, or raise AppError if it can't be read."""
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_TYPES:
        raise AppError(f"{path.name}: unsupported file type '{suffix}'. Use .txt, .md or .pdf", 400)

    try:
        if suffix == ".pdf":
            reader = PdfReader(path)
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            text = path.read_text(encoding="utf-8")
    except Exception:
        raise AppError(f"{path.name}: the file is corrupted or could not be read")

    if not text.strip():
        raise AppError(f"{path.name}: the file contains no readable text")

    return text


def split_into_sections(text):
    """Split on "# Heading" lines. Returns (heading, body) pairs; text before the first heading is "Introduction"."""
    sections = []
    heading = "Introduction"
    lines = []

    for line in text.splitlines():
        if line.startswith("#"):
            if "\n".join(lines).strip():
                sections.append((heading, "\n".join(lines)))
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)

    if "\n".join(lines).strip():
        sections.append((heading, "\n".join(lines)))

    return sections


def split_long_paragraph(paragraph, max_words):
    """Only used when a single paragraph is longer than a whole chunk."""
    words = paragraph.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def chunk_section(body, max_words):
    """Group whole paragraphs into chunks of at most max_words, without cutting a paragraph in half."""
    paragraphs = []
    for paragraph in body.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            paragraphs.extend(split_long_paragraph(paragraph, max_words))

    chunks = []
    current = []
    current_words = 0
    for paragraph in paragraphs:
        size = len(paragraph.split())
        if current and current_words + size > max_words:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
        current.append(paragraph)
        current_words += size

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_document(file_name, text, max_words=CHUNK_WORDS):
    """Return the chunks of one document. A chunk never crosses a section, so it can be cited as "file > section"."""
    chunks = []
    for heading, body in split_into_sections(text):
        for piece in chunk_section(body, max_words):
            chunks.append({
                "file": file_name,
                "section": heading,
                "text": piece,
            })
    return chunks


def chunk_to_embedding_text(chunk):
    """The heading is embedded with the chunk so a chunk from the middle of a section keeps its topic."""
    return f"{chunk['section']}\n{chunk['text']}"
