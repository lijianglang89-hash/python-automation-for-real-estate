"""
scrape_listings.py
Fetches publicly visible property listing cards from a search results page,
extracts structured fields, and exports a timestamped CSV.

Responsible-use requirements:
  - Check the target site's Terms of Service and robots.txt before running.
  - Keep REQUEST_DELAY_SECONDS >= 2. Never run more than one instance at a time.
  - Prefer an official API or licensed feed where one exists.
"""

import csv
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# CONFIGURATION — edit these values for your target site
# --------------------------------------------------------------------------
TARGET_URL = "https://example-realestate-site.com/listings?region=oakville"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path("exports")
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_DELAY_SECONDS = 2
MAX_RETRIES = 3
LISTING_CARD_CLASS = "property-card-info"   # inspect your target with F12

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("listing_scraper")


# --------------------------------------------------------------------------
# STAGE 1 — HTTP fetching
# --------------------------------------------------------------------------
def fetch_html(url: str) -> str | None:
    """Retrieve raw HTML with browser-like headers, retries, and backoff."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text

        except requests.exceptions.HTTPError as err:
            status = err.response.status_code
            # 4xx means "do not retry" — the request itself is the problem.
            if 400 <= status < 500:
                log.error("HTTP %s returned. Not retrying a client error.", status)
                return None
            log.warning("HTTP %s on attempt %d/%d.", status, attempt, MAX_RETRIES)

        except requests.exceptions.RequestException as err:
            log.warning("Network error on attempt %d/%d: %s", attempt, MAX_RETRIES, err)

        if attempt < MAX_RETRIES:
            # Exponential backoff with jitter: 2s, 4s (+/- random fraction)
            backoff = (2 ** attempt) + random.uniform(0, 1)
            log.info("Waiting %.1fs before retry...", backoff)
            time.sleep(backoff)

    log.error("All %d attempts failed for %s", MAX_RETRIES, url)
    return None


# --------------------------------------------------------------------------
# STAGE 3 — normalization helpers
# --------------------------------------------------------------------------
def parse_price(raw_text: str | None) -> int | None:
    """
    Convert a price string into an integer.
    Handles: '$549,000'  '549000'  'USD 549,000'  'Contact Agent'  None
    Returns None when no numeric value can be recovered.
    """
    if not raw_text:
        return None
    digits_only = re.sub(r"[^0-9]", "", raw_text)
    if not digits_only:
        log.debug("Non-numeric price encountered: %r", raw_text.strip())
        return None
    return int(digits_only)


def clean_text(raw_text: str | None, default: str = "N/A") -> str:
    """Collapse whitespace and fall back to a safe default."""
    if not raw_text:
        return default
    collapsed = re.sub(r"\s+", " ", raw_text).strip()
    return collapsed or default


# --------------------------------------------------------------------------
# STAGE 2 + 3 — parsing
# --------------------------------------------------------------------------
def extract_listing_cards(html: str) -> list[dict]:
    """Locate every listing card in the HTML and normalize its fields."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_=LISTING_CARD_CLASS)
    log.info("Discovered %d listing cards.", len(cards))

    records: list[dict] = []
    scrape_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for index, card in enumerate(cards, start=1):
        try:
            address_node = card.find("address", class_="property-address")
            price_node = card.find("span", class_="property-card-price")
            beds_node = card.find("li", class_="beds-spec")
            baths_node = card.find("li", class_="baths-spec")
            sqft_node = card.find("li", class_="sqft-spec")
            dom_node = card.find("li", class_="dom-spec")
            link_node = card.find("a", href=True)

            records.append({
                "Scraped_At": scrape_timestamp,
                "Address": clean_text(address_node.get_text() if address_node else None),
                "Price": parse_price(price_node.get_text() if price_node else None),
                "Beds": clean_text(beds_node.get_text() if beds_node else None),
                "Baths": clean_text(baths_node.get_text() if baths_node else None),
                "SqFt": parse_price(sqft_node.get_text() if sqft_node else None),
                "DOM": parse_price(dom_node.get_text() if dom_node else None),
                "Listing_URL": link_node["href"] if link_node else "N/A",
            })

        except Exception as card_error:
            # One malformed card must never abort the whole run.
            log.warning("Skipped card %d: %s", index, card_error)
            continue

    return records


# --------------------------------------------------------------------------
# STAGE 4 — export
# --------------------------------------------------------------------------
def export_to_csv(records: list[dict], output_dir: Path = OUTPUT_DIR) -> Path | None:
    """Write records to a timestamped CSV encoded for Excel compatibility."""
    if not records:
        log.warning("No records to export. Nothing written.")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"listings_{stamp}.csv"

    fieldnames = ["Scraped_At", "Address", "Price", "Beds", "Baths",
                  "SqFt", "DOM", "Listing_URL"]

    # utf-8-sig writes a BOM so Excel detects UTF-8 and renders accents correctly.
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    log.info("Exported %d records to %s", len(records), output_path.resolve())
    return output_path


def main() -> None:
    log.info("Starting listing scraper run.")
    html = fetch_html(TARGET_URL)

    if html is None:
        log.error("Fetch failed. Exiting with status 1 so schedulers can detect it.")
        raise SystemExit(1)

    records = extract_listing_cards(html)
    export_to_csv(records)

    # Polite delay between any follow-up request in a multi-page run.
    time.sleep(REQUEST_DELAY_SECONDS)
    log.info("Run complete.")


if __name__ == "__main__":
    main()
