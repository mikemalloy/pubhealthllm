"""
MMWR PDF Parser and ChromaDB Vector Database Builder.

Reads MMWR PDFs from disk, extracts text (LlamaParse if API key
available, otherwise PyPDF2), splits into overlapping chunks, embeds
them, and stores in a persistent ChromaDB collection.

The build is idempotent: documents already present in ChromaDB are
identified by their source filename hash and skipped on subsequent
runs.

Usage:
    python -m data_ingestion.build_vector_db
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PDF_DIR = Path(__file__).parents[2] / "data" / "mmwr_pdfs"
CHROMA_DIR = Path(__file__).parents[2] / "data" / "chroma_db"
COLLECTION_NAME = "mmwr_reports"

# Text chunking parameters — tuned for MMWR report prose
CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 150     # overlap between consecutive chunks
MIN_CHUNK_LENGTH = 100  # discard very short fragments

# Embedding model — Sentence Transformers runs locally, no API key needed.
# Uses all-MiniLM-L6-v2 by default (fast, good quality for dense retrieval).
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def _extract_text_llamaparse(pdf_path: Path) -> Optional[str]:
    """
    Extract text from a PDF using LlamaParse (cloud API).

    Requires LLAMA_CLOUD_API_KEY in environment.  Returns None if the
    key is absent or the API call fails, triggering fallback to PyPDF2.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text string, or None on failure.
    """
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        return None

    try:
        from llama_parse import LlamaParse  # type: ignore

        parser = LlamaParse(
            api_key=api_key,
            result_type="text",
            verbose=False,
        )
        documents = parser.load_data(str(pdf_path))
        return "\n\n".join(doc.text for doc in documents)
    except Exception as exc:
        logger.warning("LlamaParse failed for %s: %s", pdf_path.name, exc)
        return None


def _extract_text_pypdf2(pdf_path: Path) -> str:
    """
    Extract text from a PDF using PyPDF2 (local, no API key needed).

    PyPDF2 is less accurate on complex layouts but sufficient for the
    plain-text MMWR reports.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Concatenated page text.
    """
    try:
        import PyPDF2  # type: ignore

        text_parts: list[str] = []
        with open(pdf_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning("PyPDF2 failed for %s: %s", pdf_path.name, exc)
        return ""


def extract_text(pdf_path: Path) -> str:
    """
    Extract text from a PDF, preferring LlamaParse and falling back
    to PyPDF2.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text (empty string if both extractors fail).
    """
    text = _extract_text_llamaparse(pdf_path)
    if text:
        logger.debug("LlamaParse extracted text from %s", pdf_path.name)
        return text

    logger.debug("Using PyPDF2 for %s", pdf_path.name)
    return _extract_text_pypdf2(pdf_path)


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split a long text string into overlapping chunks.

    Tries to split on paragraph boundaries (double newline) first.
    If a paragraph is longer than chunk_size it is split mid-text.

    Args:
        text:       The full document text.
        chunk_size: Target maximum characters per chunk.
        overlap:    Characters of overlap between consecutive chunks.

    Returns:
        List of text chunk strings.
    """
    if not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # If adding this paragraph would overflow, flush the current chunk
        if len(current) + len(para) > chunk_size and current:
            chunks.append(current.strip())
            # Carry over the tail for overlap
            current = current[-overlap:] + "\n\n" + para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    # Filter out very short fragments (usually header/footer noise)
    return [c for c in chunks if len(c) >= MIN_CHUNK_LENGTH]


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------


def get_chroma_collection() -> chromadb.Collection:
    """
    Return (or create) the persistent ChromaDB collection for MMWR reports.

    Uses a local Sentence Transformers embedding function so no
    external embedding API is needed.

    Returns:
        ChromaDB Collection object.
    """
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def _doc_id(pdf_path: Path, chunk_index: int) -> str:
    """
    Stable unique ID for a document chunk.

    ID is derived from filename hash + chunk index so re-ingesting the
    same PDF produces identical IDs (enabling idempotent upserts).

    Args:
        pdf_path:    PDF file path.
        chunk_index: Zero-based position of this chunk in the file.

    Returns:
        Short hex string suitable as a ChromaDB document ID.
    """
    name_hash = hashlib.md5(pdf_path.name.encode()).hexdigest()[:12]
    return f"{name_hash}_{chunk_index:04d}"


def ingest_pdf(pdf_path: Path, collection: chromadb.Collection) -> int:
    """
    Extract, chunk, and upsert a single PDF into ChromaDB.

    Existing chunks for the same PDF are replaced (upsert semantics),
    so the function is safe to call multiple times on the same file.

    Args:
        pdf_path:   Path to the MMWR PDF.
        collection: Target ChromaDB collection.

    Returns:
        Number of chunks upserted.
    """
    text = extract_text(pdf_path)
    if not text:
        logger.warning("No text extracted from %s — skipping", pdf_path.name)
        return 0

    chunks = chunk_text(text)
    if not chunks:
        logger.warning("No usable chunks from %s — skipping", pdf_path.name)
        return 0

    ids = [_doc_id(pdf_path, i) for i in range(len(chunks))]
    metadatas = [
        {
            "source": pdf_path.name,
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        for i in range(len(chunks))
    ]

    # ChromaDB upsert is idempotent — existing IDs are updated.
    collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(pdf_dir: Path = PDF_DIR) -> None:
    """
    Build (or update) the ChromaDB vector database from MMWR PDFs.

    Discovers all .pdf files in pdf_dir, extracts text, chunks and
    embeds each, and upserts into the persistent ChromaDB collection.

    Args:
        pdf_dir: Directory containing MMWR PDF files.
    """
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(
            "No PDF files found in %s. Run download_mmwr.py first.", pdf_dir
        )
        return

    logger.info("Found %d PDF files to process", len(pdf_files))
    collection = get_chroma_collection()

    total_chunks = 0
    for pdf_path in tqdm(pdf_files, desc="Building vector DB", unit="pdf"):
        n = ingest_pdf(pdf_path, collection)
        total_chunks += n
        logger.debug("  %s → %d chunks", pdf_path.name, n)

    logger.info(
        "Vector DB build complete. Collection '%s' has %d documents.",
        COLLECTION_NAME,
        collection.count(),
    )
    logger.info("Total chunks upserted this run: %d", total_chunks)


if __name__ == "__main__":
    run()
