"""
monitor_price_drops.py
Compares a current market feed against a persisted baseline and dispatches
alerts when a property's asking price falls by more than a set threshold.

Credentials are read from environment variables:
    ALERT_SENDER_EMAIL       e.g. you@gmail.com
    ALERT_SENDER_PASSWORD    a 16-character Google App Password (NOT your login)
    ALERT_RECIPIENT_EMAIL    where alerts should arrive
    SLACK_WEBHOOK_URL        optional; leave unset to disable webhook alerts

Run:
    python monitor_price_drops.py
"""

import html
import json
import logging
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------
STATE_FILE = Path("property_state.json")
PRICE_DROP_THRESHOLD = 0.05        # 5% reduction triggers an alert
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587                    # STARTTLS
REQUEST_TIMEOUT_SECONDS = 10

SENDER_EMAIL = os.getenv("ALERT_SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("ALERT_SENDER_PASSWORD")
RECIPIENT_EMAIL = os.getenv("ALERT_RECIPIENT_EMAIL")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("price_monitor")


# --------------------------------------------------------------------------
# STATE PERSISTENCE
# --------------------------------------------------------------------------
def load_state(path: Path = STATE_FILE) -> dict:
    """Load the previous price baseline. Missing or corrupt file => empty state."""
    if not path.exists():
        log.info("No existing state file. This run establishes the baseline.")
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as err:
        # A corrupt state file must not crash a scheduled job.
        log.warning("State file unreadable (%s). Starting from a fresh baseline.", err)
        return {}


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    """Persist the updated baseline atomically."""
    temp_path = path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
    temp_path.replace(path)   # atomic swap: never leave a half-written file


# --------------------------------------------------------------------------
# DISPATCHERS
# --------------------------------------------------------------------------
def send_email_alert(prop: dict, old_price: float, new_price: float, drop_pct: float) -> bool:
    """Send an HTML price-drop alert via SMTP with STARTTLS."""
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        log.warning("Email credentials not configured. Skipping email dispatch.")
        return False

    savings = old_price - new_price
    subject = f"[Price Drop {drop_pct:.1f}%] {prop['Address']}"

    # html.escape() prevents a scraped address containing '<' or '&' from
    # corrupting the markup or injecting tags into the email body.
    safe = {key: html.escape(str(value)) for key, value in prop.items()}

    body = f"""<html><body style="font-family: Arial, Helvetica, sans-serif; color:#333;">
  <h2 style="color:#c0392b; margin-bottom:4px;">Price Reduction Detected</h2>
  <p style="margin-top:0; color:#777; font-size:13px;">
    Detected {datetime.now().strftime('%Y-%m-%d %H:%M')}
  </p>
  <table cellpadding="6" style="border-collapse:collapse; font-size:14px;">
    <tr><td><b>Address</b></td><td>{safe.get('Address', 'N/A')}</td></tr>
    <tr><td><b>Previous Price</b></td><td>${old_price:,.0f}</td></tr>
    <tr><td><b>New Price</b></td>
        <td style="color:#27ae60; font-weight:bold;">${new_price:,.0f}</td></tr>
    <tr><td><b>Reduction</b></td>
        <td style="color:#27ae60;">${savings:,.0f} ({drop_pct:.1f}%)</td></tr>
    <tr><td><b>Specs</b></td>
        <td>{safe.get('Beds', 'N/A')} bd / {safe.get('Baths', 'N/A')} ba /
            {safe.get('SqFt', 'N/A')} SqFt</td></tr>
  </table>
  <p style="margin-top:16px;">
    <a href="{safe.get('URL', '#')}"
       style="background:#1f3864; color:#fff; padding:10px 16px;
              text-decoration:none; border-radius:4px;">View Listing</a>
  </p>
</body></html>"""

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = RECIPIENT_EMAIL
    message.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=REQUEST_TIMEOUT_SECONDS) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], message.as_string())
        log.info("Email alert sent for %s", prop["Address"])
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP authentication failed. Use an App Password, not your account password.")
    except (smtplib.SMTPException, OSError) as err:
        log.error("Email dispatch failed: %s", err)
    return False


