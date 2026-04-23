"""
CDC MMWR Weekly Report Downloader.

Scrapes the CDC MMWR weekly reports index page, identifies recent
PDF links (last N years), and downloads them to the local mmwr_pdfs/
directory.  Already-downloaded files are skipped, making this
idempotent.

CDC MMWR homepage: https://www.cdc.gov/mmwr/index.html

Usage:
    python -m data_ingestion.download_mmwr
"""

import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MMWR_BASE_URL = "https://www.cdc.gov"
MMWR_WEEKLY_INDEX = "https://www.cdc.gov/mmwr/mmwr_wk/wk_pvol.html"

# Fallback: direct volume/issue index URLs for recent years.
# Keyed by year → index page for that year's weekly reports.
MMWR_YEAR_INDEXES: dict[int, str] = {
    2024: "https://www.cdc.gov/mmwr/mmwr_wk/wk_pvol.html",
    2023: "https://www.cdc.gov/mmwr/volumes/72/wr/index.htm",
    2022: "https://www.cdc.gov/mmwr/volumes/71/wr/index.htm",
}

PDF_DIR = Path(__file__).parents[2] / "data" / "mmwr_pdfs"
YEARS_TO_FETCH = 3          # how many calendar years of reports to pull
MAX_PDFS_PER_YEAR = 12      # cap per year to keep demo ingestion manageable
REQUEST_DELAY = 0.5         # seconds between HTTP requests (be polite)
CHUNK_SIZE = 8192           # bytes per download chunk
REQUEST_TIMEOUT = 30        # seconds

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "pubHealthLLM-research-tool/1.0"})


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------


