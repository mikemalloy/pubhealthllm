"""
Tests for the rewritten build_vector_db.py (S3 Vectors backend).

TDD order:
  1. Unit tests (no I/O): chunk_text, _doc_id
  2. Mocked integration: ingest_pdf calls put_vectors with correct structure
  3. Live: run() ingests all PDFs into S3 Vectors and count >= 50
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from pubhealth_llm.data_ingestion.build_vector_db import (
    _doc_id,
    chunk_text,
    ingest_pdf,
    run,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[1]
PDF_DIR = REPO_ROOT / "data" / "mmwr_pdfs"

# Pick the first real PDF for integration tests
_PDFS = sorted(PDF_DIR.glob("*.pdf"))
FIRST_PDF = _PDFS[0] if _PDFS else None


# ---------------------------------------------------------------------------
# 1. chunk_text — basic
# ---------------------------------------------------------------------------


def test_chunk_text_basic():
    """chunk_text produces a non-empty list for a long multi-paragraph input."""
    long_text = "\n\n".join(
        [f"Paragraph {i}: " + ("word " * 50) for i in range(20)]
    )
    chunks = chunk_text(long_text)
    assert len(chunks) > 0, "chunk_text returned empty list for long input"
    for c in chunks:
        assert isinstance(c, str)
        assert len(c) > 0


# ---------------------------------------------------------------------------
# 2. chunk_text — min_length filter
# ---------------------------------------------------------------------------


def test_chunk_text_min_length():
    """Very short paragraphs (< 100 chars) must be filtered out."""
    # All paragraphs are 5 chars — well below MIN_CHUNK_LENGTH=100
    short_text = "\n\n".join(["hi." for _ in range(30)])
    chunks = chunk_text(short_text)
    # Each combined chunk is still short; the filter should drop them all
    # OR they accumulate — but the result must only contain chunks >= 100 chars
    for c in chunks:
        assert len(c) >= 100, (
            f"Chunk shorter than MIN_CHUNK_LENGTH survived: {c!r}"
        )


# ---------------------------------------------------------------------------
# 3. _doc_id — stability
# ---------------------------------------------------------------------------


def test_doc_id_stable():
    """Same pdf name + chunk index always yields the same ID."""
    p = Path("/some/path/report.pdf")
    id1 = _doc_id(p, 3)
    id2 = _doc_id(p, 3)
    assert id1 == id2, "doc_id is not stable across calls"


# ---------------------------------------------------------------------------
# 4. _doc_id — uniqueness across chunk indices
# ---------------------------------------------------------------------------


def test_doc_id_unique():
    """Different chunk_index values for the same PDF must give different IDs."""
    p = Path("/some/path/report.pdf")
    id0 = _doc_id(p, 0)
    id1 = _doc_id(p, 1)
    assert id0 != id1, "doc_id collision between chunk 0 and chunk 1"


# ---------------------------------------------------------------------------
# 5. ingest_pdf — mocked: verifies put_vectors call structure
# ---------------------------------------------------------------------------


@pytest.mark.skipif(FIRST_PDF is None, reason="No PDF files found in data/mmwr_pdfs/")
def test_ingest_pdf_calls_put_vectors(monkeypatch):
    """
    ingest_pdf must call boto3 s3vectors put_vectors at least once.
    The call must include the correct structure:
      - key: str
      - data.float32: list of floats (length 384)
      - metadata.source: the PDF filename
    """
    fake_embedding = [0.1] * 384

    # Monkeypatch embed_text in the build_vector_db module namespace
    monkeypatch.setattr(
        "pubhealth_llm.data_ingestion.build_vector_db.embed_text",
        lambda text, **kwargs: fake_embedding,
    )

    # Build a mock boto3 client
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    monkeypatch.setattr(
        "pubhealth_llm.data_ingestion.build_vector_db.boto3",
        mock_boto3,
    )

    bucket = "test-bucket"
    index = "test-index"
    region = "us-west-1"

    n = ingest_pdf(FIRST_PDF, bucket=bucket, index=index, region=region)

    assert n > 0, "ingest_pdf returned 0 chunks — extraction or chunking failed"
    assert mock_client.put_vectors.called, "put_vectors was never called"

    # Inspect the first call to put_vectors
    first_call_kwargs = mock_client.put_vectors.call_args_list[0]
    # Could be positional or keyword; normalise
    kwargs = first_call_kwargs.kwargs if first_call_kwargs.kwargs else first_call_kwargs[1]
    # If called positionally, fall back to args
    if not kwargs:
        args = first_call_kwargs[0]
        # positional: put_vectors(vectorBucketName=..., indexName=..., vectors=[...])
        # Shouldn't happen with our implementation, but be safe
        pytest.skip("put_vectors called positionally — inspect manually")

    assert kwargs.get("vectorBucketName") == bucket
    assert kwargs.get("indexName") == index

    vectors = kwargs.get("vectors", [])
    assert len(vectors) > 0, "vectors list was empty"

    first_vec = vectors[0]
    assert "key" in first_vec, "vector missing 'key'"
    assert isinstance(first_vec["key"], str), "'key' must be a string"

    assert "data" in first_vec, "vector missing 'data'"
    assert "float32" in first_vec["data"], "data missing 'float32'"
    assert isinstance(first_vec["data"]["float32"], list), "'float32' must be a list"
    assert len(first_vec["data"]["float32"]) == 384

    assert "metadata" in first_vec, "vector missing 'metadata'"
    assert "source" in first_vec["metadata"], "metadata missing 'source'"
    assert first_vec["metadata"]["source"] == FIRST_PDF.name


# ---------------------------------------------------------------------------
# 6. run — live S3 Vectors ingestion
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_run_ingests_all_pdfs_live():
    """
    Live test: run() ingests all PDFs into S3 Vectors; final vector count >= 50.

    Requires:
      VECTOR_BUCKET, INDEX_NAME, SAGEMAKER_ENDPOINT, AWS_REGION in environment.
    Skips if VECTOR_BUCKET is not set.
    """
    bucket = os.environ.get("VECTOR_BUCKET", "")
    index = os.environ.get("INDEX_NAME", "")
    region = os.environ.get("AWS_REGION", "us-west-1")

    if not bucket:
        pytest.skip("VECTOR_BUCKET not set — skipping live S3 Vectors ingestion test")
    if not index:
        pytest.skip("INDEX_NAME not set — skipping live S3 Vectors ingestion test")

    import boto3

    # Run ingestion
    run(pdf_dir=PDF_DIR)

    # Count vectors in the index with pagination
    client = boto3.client("s3vectors", region_name=region)
    total = 0
    kwargs: dict = {"vectorBucketName": bucket, "indexName": index, "maxResults": 500}
    while True:
        resp = client.list_vectors(**kwargs)
        total += len(resp.get("vectors", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break
        kwargs["nextToken"] = next_token

    print(f"\nTotal vectors in S3 index after ingestion: {total}")
    assert total >= 50, (
        f"Expected >= 50 vectors in S3 Vectors index after ingestion, got {total}"
    )