def send_slack_webhook(prop: dict, old_price: float, new_price: float, drop_pct: float) -> bool:
    """Post a formatted alert to a Slack (or compatible) incoming webhook."""
    if not SLACK_WEBHOOK_URL:
        log.debug("No webhook URL configured. Skipping webhook dispatch.")
        return False

    payload = {
        "text": (
            f":rotating_light: *Price Drop {drop_pct:.1f}%*\n"
            f"*Address:* {prop['Address']}\n"
            f"*Price:* ~${old_price:,.0f}~ -> *${new_price:,.0f}*\n"
            f"*Link:* {prop.get('URL', 'N/A')}"
        )
    }

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code == 200:
            log.info("Webhook alert sent for %s", prop["Address"])
            return True
        log.warning("Webhook returned HTTP %s", response.status_code)
    except requests.exceptions.RequestException as err:
        log.error("Webhook dispatch failed: %s", err)
    return False


# --------------------------------------------------------------------------
# CORE LOOP
# --------------------------------------------------------------------------
def monitor_price_drops(current_feed: list[dict]) -> list[dict]:
    """Compare the feed to the baseline, alert on real drops, persist new state."""
    previous_state = load_state()
    updated_state: dict = {}
    alerts: list[dict] = []

    for prop in current_feed:
        prop_id = str(prop.get("PropID") or prop.get("Address", "")).strip()
        if not prop_id:
            log.warning("Skipping a record with neither PropID nor Address.")
            continue

        try:
            current_price = float(prop["Price"])
        except (KeyError, TypeError, ValueError):
            log.warning("Skipping %s: unusable price %r", prop_id, prop.get("Price"))
            continue

        # ---- Evaluate against the baseline ------------------------------
        baseline = previous_state.get(prop_id)
        if baseline:
            old_price = float(baseline["Price"])
            if current_price < old_price:
                drop_pct = (old_price - current_price) / old_price
                if drop_pct >= PRICE_DROP_THRESHOLD:
                    log.info(
                        "ALERT: %s fell %.2f%% (%.0f -> %.0f)",
                        prop.get("Address", prop_id), drop_pct * 100,
                        old_price, current_price,
                    )
                    send_email_alert(prop, old_price, current_price, drop_pct * 100)
                    send_slack_webhook(prop, old_price, current_price, drop_pct * 100)
                    alerts.append({
                        "Address": prop.get("Address", prop_id),
                        "Old_Price": old_price,
                        "New_Price": current_price,
                        "Drop_Pct": round(drop_pct * 100, 2),
                    })
                else:
                    log.info(
                        "%s dipped %.2f%% — below the %.0f%% threshold.",
                        prop.get("Address", prop_id), drop_pct * 100,
                        PRICE_DROP_THRESHOLD * 100,
                    )

        # ---- Record the new baseline (this is the dedup mechanism) -------
        updated_state[prop_id] = {
            "Address": prop.get("Address", "N/A"),
            "Price": current_price,
            "Last_Seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    save_state(updated_state)
    log.info("Run complete. %d properties tracked, %d alerts issued.",
             len(updated_state), len(alerts))
    return alerts


# --------------------------------------------------------------------------
# Demo run
# --------------------------------------------------------------------------
SAMPLE_FEED = [
    {
        "PropID": "PROP_1001",
        "Address": "104 Maple St, Oakville",
        "Price": 465000,          # was 500,000 in the baseline => 7.0% drop
        "Beds": 3, "Baths": 2, "SqFt": 1650,
        "URL": "https://example.com/listing/1001",
    },
    {
        "PropID": "PROP_1002",
        "Address": "208 Pine Rd, Oakville",
        "Price": 620000,          # unchanged
        "Beds": 4, "Baths": 3, "SqFt": 2200,
        "URL": "https://example.com/listing/1002",
    },
    {
        "PropID": "PROP_1003",
        "Address": "77 Birch Ave, Oakville",
        "Price": 489000,          # was 495,000 => 1.2%, below threshold
        "Beds": 3, "Baths": 2, "SqFt": 1780,
        "URL": "https://example.com/listing/1003",
    },
]

if __name__ == "__main__":
    # Seed a baseline on first run so the demo produces a visible alert.
    if not STATE_FILE.exists():
        save_state({
            "PROP_1001": {"Address": "104 Maple St", "Price": 500000},
            "PROP_1002": {"Address": "208 Pine Rd", "Price": 620000},
            "PROP_1003": {"Address": "77 Birch Ave", "Price": 495000},
        })
        log.info("Seeded a demo baseline. Re-run to observe alert behaviour.")

    log.info("Evaluating market feed against baseline...")
    monitor_price_drops(SAMPLE_FEED)
    sys.exit(0)