def _get(url: str) -> requests.Response:
    """
    GET a URL with a short polite delay and timeout.

    Args:
        url: URL to fetch.

    Returns:
        Response object (raises on HTTP error).
    """
    time.sleep(REQUEST_DELAY)
    resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def _find_pdf_links_on_page(page_url: str) -> list[str]:
    """
    Parse an HTML page and return all absolute PDF href values.

    Args:
        page_url: The URL of the page to scrape.

    Returns:
        List of absolute URLs ending in .pdf (may be empty).
    """
    try:
        resp = _get(page_url)
    except Exception as exc:
        logger.warning("Could not fetch %s: %s", page_url, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    pdfs: list[str] = []
    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        if href.lower().endswith(".pdf"):
            absolute = urljoin(MMWR_BASE_URL, href)
            pdfs.append(absolute)
    return pdfs


def collect_mmwr_pdf_urls(years_back: int = YEARS_TO_FETCH) -> list[str]:
    """
    Collect MMWR weekly report PDF URLs from CDC's index pages.

    Strategy:
      1. Try the main MMWR weekly volume index.
      2. Fall back to known per-year index URLs for resilience.
      3. Filter to PDF links that look like weekly reports.

    Args:
        years_back: Number of past years to include (relative to 2024).

    Returns:
        Deduplicated list of PDF URLs, most recent first.
    """
    collected: set[str] = set()

    # Primary: scrape the rolling index page
    logger.info("Scraping primary MMWR weekly index …")
    try:
        resp = _get(MMWR_WEEKLY_INDEX)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find links to individual issue index pages
        issue_pattern = re.compile(r"/mmwr/volumes/\d+/wr/mm\d+", re.IGNORECASE)
        issue_pages: list[str] = []
        for tag in soup.find_all("a", href=True):
            if issue_pattern.search(tag["href"]):
                issue_pages.append(urljoin(MMWR_BASE_URL, tag["href"]))

        logger.info("Found %d issue index pages from primary index", len(issue_pages))

        # Visit each issue page and collect PDFs (limit to keep demo fast)
        for page_url in issue_pages[:MAX_PDFS_PER_YEAR * years_back]:
            for pdf in _find_pdf_links_on_page(page_url):
                collected.add(pdf)

    except Exception as exc:
        logger.warning("Primary index scrape failed (%s); using fallback URLs", exc)

    # Fallback: use known year index URLs
    if len(collected) < 10:
        logger.info("Falling back to per-year index pages …")
        current_year = 2024
        for year in range(current_year, current_year - years_back, -1):
            if year not in MMWR_YEAR_INDEXES:
                continue
            index_url = MMWR_YEAR_INDEXES[year]
            logger.info("  Scraping year %d index: %s", year, index_url)
            try:
                resp = _get(index_url)
                soup = BeautifulSoup(resp.text, "html.parser")
                # Each row in the table links to a volume/issue page
                for tag in soup.find_all("a", href=True):
                    href = tag["href"]
                    if re.search(r"mm\d{4}", href, re.IGNORECASE):
                        issue_url = urljoin(MMWR_BASE_URL, href)
                        for pdf in _find_pdf_links_on_page(issue_url):
                            collected.add(pdf)
                            if len(collected) >= MAX_PDFS_PER_YEAR * years_back:
                                break
            except Exception as exc2:
                logger.warning("  Year %d index failed: %s", year, exc2)

    # If we still have nothing, use hard-coded sample URLs as a last resort
    if not collected:
        logger.warning(
            "Could not scrape live MMWR links. Using sample report URLs for demo."
        )
        collected = _sample_mmwr_urls()

    pdf_list = sorted(collected, reverse=True)
    logger.info("Collected %d unique MMWR PDF URLs", len(pdf_list))
    return pdf_list


def _sample_mmwr_urls() -> set[str]:
    """
    Return a small set of known stable MMWR PDF URLs as a demo fallback.

    These are real CDC MMWR weekly report PDFs that existed as of 2024.
    Used only when live scraping fails entirely.

    Returns:
        Set of PDF URL strings.
    """
    return {
        # 2024
        "https://www.cdc.gov/mmwr/volumes/73/wr/pdfs/mm7301a1-H.pdf",
        "https://www.cdc.gov/mmwr/volumes/73/wr/pdfs/mm7302a1-H.pdf",
        "https://www.cdc.gov/mmwr/volumes/73/wr/pdfs/mm7303a1-H.pdf",
        # 2023
        "https://www.cdc.gov/mmwr/volumes/72/wr/pdfs/mm7201a1-H.pdf",
        "https://www.cdc.gov/mmwr/volumes/72/wr/pdfs/mm7210a1-H.pdf",
        "https://www.cdc.gov/mmwr/volumes/72/wr/pdfs/mm7220a1-H.pdf",
        # 2022
        "https://www.cdc.gov/mmwr/volumes/71/wr/pdfs/mm7101a1-H.pdf",
        "https://www.cdc.gov/mmwr/volumes/71/wr/pdfs/mm7110a1-H.pdf",
        "https://www.cdc.gov/mmwr/volumes/71/wr/pdfs/mm7120a1-H.pdf",
    }


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def _filename_from_url(url: str) -> str:
    """Derive a safe local filename from a PDF URL."""
    return url.split("/")[-1].split("?")[0] or "mmwr_report.pdf"


def download_pdfs(pdf_urls: list[str], dest_dir: Path) -> list[Path]:
    """
    Download a list of PDF URLs, skipping files that already exist.

    Args:
        pdf_urls: Absolute URLs to download.
        dest_dir: Directory to save PDFs into (created if needed).

    Returns:
        List of local paths for all PDFs (downloaded + already present).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    skipped = 0

    for url in tqdm(pdf_urls, desc="Downloading MMWR PDFs", unit="pdf"):
        filename = _filename_from_url(url)
        dest_path = dest_dir / filename

        if dest_path.exists():
            skipped += 1
            downloaded.append(dest_path)
            continue

        try:
            resp = _SESSION.get(url, stream=True, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    fh.write(chunk)
            downloaded.append(dest_path)
            time.sleep(REQUEST_DELAY)
        except Exception as exc:
            logger.warning("Failed to download %s: %s", url, exc)

    logger.info(
        "PDFs ready: %d downloaded, %d already present, %d skipped due to error",
        len(downloaded) - skipped,
        skipped,
        len(pdf_urls) - len(downloaded),
    )
    return downloaded


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(years_back: int = YEARS_TO_FETCH) -> list[Path]:
    """
    Collect and download recent MMWR PDFs.

    Args:
        years_back: Number of calendar years of reports to fetch.

    Returns:
        List of local PDF file paths ready for text extraction.
    """
    urls = collect_mmwr_pdf_urls(years_back=years_back)
    paths = download_pdfs(urls, PDF_DIR)
    logger.info("MMWR download phase complete. %d PDFs on disk.", len(paths))
    return paths


if __name__ == "__main__":
    run()
