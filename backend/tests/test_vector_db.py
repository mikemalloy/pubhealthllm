"""
Tests for the ChromaDB MMWR vector database.

Verifies the collection exists, contains embedded documents, and
returns results for representative semantic queries.
"""

import pytest


def test_chroma_dir_populated(chroma_dir):
    """ChromaDB directory must contain files (not just be created empty)."""
    files = list(chroma_dir.rglob("*"))
    assert files, f"ChromaDB directory {chroma_dir} exists but is empty"


def test_chroma_client_connects(chroma_dir):
    """PersistentClient must connect to the local ChromaDB without error."""
    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_dir))
    assert client is not None


def test_mmwr_collection_exists(chroma_dir):
    """The mmwr_reports collection must exist in ChromaDB."""
    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collections = [c.name for c in client.list_collections()]
    assert "mmwr_reports" in collections, (
        f"mmwr_reports collection not found. Available: {collections}"
    )


def test_mmwr_collection_has_documents(chroma_dir):
    """mmwr_reports collection must contain at least a few embedded chunks."""
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(chroma_dir))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    col = client.get_collection(name="mmwr_reports", embedding_function=ef)
    count = col.count()
    assert count > 0, (
        "mmwr_reports collection is empty. Run: "
        "python -m pubhealth_llm.data_ingestion.run_ingestion"
    )


def test_mmwr_semantic_search_returns_results(chroma_dir):
    """
    A query about disease surveillance must return at least one result.

    This exercises the full embedding → similarity search path that
    the search_mmwr_reports tool uses at runtime.
    """
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(chroma_dir))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    col = client.get_collection(name="mmwr_reports", embedding_function=ef)

    results = col.query(
        query_texts=["infectious disease outbreak surveillance"],
        n_results=min(3, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    assert results["documents"], "Query returned no documents"
    assert results["documents"][0], "First result set is empty"
    assert len(results["documents"][0]) > 0, "No chunks returned from semantic search"


def test_mmwr_result_metadata_has_source(chroma_dir):
    """
    Each returned chunk must carry a 'source' metadata field.

    The Gradio UI displays source filenames in the response, so missing
    metadata would cause KeyError at render time.
    """
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(chroma_dir))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    col = client.get_collection(name="mmwr_reports", embedding_function=ef)

    results = col.query(
        query_texts=["public health"],
        n_results=min(1, col.count()),
        include=["metadatas"],
    )

    metadatas = results["metadatas"][0]
    assert metadatas, "No metadata returned"
    assert "source" in metadatas[0], (
        f"'source' key missing from chunk metadata. Got: {metadatas[0]}"
    )
