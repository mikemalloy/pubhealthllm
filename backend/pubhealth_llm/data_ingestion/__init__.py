"""
Data ingestion pipeline for pubHealthLLM.

Modules:
    download_cdc_places  — downloads CDC PLACES CSV and loads into SQLite
    download_mmwr        — fetches recent MMWR PDFs from CDC website
    build_vector_db      — parses PDFs and ingests into ChromaDB
    run_ingestion        — orchestrates the full pipeline end-to-end
"""
