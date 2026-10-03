"""
generate_listing_copy.py
Generates channel-specific marketing copy for property listings using an
LLM API, then validates output for schema correctness and fair-housing risk.

Environment variables:
    LLM_API_KEY    your API key
    LLM_BASE_URL   optional, default https://api.openai.com/v1
    LLM_MODEL      optional, default gpt-4o-mini
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
TEMPERATURE = 0.7

CHANNELS = {
    "mls_description": {
        "max_words": 180,
        "instruction": (
            "Write a factual MLS listing description. Lead with the property's "
            "strongest verifiable feature. Use concrete nouns and measurements. "
            "Do not use superlatives such as 'stunning' or 'must-see'. "
            "No emoji. Plain prose, two short paragraphs."
        ),
    },
    "instagram_caption": {
        "max_words": 90,
        "instruction": (
            "Write an Instagram caption. Open with a one-line hook of six words "
            "or fewer, then two short lines of detail, then a call to action, "
            "then exactly five relevant hashtags on the final line."
        ),
    },
    "email_blast": {
        "max_words": 140,
        "instruction": (
            "Write a short email to a buyer list. Open with a benefit to the "
            "reader, not a description of the property. Include a clear subject "
            "line on the first line prefixed with 'Subject: '. Close with a "
            "single call to action and a sign-off placeholder [AGENT NAME]."
        ),
    },
    "portal_headline": {
        "max_words": 15,
        "instruction": (
            "Write a single headline of at most 15 words for a listing portal. "
            "Lead with the property type and the single most compelling metric."
        ),
    },
}

# Terms that create fair-housing exposure in US and Canadian marketing.
# This list is a safety net, not legal advice. Always review before publishing.
FAIR_HOUSING_BLOCKLIST = [
    "family-friendly", "perfect for families", "no children", "adults only",
    "walk to church", "close to churches", "christian", "muslim", "jewish",
    "exclusive community", "private community", "integrated neighbourhood",
    "safe neighbourhood", "good schools for your kids", "ideal for couples",
    "bachelor pad", "empty nesters", "senior living", "retirees only",
    "no section 8", "english speakers", "ethnic", "racial", "handicap",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("copy_generator")


# --------------------------------------------------------------------------
# STAGE 1 — Prompt builder
# --------------------------------------------------------------------------
def build_prompt(listing: dict, channel: str, tone: str = "professional") -> str:
    """Assemble the channel-specific generation instruction."""
    channel_config = CHANNELS[channel]
    features = listing.get("Features", [])
    features_text = "; ".join(features) if features else "none supplied"

    return f"""Generate marketing copy for the property below.

PROPERTY FACTS (use only these; do not invent any detail):
- Address area: {listing.get('Neighbourhood', 'N/A')}
- Property type: {listing.get('Property_Type', 'N/A')}
- Bedrooms: {listing.get('Beds', 'N/A')}
- Bathrooms: {listing.get('Baths', 'N/A')}
- Interior area: {listing.get('SqFt', 'N/A')} sq ft
- Lot size: {listing.get('Lot', 'N/A')}
- Year built: {listing.get('Year_Built', 'N/A')}
- Asking price: {listing.get('Price', 'N/A')}
- Verifiable features: {features_text}

TONE: {tone}

CHANNEL INSTRUCTION:
{channel_config['instruction']}

HARD CONSTRAINTS:
- Maximum {channel_config['max_words']} words.
- Never mention or imply race, colour, religion, national origin, familial
  status, disability, or sex. Do not describe neighbourhood demographics.
- Never state or imply that a school, place of worship, or facility is
  affiliated with any protected group.
- Do not invent features, measurements, or amenities that are not listed above.

