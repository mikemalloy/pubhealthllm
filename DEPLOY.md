# Deploying pubHealthLLM to HuggingFace Spaces

## Prerequisites

- A HuggingFace account (free): https://huggingface.co/join
- An Anthropic API key: https://console.anthropic.com
- Git installed locally
- The data ingestion pipeline has been run locally (see README.md)

---

## Why push data files to the repo

HuggingFace Spaces runs your `app.py` directly — there is no build step to
run the ingestion pipeline. The pre-built data files must be committed to the
repo so the Space can serve them immediately on startup.

The `.gitignore` has been configured to include:
- `data/healthgpt.db` — SQLite database (CDC PLACES + mortality, ~25 MB)
- `data/chroma_db/` — ChromaDB vector store (MMWR embeddings, ~150 MB)
- `data/mmwr_pdfs/` — source PDFs (optional; Space does not need them at runtime)

Raw CSV caches (`data/cdc_places_raw.csv`, `data/cdc_mortality_raw.csv`) are
excluded — they are large and not needed at runtime.

---

## Step-by-step deployment

### 1. Run data ingestion locally (if not done already)

```bash
source .venv/bin/activate
python -m pubhealth_llm.data_ingestion.run_ingestion
```

Verify the output files exist:
```bash
ls -lh data/healthgpt.db data/chroma_db/ data/mmwr_pdfs/
```

### 2. Create a new HuggingFace Space

1. Go to https://huggingface.co/new-space
2. Set the following:
   - **Space name:** `pubHealthLLM` (or your preferred name)
   - **License:** MIT
   - **SDK:** Gradio
   - **SDK version:** 6.13.0
   - **Hardware:** CPU Basic (free tier is sufficient)
3. Click **Create Space**

### 3. Clone the Space repo

HuggingFace Spaces are backed by a git repo. Clone it:

```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/pubHealthLLM
cd pubHealthLLM
```

Replace `YOUR_USERNAME` with your HuggingFace username.

### 4. Copy your project files into the Space repo

```bash
# From the Space repo directory:
cp -r /path/to/pubHealthLLM_v1/* .
cp /path/to/pubHealthLLM_v1/.gitignore .
cp /path/to/pubHealthLLM_v1/.env.example .
```

Or, if your project is already a git repo, add the HF Space as a remote:

```bash
cd /path/to/pubHealthLLM_v1
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/pubHealthLLM
```

### 5. Set the ANTHROPIC_API_KEY secret

**Do not commit your API key to the repo.**

In your Space settings:
1. Go to your Space on HuggingFace
2. Click **Settings** tab
3. Scroll to **Variables and secrets**
4. Click **New secret**
5. Name: `ANTHROPIC_API_KEY`
6. Value: your Anthropic API key (starts with `sk-ant-`)
7. Click **Save**

The Space will expose this as an environment variable at runtime — the same
way a local `.env` file works.

### 6. Push to HuggingFace

```bash
git add .
git commit -m "Initial deployment"
git push hf main
```

If your data files are large, git-lfs is recommended for files over 10 MB:

```bash
# Install git-lfs if not already installed
brew install git-lfs   # macOS
git lfs install

# Track large file types
git lfs track "*.db"
git lfs track "*.pdf"
git lfs track "*.bin"
git lfs track "*.parquet"
git add .gitattributes
git commit -m "Add git-lfs tracking"
git push hf main
```

### 7. Verify the Space builds

1. Go to your Space URL: `https://huggingface.co/spaces/YOUR_USERNAME/pubHealthLLM`
2. Watch the **Build** tab — it should install requirements and start the app
3. Once the status shows **Running**, click the app URL to test it

Common build issues:
- **Build fails on chromadb:** The free CPU tier has enough RAM; if it OOMs, try the T4 Small GPU tier
- **"ANTHROPIC_API_KEY not set" error:** The secret was not saved correctly — check Settings → Secrets
- **App starts but returns errors:** Check that `data/healthgpt.db` and `data/chroma_db/` were committed and pushed

---

## Updating the Space

To push code changes (no data change):
```bash
git add pubhealth_llm/ app.py requirements.txt
git commit -m "Update: describe your change"
git push hf main
```

To push data updates (after re-running ingestion):
```bash
git add data/healthgpt.db data/chroma_db/
git commit -m "Refresh data: re-ran ingestion pipeline"
git push hf main
```

---

## Expected resource usage

| Resource | Amount |
|----------|--------|
| Disk     | ~500 MB (db + vectors + PDFs) |
| RAM      | ~1.5 GB at peak (ChromaDB + sentence-transformers model) |
| CPU      | Low (inference is handled by Anthropic API) |
| Network  | One API call per user question to Anthropic |

The free CPU Basic tier (16 GB RAM, 2 vCPU) is sufficient for demo use.

---

## Environment variables reference

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | Anthropic API key for Claude inference |
| `HEALTHGPT_MODEL` | No | Override Claude model (default: `claude-sonnet-4-5`) |
| `CHROMA_DB_PATH` | No | Override ChromaDB path (default: `data/chroma_db`) |
| `SQLITE_DB_PATH` | No | Override SQLite path (default: `data/healthgpt.db`) |
