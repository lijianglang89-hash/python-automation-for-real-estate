"""
generate_cma.py
Turns raw comparable-sales data into a styled, client-ready CMA report (.docx).

Usage:
    python generate_cma.py
Output:
    CMA_Report_<address-slug>.docx
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

# --------------------------------------------------------------------------
# Style constants — change these once and the whole report re-brands
# --------------------------------------------------------------------------
NAVY = RGBColor(0x1F, 0x38, 0x64)
ACCENT = RGBColor(0x00, 0x66, 0xCC)
VALUATION_BAND = 0.05          # +/- 5% around the point estimate


# --------------------------------------------------------------------------
# STAGE 1 — Analytics
# --------------------------------------------------------------------------
def build_comps_dataframe(comps: list[dict]) -> pd.DataFrame:
    """Coerce comps into numeric form and discard rows that cannot be used."""
    df = pd.DataFrame(comps)

    required = {"Address", "Price", "SqFt"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Comps data is missing required columns: {sorted(missing)}")

    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df["SqFt"] = pd.to_numeric(df["SqFt"], errors="coerce")

    # An unusable comp is worse than a missing comp: drop, do not guess.
    df = df.dropna(subset=["Price", "SqFt"])
    df = df[(df["SqFt"] > 0) & (df["Price"] > 0)]

    if df.empty:
        raise ValueError("No valid comps remain after cleaning. Check the input data.")

    df["Price_Per_SqFt"] = (df["Price"] / df["SqFt"]).round(2)
    return df.sort_values("Price_Per_SqFt", ascending=False).reset_index(drop=True)


def calculate_cma_metrics(df: pd.DataFrame, subject_sqft: float) -> dict:
    """Compute the valuation metrics that drive the report."""
    median_ppsf = float(df["Price_Per_SqFt"].median())
    point_estimate = subject_sqft * median_ppsf

    return {
        "Comp_Count": len(df),
        "Median_Price_Per_SqFt": median_ppsf,
        "Average_Price_Per_SqFt": float(df["Price_Per_SqFt"].mean()),
        "Lowest_Price": float(df["Price"].min()),
        "Highest_Price": float(df["Price"].max()),
        "Point_Estimate": point_estimate,
        "Range_Low": point_estimate * (1 - VALUATION_BAND),
        "Range_High": point_estimate * (1 + VALUATION_BAND),
    }


# --------------------------------------------------------------------------
# STAGE 3 — Template build
# --------------------------------------------------------------------------
def add_styled_heading(doc: Document, text: str, level: int) -> None:
    heading = doc.add_heading(level=level)
    run = heading.add_run(text)
    run.font.color.rgb = NAVY
    run.font.name = "Calibri"


def format_number(value) -> str:
    """Render 2.0 as '2' and 2.5 as '2.5'; pass through anything non-numeric."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def build_comps_table(doc: Document, df: pd.DataFrame) -> None:
    """Render the comps DataFrame as a bordered, header-shaded Word table."""
    headers = ["Address", "Beds / Baths", "Sq Ft", "List Price", "$ / SqFt"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header_cells = table.rows[0].cells
    for index, label in enumerate(headers):
        header_cells[index].text = label
        for paragraph in header_cells[index].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.size = Pt(9.5)

    for _, row in df.iterrows():
        cells = table.add_row().cells
        # IMPORTANT: assign to cells[i] individually.
        # cells.text = "..." sets an attribute on a Python list and silently
        # does nothing — a classic cause of blank tables.
        cells[0].text = str(row["Address"])
        cells[1].text = (f"{format_number(row.get('Beds', 'N/A'))} / "
                         f"{format_number(row.get('Baths', 'N/A'))}")
        cells[2].text = f"{int(row['SqFt']):,}"
        cells[3].text = f"${int(row['Price']):,}"
        cells[4].text = f"${row['Price_Per_SqFt']:,.2f}"

        for cell in cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)

    # Fixed column widths stop Word from re-flowing the table on narrow pages.
    widths = [Inches(2.0), Inches(1.0), Inches(0.8), Inches(1.1), Inches(0.9)]
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = width


