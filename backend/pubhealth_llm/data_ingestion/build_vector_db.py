"""
MMWR PDF Parser and S3 Vectors Database Builder.

Reads MMWR PDFs from disk, extracts text (LlamaParse if API key
available, otherwise PyPDF2), splits into overlapping chunks, embeds
them via SageMaker, and stores in an S3 Vectors index.

The build is idempotent: re-ingesting the same PDF overwrites existing
vectors (same stable keys derived from filename hash + chunk index).

Usage:
    python -m pubhealth_llm.data_ingestion.build_vector_db

Environment variables required:
    VECTOR_BUCKET       — S3 Vectors bucket name
    INDEX_NAME          — S3 Vectors index name
    SAGEMAKER_ENDPOINT  — SageMaker embedding endpoint name
    AWS_REGION          — AWS region (default: us-west-1)
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from tqdm import tqdm

from pubhealth_llm.app.embeddings import embed_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PDF_DIR = Path(__file__).parents[2] / "data" / "mmwr_pdfs"
CHROMA_DIR = Path(__file__).parents[2] / "data" / "chroma_db"  # kept for legacy; not written

CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 150     # overlap between consecutive chunks
MIN_CHUNK_LENGTH = 100  # discard very short fragments

# S3 Vectors batch size limit
_S3V_BATCH_SIZE = 500

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF text extraction (unchanged)
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
# Text chunking (unchanged)
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split a long text string into overlapping chunks.

    Tries to split on paragraph boundaries (double newline) first.
    If a paragraph is longer than chunk_size it is split mid-text.

    Args:
        text:       The full document text.
        chunk_size: Target maximum characters per chunk.
        overlap:    Characters of overlap between consecutive chunks.

    Returns:
        List of text chunk strings filtered to MIN_CHUNK_LENGTH.
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
# Stable document ID (unchanged)
# ---------------------------------------------------------------------------


def _doc_id(pdf_path: Path, chunk_index: int) -> str:
    """
    Stable unique ID for a document chunk.

    ID is derived from filename hash + chunk index so re-ingesting the
    same PDF produces identical IDs (enabling idempotent upserts).

    Args:
        pdf_path:    PDF file path.
        chunk_index: Zero-based position of this chunk in the file.

    Returns:
        Short hex string suitable as a vector key.
    """
    name_hash = hashlib.md5(pdf_path.name.encode()).hexdigest()[:12]
    return f"{name_hash}_{chunk_index:04d}"


# ---------------------------------------------------------------------------
# S3 Vectors helpers
# ---------------------------------------------------------------------------


def put_vectors_batch(
    chunks: list[str],
    keys: list[str],
    metadatas: list[dict],
    embeddings: list[list[float]],
    bucket: str,
    index: str,
    region: str,
) -> None:
    """
    Write vectors to S3 Vectors in batches of _S3V_BATCH_SIZE.

    Args:
        chunks:     Raw text strings (stored in metadata).
        keys:       Stable unique keys for each vector.
        metadatas:  Per-chunk metadata dicts (must include 'source').
        embeddings: 384-dim float32 embeddings, one per chunk.
        bucket:     S3 Vectors bucket name.
        index:      S3 Vectors index name.
        region:     AWS region.
    """
    client = boto3.client("s3vectors", region_name=region)

    total = len(keys)
    for start in range(0, total, _S3V_BATCH_SIZE):
        end = min(start + _S3V_BATCH_SIZE, total)
        # S3 Vectors: filterable metadata total size limit is 2048 bytes.
        # Truncate stored text to 1500 chars to stay comfortably within
        # the limit even for chunks with multi-byte UTF-8 characters.
        _META_TEXT_LIMIT = 1500
        vectors = [
            {
                "key": keys[i],
                "data": {"float32": embeddings[i]},
                "metadata": {
                    **metadatas[i],
                    "text": chunks[i][:_META_TEXT_LIMIT],
                },
            }
            for i in range(start, end)
        ]
        client.put_vectors(
            vectorBucketName=bucket,
            indexName=index,
            vectors=vectors,
        )
        logger.debug("  put_vectors batch %d–%d OK", start, end - 1)


# ---------------------------------------------------------------------------
# Per-PDF ingestion
# ---------------------------------------------------------------------------


def ingest_pdf(
    pdf_path: Path,
    bucket: str,
    index: str,
    region: str,
) -> int:
    """
    Extract, chunk, embed, and store a single PDF into S3 Vectors.

    Args:
        pdf_path: Path to the MMWR PDF.
        bucket:   S3 Vectors bucket name.
        index:    S3 Vectors index name.
        region:   AWS region.

    Returns:
        Number of chunks written.
    """
    text = extract_text(pdf_path)
    if not text:
        logger.warning("No text extracted from %s — skipping", pdf_path.name)
        return 0

    chunks = chunk_text(text)
    if not chunks:
        logger.warning("No usable chunks from %s — skipping", pdf_path.name)
        return 0

    keys = [_doc_id(pdf_path, i) for i in range(len(chunks))]
    metadatas = [
        {
            "source": pdf_path.name,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    # Embed every chunk.
    # Truncate to 900 chars before embedding to stay within the model's
    # 512-token limit.  MMWR tables tokenize at ~2 chars/token (dense
    # numerics), so 900 chars ≈ 450 tokens — safely under the 512 cap.
    _EMBED_CHAR_LIMIT = 900
    embeddings: list[list[float]] = []
    for chunk in chunks:
        text_for_embed = chunk[:_EMBED_CHAR_LIMIT]
        vec = embed_text(text_for_embed)
        embeddings.append(vec)

    put_vectors_batch(
        chunks=chunks,
        keys=keys,
        metadatas=metadatas,
        embeddings=embeddings,
        bucket=bucket,
        index=index,
        region=region,
    )

    return len(chunks)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(pdf_dir: Path = PDF_DIR) -> None:
    """
    Ingest all MMWR PDFs in pdf_dir into S3 Vectors.

    Reads VECTOR_BUCKET, INDEX_NAME, and AWS_REGION from environment.
    Iterates every .pdf file in pdf_dir, extracts, chunks, embeds, and
    writes to S3 Vectors.

    Args:
        pdf_dir: Directory containing MMWR PDF files.
    """
    bucket = os.environ.get("VECTOR_BUCKET", "")
    index = os.environ.get("INDEX_NAME", "")
    region = os.environ.get("AWS_REGION", "us-west-1")

    if not bucket:
        raise RuntimeError(
            "VECTOR_BUCKET env var not set. "
            "Export it before running build_vector_db."
        )
    if not index:
        raise RuntimeError(
            "INDEX_NAME env var not set. "
            "Export it before running build_vector_db."
        )

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(
            "No PDF files found in %s. Run download_mmwr.py first.", pdf_dir
        )
        return

    logger.info("Found %d PDF files to process", len(pdf_files))

    total_chunks = 0
    for pdf_path in tqdm(pdf_files, desc="Building S3 vector index", unit="pdf"):
        n = ingest_pdf(pdf_path, bucket=bucket, index=index, region=region)
        total_chunks += n
        logger.debug("  %s → %d chunks", pdf_path.name, n)

    print(
        f"Ingestion complete: {total_chunks} chunks across {len(pdf_files)} PDFs"
    )


if __name__ == "__main__":
    run()
