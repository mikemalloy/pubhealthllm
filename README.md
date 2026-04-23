---
title: pubHealthLLM
emoji: 🏥
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "6.13.0"
app_file: app.py
pinned: false
license: mit
short_description: Evidence-based public health Q&A from CDC surveillance data
---

# pubHealthLLM — Public Health Decision Intelligence

An AI assistant for public health professionals that answers questions using
real CDC data — no hallucinated statistics.

**Data sources:**
- **CDC PLACES 2023** — county-level prevalence of 36 health measures for ~3,000 US counties
- **CDC MMWR 2022–2024** — weekly outbreak surveillance reports (semantic search)
- **CDC NCHS Mortality 1999–2017** — state-level age-adjusted death rates by cause

**Powered by:** Claude Sonnet (Anthropic) via PydanticAI · ChromaDB · SQLite · Gradio

---

## Example questions to try

> "What is the obesity rate in Travis County, Texas? How does it compare to the state average?"

> "Compare diabetes prevalence across Harris County, Dallas County, and Bexar County in Texas."

> "What are the leading causes of death in Louisiana and how do cardiovascular mortality rates compare to neighboring states?"

---

## How it works

```
Your question
     │
     ▼
PydanticAI Agent (Claude Sonnet)
     │
     ├── search_mmwr_reports()        → ChromaDB  (MMWR PDF chunks)
     ├── get_health_statistics()      → SQLite    (CDC PLACES county data)
     ├── compare_locations()          → SQLite    (CDC PLACES multi-county)
     ├── get_worst_counties_by_measure() → SQLite (CDC PLACES ranking)
     ├── rank_counties_composite()    → SQLite    (z-score composite ranking)
     ├── get_mortality_data()         → SQLite    (CDC NCHS mortality)
     └── compare_mortality()          → SQLite    (multi-state mortality)
     │
     ▼
Structured PublicHealthResponse (Pydantic)
     │
     ▼
Gradio ChatInterface
```

The agent is instructed to never fabricate statistics — every figure in a response
must come from a tool call against real CDC data.

---

## Disclaimer

This tool provides decision support only. All outputs require validation by qualified
public health professionals before informing operational decisions. Data reflects
historical surveillance and may not capture current conditions.

---

## Local setup

```bash
git clone <repo-url> pubHealthLLM_v1
cd pubHealthLLM_v1
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Build data files (5–20 minutes, ~500 MB)
python -m pubhealth_llm.data_ingestion.run_ingestion

# Launch
python main.py
```

## Project structure

```
pubHealthLLM_v1/
├── app.py                           ← HuggingFace Spaces entry point
├── main.py                          ← local dev entry point
├── pubhealth_llm/
│   ├── data_ingestion/
│   │   ├── download_cdc_places.py   # CDC PLACES CSV → SQLite
│   │   ├── download_mmwr.py         # MMWR PDFs → disk
│   │   ├── build_vector_db.py       # PDFs → ChromaDB
│   │   ├── download_mortality.py    # CDC NCHS mortality → SQLite
│   │   └── run_ingestion.py         # orchestrates all steps
│   └── app/
│       ├── schemas.py               # Pydantic output models
│       ├── tools.py                 # 7 agent tool implementations
│       ├── agent.py                 # PydanticAI agent + system prompt
│       └── gradio_app.py            # Gradio ChatInterface
├── data/
│   ├── healthgpt.db                 # SQLite (CDC PLACES + mortality)
│   ├── mmwr_pdfs/                   # MMWR PDFs
│   └── chroma_db/                   # ChromaDB vector store
├── tests/                           # pytest test suite (95 tests)
├── .env.example                     # required secrets template
├── requirements.txt
└── DEPLOY.md                        # HuggingFace deployment guide
```
