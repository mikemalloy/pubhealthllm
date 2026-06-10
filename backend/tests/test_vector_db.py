"""
Tests for the S3 Vectors MMWR vector store.

Verifies the index is populated and returns semantically relevant results.
All tests guard on the `s3v_index` fixture (skips when VECTOR_BUCKET unset).
"""
import os
import pytest

VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET", "")
INDEX_NAME = os.environ.get("INDEX_NAME", "mmwr-reports")


def test_s3v_index_accessible(s3v_index):
    """S3 Vectors index must be reachable — list_vectors should not raise."""
    resp = s3v_index.list_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        maxResults=1,
    )
    assert "vectors" in resp


def test_s3v_index_has_vectors(s3v_index):
    """Index must contain at least 10 vectors (60 were ingested from 9 PDFs)."""
    resp = s3v_index.list_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        maxResults=100,
    )
    vectors = resp.get("vectors", [])
    assert len(vectors) >= 10, (
        f"Expected ≥10 vectors, got {len(vectors)}. "
        "Run: python -m pubhealth_llm.data_ingestion.build_vector_db"
    )


def test_s3v_semantic_search_returns_results(s3v_index):
    """Semantic query must return at least one result."""
    from pubhealth_llm.app.embeddings import embed_text

    query_vec = embed_text("infectious disease outbreak surveillance")
    resp = s3v_index.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        queryVector={"float32": query_vec},
        topK=3,
        returnMetadata=True,
    )
    results = resp.get("vectors", [])
    assert len(results) > 0, "query_vectors returned no results"


def test_s3v_result_metadata_has_source(s3v_index):
    """Each returned vector must carry a 'source' metadata field."""
    from pubhealth_llm.app.embeddings import embed_text

    query_vec = embed_text("public health")
    resp = s3v_index.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        queryVector={"float32": query_vec},
        topK=1,
        returnMetadata=True,
    )
    results = resp.get("vectors", [])
    assert results, "No results returned"
    metadata = results[0].get("metadata", {})
    assert "source" in metadata, f"'source' missing from metadata. Got: {metadata}"


def test_s3v_result_metadata_has_text(s3v_index):
    """Each returned vector must carry a 'text' metadata field."""
    from pubhealth_llm.app.embeddings import embed_text

    query_vec = embed_text("public health")
    resp = s3v_index.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        queryVector={"float32": query_vec},
        topK=1,
        returnMetadata=True,
    )
    results = resp.get("vectors", [])
    assert results, "No results returned"
    metadata = results[0].get("metadata", {})
    assert "text" in metadata, f"'text' missing from metadata. Got: {metadata}"