Return ONLY valid JSON in this exact shape:
{{"copy": "<the marketing text>", "word_count": <integer>}}
"""


# --------------------------------------------------------------------------
# STAGE 2 — LLM call
# --------------------------------------------------------------------------
def call_llm(prompt: str) -> str | None:
    """Send the prompt and return the raw message content, or None on failure."""
    if not LLM_API_KEY:
        log.error("LLM_API_KEY is not set. Export it before running.")
        return None

    endpoint = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a licensed real estate marketing copywriter. "
                    "You write accurate, compliant, channel-appropriate copy and "
                    "you always return valid JSON. You never fabricate property "
                    "details and you never reference protected characteristics."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                endpoint, headers=headers, json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 429:
                wait = 2 ** attempt
                log.warning("Rate limited. Waiting %ds before retry %d/%d.",
                            wait, attempt, MAX_RETRIES)
                time.sleep(wait)
                continue

            if response.status_code >= 500:
                wait = 2 ** attempt
                log.warning("Server error %s. Retrying in %ds.",
                            response.status_code, wait)
                time.sleep(wait)
                continue

            if response.status_code >= 400:
                # 400/401/403 will not improve with retries.
                log.error("API rejected the request (HTTP %s): %s",
                          response.status_code, response.text[:300])
                return None

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            log.warning("Request timed out (attempt %d/%d).", attempt, MAX_RETRIES)
        except (requests.exceptions.RequestException, KeyError, IndexError) as err:
            log.warning("Call failed (attempt %d/%d): %s", attempt, MAX_RETRIES, err)

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)

    log.error("LLM call failed after %d attempts.", MAX_RETRIES)
    return None


# --------------------------------------------------------------------------
# STAGE 3 — Validation
# --------------------------------------------------------------------------
def parse_and_validate(raw_content: str, channel: str) -> dict:
    """Parse JSON, enforce schema and length limits. Returns a result dict."""
    result = {"channel": channel, "status": "unknown", "copy": "", "issues": []}

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        # Models occasionally wrap JSON in a markdown fence despite instructions.
        match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if not match:
            result["status"] = "rejected"
            result["issues"].append("Response was not parseable JSON.")
            return result
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            result["status"] = "rejected"
            result["issues"].append("Response contained malformed JSON.")
            return result

    copy_text = str(parsed.get("copy", "")).strip()
    if not copy_text:
        result["status"] = "rejected"
        result["issues"].append("Field 'copy' is missing or empty.")
        return result

    result["copy"] = copy_text
    actual_words = len(copy_text.split())
    limit = CHANNELS[channel]["max_words"]
    if actual_words > limit:
        result["issues"].append(
            f"Length {actual_words} words exceeds the {limit}-word limit."
        )

    result["status"] = "approved" if not result["issues"] else "needs_review"
    return result


def screen_fair_housing(copy_text: str) -> list[str]:
    """Return any blocklisted phrases found in the copy."""
    lowered = copy_text.lower()
    return [term for term in FAIR_HOUSING_BLOCKLIST if term in lowered]


def generate_channel_copy(listing: dict, channel: str, tone: str = "professional") -> dict:
    """Full pipeline for one listing and one channel."""
    prompt = build_prompt(listing, channel, tone)
    raw = call_llm(prompt)

    if raw is None:
        return {"channel": channel, "status": "failed", "copy": "",
                "issues": ["LLM call failed after all retries."]}

    result = parse_and_validate(raw, channel)

    if result["copy"]:
        violations = screen_fair_housing(result["copy"])
        if violations:
            result["status"] = "quarantined"
            result["issues"].append(
                "Fair-housing review required. Matched: " + ", ".join(violations)
            )

    return result


def generate_all_channels(listing: dict, tone: str = "professional") -> dict:
    """Run every channel for one listing and return a structured bundle."""
    bundle = {
        "Generated_At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Listing": listing.get("Address", "Unnamed listing"),
        "Channels": {},
    }
    for channel in CHANNELS:
        log.info("Generating %s ...", channel)
        bundle["Channels"][channel] = generate_channel_copy(listing, channel, tone)
    return bundle


def save_results(bundles: list[dict], output_dir: Path = Path("marketing")) -> Path:
    """Write approved and quarantined copy to separate files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    approved, quarantined = [], []
    for bundle in bundles:
        for channel, result in bundle["Channels"].items():
            record = {
                "Listing": bundle["Listing"],
                "Channel": channel,
                "Status": result["status"],
                "Copy": result["copy"],
                "Issues": result["issues"],
            }
            if result["status"] == "quarantined":
                quarantined.append(record)
            elif result["status"] == "approved":
                approved.append(record)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    approved_path = output_dir / f"approved_copy_{stamp}.json"
    with approved_path.open("w", encoding="utf-8") as handle:
        json.dump(approved, handle, indent=2, ensure_ascii=False)

    if quarantined:
        quarantine_path = output_dir / f"QUARANTINE_review_{stamp}.json"
        with quarantine_path.open("w", encoding="utf-8") as handle:
            json.dump(quarantined, handle, indent=2, ensure_ascii=False)
        log.warning("%d item(s) quarantined for human review: %s",
                    len(quarantined), quarantine_path)

    log.info("%d approved item(s) written to %s", len(approved), approved_path)
    return approved_path


# --------------------------------------------------------------------------
# Demo run
# --------------------------------------------------------------------------
SAMPLE_LISTING = {
    "Address": "730 Evergreen Terrace, Springfield",
    "Neighbourhood": "Evergreen Terrace",
    "Property_Type": "Detached two-storey",
    "Beds": 4, "Baths": 2.5, "SqFt": 1950,
    "Lot": "0.18 acres", "Year_Built": 2006, "Price": 579000,
    "Features": [
        "Renovated kitchen (2023)",
        "Double attached garage",
        "Forced-air gas furnace replaced 2022",
        "South-facing rear yard",
        "Finished basement with separate entrance",
    ],
}

if __name__ == "__main__":
    if not LLM_API_KEY:
        log.error("Set LLM_API_KEY before running. Example (bash):")
        log.error('    export LLM_API_KEY="sk-..."')
        raise SystemExit(1)

    bundles = [generate_all_channels(SAMPLE_LISTING, tone="warm and factual")]
    save_results(bundles)
