"""
verify_setup.py
Confirms that Python and every library used in this book are correctly installed,
then performs a real data operation so you can see output, not just a version number.
"""

import sys
import platform

# --- Part 1: Confirm the interpreter itself -------------------------------
print("=" * 62)
print("ENVIRONMENT CHECK")
print("=" * 62)
print(f"Python version : {sys.version.split()[0]}")
print(f"Operating system: {platform.system()} {platform.release()}")
print(f"Executable      : {sys.executable}")
print("-" * 62)

# --- Part 2: Import each library, reporting clearly on failure ------------
REQUIRED_LIBRARIES = [
    ("pandas", "pandas"),
    ("requests", "requests"),
    ("bs4", "beautifulsoup4"),
    ("openpyxl", "openpyxl"),
    ("docx", "python-docx"),
]

missing = []
for import_name, pip_name in REQUIRED_LIBRARIES:
    try:
        module = __import__(import_name)
        version = getattr(module, "__version__", "installed")
        print(f"[ OK ]   {pip_name:<16} version {version}")
    except ImportError:
        print(f"[MISS]   {pip_name:<16} NOT INSTALLED")
        missing.append(pip_name)

print("-" * 62)

if missing:
    print("\nFix this by running the following command:\n")
    print(f"    pip install {' '.join(missing)}\n")
    sys.exit(1)

# --- Part 3: Prove it works with a real data operation --------------------
print("RUNNING A LIVE DATA TEST...\n")

import pandas as pd

# Simulated raw MLS export — deliberately messy, exactly like a real one.
raw_mls_export = [
    {"MLS_ID": "A1023", "Address": "742 Evergreen Terrace", "List Price": "$520,000",
     "Sq Ft": "1,800", "Beds": 3, "DOM": 12},
    {"MLS_ID": "A1024", "Address": "748 Evergreen Terrace", "List Price": "$595,000",
     "Sq Ft": "2,100", "Beds": 4, "DOM": 4},
    {"MLS_ID": "A1025", "Address": "710 Evergreen Terrace", "List Price": "$499,000",
     "Sq Ft": "1,750", "Beds": 3, "DOM": 31},
]

df = pd.DataFrame(raw_mls_export)

# Clean the money and area columns: strip "$" and "," then cast to numbers.
df["List Price"] = pd.to_numeric(df["List Price"].str.replace(r"[$,]", "", regex=True))
df["Sq Ft"] = pd.to_numeric(df["Sq Ft"].str.replace(",", "", regex=False))

# Derive the single most useful valuation metric in residential real estate.
df["Price per SqFt"] = (df["List Price"] / df["Sq Ft"]).round(2)

print(df.to_string(index=False))
print("-" * 62)
print(f"Median price per SqFt across comps: ${df['Price per SqFt'].median():,.2f}")
print(f"Average days on market (DOM)      : {df['DOM'].mean():.1f} days")
print("=" * 62)
print("SUCCESS — your environment is ready for Chapter 2.")