def generate_cma_report(
    subject_address: str,
    subject_sqft: float,
    comps: list[dict],
    output_dir: Path = Path("reports"),
) -> Path:
    """Full pipeline: analytics -> valuation -> styled .docx report."""
    df = build_comps_dataframe(comps)
    metrics = calculate_cma_metrics(df, subject_sqft)

    doc = Document()

    # ---- Title block -----------------------------------------------------
    title = doc.add_paragraph()
    title_run = title.add_run("COMPARATIVE MARKET ANALYSIS")
    title_run.bold = True
    title_run.font.size = Pt(20)
    title_run.font.color.rgb = NAVY

    meta = doc.add_paragraph()
    meta.add_run("Subject Property: ").bold = True
    meta.add_run(f"{subject_address}\n")
    meta.add_run("Prepared: ").bold = True
    meta.add_run(datetime.now().strftime("%B %d, %Y"))

    doc.add_paragraph()

    # ---- Executive summary ----------------------------------------------
    add_styled_heading(doc, "1. Executive Valuation Summary", 1)

    summary = doc.add_paragraph()
    summary.add_run(
        f"Based on {metrics['Comp_Count']} comparable properties and a subject "
        f"area of {subject_sqft:,.0f} Sq Ft, the estimated market value is "
    ).font.size = Pt(11)

    estimate_run = summary.add_run(f"${metrics['Point_Estimate']:,.0f}")
    estimate_run.bold = True
    estimate_run.font.size = Pt(13)
    estimate_run.font.color.rgb = ACCENT

    summary.add_run(
        f"\n\nRecommended listing range: "
        f"${metrics['Range_Low']:,.0f} – ${metrics['Range_High']:,.0f}\n"
        f"Neighbourhood median: ${metrics['Median_Price_Per_SqFt']:,.2f} per Sq Ft\n"
        f"Comp price range: ${metrics['Lowest_Price']:,.0f} – "
        f"${metrics['Highest_Price']:,.0f}"
    )

    # ---- Comps table -----------------------------------------------------
    add_styled_heading(doc, "2. Comparable Properties", 1)
    build_comps_table(doc, df)

    # ---- Methodology note ------------------------------------------------
    add_styled_heading(doc, "3. Methodology", 1)
    method = doc.add_paragraph()
    method.add_run(
        "The point estimate applies the median price per square foot of the "
        "comparable set to the subject property's area. The median is used in "
        "preference to the arithmetic mean so that a single outlier sale cannot "
        "distort the valuation. The recommended range reflects a ±"
        f"{int(VALUATION_BAND * 100)}% band around that estimate and is intended "
        "as a pricing guide, not a formal appraisal."
    ).font.size = Pt(10)

    # ---- Save ------------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", subject_address.lower()).strip("_")[:40]
    output_path = output_dir / f"CMA_Report_{slug}.docx"
    doc.save(output_path)

    print(f"[OK] Report generated: {output_path.resolve()}")
    print(f"[OK] Point estimate: ${metrics['Point_Estimate']:,.0f} "
          f"(range ${metrics['Range_Low']:,.0f} – ${metrics['Range_High']:,.0f})")
    return output_path


# --------------------------------------------------------------------------
# Demo run
# --------------------------------------------------------------------------
SAMPLE_COMPS = [
    {"Address": "742 Evergreen Terrace", "Beds": 3, "Baths": 2,   "SqFt": 1800, "Price": 520000},
    {"Address": "748 Evergreen Terrace", "Beds": 4, "Baths": 2.5, "SqFt": 2100, "Price": 595000},
    {"Address": "710 Evergreen Terrace", "Beds": 3, "Baths": 2,   "SqFt": 1750, "Price": 499000},
    {"Address": "755 Evergreen Terrace", "Beds": 4, "Baths": 3,   "SqFt": 2300, "Price": 640000},
    {"Address": "761 Evergreen Terrace", "Beds": 3, "Baths": 2,   "SqFt": 1850, "Price": 531000},
]

if __name__ == "__main__":
    generate_cma_report(
        subject_address="730 Evergreen Terrace, Springfield",
        subject_sqft=1950,
        comps=SAMPLE_COMPS,
    )
