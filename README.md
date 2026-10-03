# Python Automation for Real Estate

> **A Practical Guide to Scraping Market Data, Automating Property Reports, and Building Micro-Workflows**

<!-- Replace YOUR_ASIN_HERE with the real ASIN once the book is live. -->

[![Available on Amazon Kindle](https://img.shields.io/badge/Amazon_Kindle-Available_Now-orange?style=for-the-badge&logo=amazon)](https://www.amazon.com/dp/YOUR_ASIN_HERE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python)](https://www.python.org/)

<!-- KDP Select only: uncomment the badge below ONLY if the book is enrolled in
     Kindle Unlimited. Claiming KU when you are not enrolled is a misleading
     claim and can draw a complaint.
[![Kindle Unlimited](https://img.shields.io/badge/Kindle_Unlimited-Read_for_Free-green?style=for-the-badge)](https://www.amazon.com/dp/YOUR_ASIN_HERE)
-->

This is the official code repository for the book **Python Automation for Real Estate**.

It contains five of the seven runnable scripts from the book, plus the
configuration templates and sample data you need to run them. Everything here is
plain Python with a small dependency list — no framework, no cloud account, no
proprietary API.

---

## 📖 Get the book

**Python Automation for Real Estate** — available on Amazon Kindle.

👉 **https://www.amazon.com/dp/YOUR_ASIN_HERE**

The book is a plug-and-play technical cookbook: 6 chapters, 7 runnable scripts,
and a five-stage format for every chapter (goal → architecture → build → run →
production notes).

---

## 💡 What is free here vs. what is in the book

The scripts in this repository run. What the book adds is *why* they are built
this way, how to adapt them to your own market, and how to keep them running
unattended.

| Content | This repo (free) | The book |
| :--- | :---: | :---: |
| Runnable scripts | **5** (Ch. 1–5) | **7** (Ch. 1–6) |
| Requirements + install instructions | ✅ | ✅ |
| Sample data and baseline state file | ✅ | ✅ |
| Line-by-line walkthrough of each script | ❌ | ✅ |
| Architecture and data-flow diagrams | ❌ | ✅ |
| Edge cases and troubleshooting tables | ❌ | ✅ |
| Adapting selectors to a different market | ❌ | ✅ |
| CMA report design and Word template internals | ❌ | ✅ |
| Fair-housing screening rules and why they matter | ❌ | ✅ |
| **Supervised pipeline orchestrator** (Chapter 6) | ❌ | ✅ |
| **Rotating logs + failure recovery per stage** | ❌ | ✅ |
| **Heartbeat file + external health check** | ❌ | ✅ |
| Unattended scheduling on macOS / Windows | ❌ | ✅ |

In short: **everything up to "it runs once" is free. The book is about making it
run every night without you watching.**

---

## 🛠️ Repository structure

```text
.
├── code/
│   ├── verify_setup.py            # Chapter 1 — confirm your environment works
│   ├── scrape_listings.py         # Chapter 2 — fetch + parse public listing cards → CSV
│   ├── generate_cma.py            # Chapter 3 — comparable-sales data → styled .docx report
│   ├── monitor_price_drops.py     # Chapter 4 — diff against a baseline, email/Slack alerts
│   ├── generate_listing_copy.py   # Chapter 5 — channel-specific copy + fair-housing screen
│   └── property_state.json        # Sample baseline for monitor_price_drops.py
├── requirements.txt
├── LICENSE
└── README.md
```

Five standalone scripts. Run any one of them on its own — no orchestrator and no
scheduling required. Only `monitor_price_drops.py` carries state between runs,
and it keeps that in a single JSON file next to it.

> **Chapter 6 is deliberately not here.** The book's final chapter is about
> *keeping* this pipeline alive: the supervised orchestrator, rotating logs, the
> heartbeat file, and the failure-recovery logic that tells you at 6am that
> last night's run silently died. That code is in the book. Everything up to and
> including "it runs once" is in this repository, free.


---

## ⚡ Quick start

**1. Clone the repository**

```bash
git clone https://github.com/lijianglang89-hash/python-automation-for-real-estate.git
cd python-automation-for-real-estate
```

**2. Create a virtual environment**

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Verify everything is wired up**

```bash
python code/verify_setup.py
```

This does a real data operation, not just a version check — if it prints a
result table, your environment is good.

**5. Run a script**

The scripts read and write files **relative to the current directory**, so run
them from inside `code/`:

```bash
cd code

python verify_setup.py            # environment check + a live data operation
python monitor_price_drops.py     # should print one alert, see note below
python scrape_listings.py         # writes a timestamped CSV
python generate_cma.py            # writes CMA_Report_<address>.docx
```

> `property_state.json` is a **sample baseline**, shipped so
> `monitor_price_drops.py` has something to diff against on the very first run.
> With it in place the script should report:
>
> ```
> ALERT: 104 Maple St, Oakville fell 7.00% (500000 -> 465000)
> ```
>
> Delete the file and the next run re-seeds an empty baseline and reports
> nothing — which is exactly the failure mode Chapter 6 is about. Real runs
> overwrite this file, so keep your own copy out of version control.

---

## 🔑 Environment variables

Two scripts read credentials from the environment. **Never commit these.**

| Variable | Used by | Notes |
| :--- | :--- | :--- |
| `ALERT_SENDER_EMAIL` | `monitor_price_drops.py` | Your sending address |
| `ALERT_SENDER_PASSWORD` | `monitor_price_drops.py` | An **app password**, not your login password |
| `ALERT_RECIPIENT_EMAIL` | `monitor_price_drops.py` | Where alerts land |
| `SLACK_WEBHOOK_URL` | `monitor_price_drops.py` | Optional — leave unset to disable |
| `LLM_API_KEY` | `generate_listing_copy.py` | Any OpenAI-compatible endpoint |
| `LLM_BASE_URL` | `generate_listing_copy.py` | Optional, defaults to `https://api.openai.com/v1` |
| `LLM_MODEL` | `generate_listing_copy.py` | Optional, defaults to `gpt-4o-mini` |

Example:

```bash
export ALERT_SENDER_EMAIL="you@example.com"
export ALERT_SENDER_PASSWORD="your-16-char-app-password"
export ALERT_RECIPIENT_EMAIL="you@example.com"
```

---

## 📚 Table of contents (the book)

1. **Zero-to-One Python Setup for Real Estate Professionals** — code: `verify_setup.py`
2. **Automated Scraping of Public Market Listings** — code: `scrape_listings.py`
3. **Generating Comparative Market Analysis (CMA) Reports** — code: `generate_cma.py`
4. **Real-Time Price Drop & High-Value Deal Alerts** — code: `monitor_price_drops.py`
5. **AI-Powered Listing Description & Social Marketing Generator** — code: `generate_listing_copy.py`
6. **Unattended Scheduling & Production Deployment** — *code in the book only*

---

## ⚠️ Responsible use — please read

**Scraping.** `scrape_listings.py` targets *publicly visible* listing pages at a
deliberately slow rate (`REQUEST_DELAY_SECONDS >= 2`). Before you point it at
anything:

- Read the target site's **Terms of Service** and `robots.txt`.
- Never run more than one instance at a time.
- **Prefer an official API or a licensed data feed wherever one exists.** Those
  are the correct answer in almost every commercial setting.

**Fair housing.** The screen in `generate_listing_copy.py` is a **safety net,
not legal advice**. It catches a limited set of phrasing patterns. Every piece
of marketing copy must be reviewed by a human before it is published. Fair
housing law in the United States is enforced by HUD and by state agencies, and
the penalties are significant.

**Not affiliated.** This project is not affiliated with, endorsed by, or
sponsored by any listing portal, brokerage, MLS, or software vendor. No
trademarked platform names appear in the code or the book.

**No warranty.** All code is provided as-is, without warranty of any kind. Test
it against your own data before relying on it in a client-facing workflow. See
[LICENSE](LICENSE).

---

## 🤝 Contributing

Bug reports and fixes to the sample scripts are welcome — please open an
[issue](https://github.com/lijianglang89-hash/python-automation-for-real-estate/issues).

Note that the scripts here are kept in sync with the book. If a site changes its
markup and a selector breaks, an issue is genuinely useful — but the fix will
often be a teaching moment in the next edition rather than a patch here.

---

## 🛒 About the author

**James Jiang** writes about practical automation for people who work with
property data.

- Amazon Author Central: *[link once the book is live]*
- Found this useful? A ⭐ on this repository helps other people find it — and
  the book goes into everything the repository deliberately leaves out.
