"""
Coverage Validation: edgar-crawler (EDGAR index) vs Hoberg-Phillips TNIC (2005)
Compares 10-K firm coverage for year 2005.
"""
# %% Setup
import io, itertools, os, zipfile, time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

WORKSPACE = Path(__file__).resolve().parents[2]  # _myworkspace/
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"
OUTPUT.mkdir(parents=True, exist_ok=True)

load_dotenv(WORKSPACE.parent / ".env")

USER_AGENT = "Academic Research marcozhang1231@gmail.com"

# %% Step 1: Download Hoberg-Phillips TNIC HHI firm-year panel
TNIC_URL = "https://hobergphillips.tuck.dartmouth.edu/idata/TNIC3HHIdata.zip"
print("Downloading TNIC HHI data...")
r = requests.get(TNIC_URL, headers={"User-Agent": USER_AGENT})
r.raise_for_status()

with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
    print(f"  Files in zip: {zf.namelist()}")
    with zf.open("TNIC3HHIdata.txt") as f:
        tnic = pd.read_csv(f, sep="\t")

print(f"  TNIC shape: {tnic.shape}")
print(f"  Columns: {list(tnic.columns)}")
print(f"  Year range: {tnic['year'].min()} - {tnic['year'].max()}")

# %% Filter TNIC to 2005
tnic_2005 = tnic[tnic["year"] == 2005].copy()
tnic_gvkeys = set(tnic_2005["gvkey"].unique())
print(f"\nTNIC 2005: {len(tnic_gvkeys)} unique firms (gvkey)")

tnic_2005.to_csv(OUTPUT / "tnic_2005_firms.csv", index=False)
print(f"  Saved to {OUTPUT / 'tnic_2005_firms.csv'}")

# %% Step 2: Fetch EDGAR full-index for all 4 quarters of 2005
BASE = "https://www.sec.gov/Archives/edgar/full-index"

def fetch_index(year, qtr):
    url = f"{BASE}/{year}/QTR{qtr}/master.zip"
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)).open("master.idx") as f:
        lines = [line.decode("latin-1") for line in itertools.islice(f, 11, None)]
    rows = [line.strip().split("|") for line in lines if "|" in line]
    return pd.DataFrame(rows, columns=["CIK", "Company", "Type", "Date", "Filename"])

dfs = []
for qtr in range(1, 5):
    print(f"Fetching EDGAR full index for 2005 Q{qtr}...")
    dfs.append(fetch_index(2005, qtr))
    time.sleep(0.2)
edgar = pd.concat(dfs, ignore_index=True)
edgar["CIK"] = edgar["CIK"].astype(int)
print(f"\nTotal EDGAR filings in 2005: {len(edgar)}")

# %% Filter for 10-K variants
TEN_K_VARIANTS = ["10-K", "10-K/A", "10KSB", "10KSB/A", "NT 10-K", "NT 10-K/A",
                   "NTN 10K", "10-KT", "10-KT/A"]
edgar_10k = edgar[edgar["Type"].isin(TEN_K_VARIANTS)].copy()
print(f"\n10-K variant filings in 2005:")
print(edgar_10k["Type"].value_counts().to_string())
print(f"\nTotal 10-K variant filings: {len(edgar_10k)}")

edgar_ciks = set(edgar_10k["CIK"].unique())
print(f"Unique CIKs with 10-K variants: {len(edgar_ciks)}")

edgar_10k.to_csv(OUTPUT / "edgar_2005_10k.csv", index=False)

# %% Step 3: Get CIK ↔ gvkey crosswalk from WRDS
import psycopg2

print("\nConnecting to WRDS...")
conn = psycopg2.connect(
    host="wrds-pgdata.wharton.upenn.edu", port=9737, dbname="wrds",
    user=os.getenv("WRDS_USERNAME"), password=os.getenv("WRDS_PASSWORD"),
    sslmode="require",
)
crosswalk = pd.read_sql("""
    SELECT DISTINCT gvkey, cik
    FROM comp.company
    WHERE cik IS NOT NULL
""", conn)
conn.close()

crosswalk["cik"] = crosswalk["cik"].astype(int)
crosswalk["gvkey"] = crosswalk["gvkey"].astype(int)
print(f"Compustat crosswalk: {len(crosswalk)} gvkey-CIK pairs")
print(f"  Unique gvkeys: {crosswalk['gvkey'].nunique()}")
print(f"  Unique CIKs: {crosswalk['cik'].nunique()}")

crosswalk.to_csv(OUTPUT / "gvkey_cik_crosswalk.csv", index=False)

# %% Step 4: Compare coverage
# Map TNIC gvkeys to CIKs
tnic_with_cik = tnic_2005.merge(crosswalk, on="gvkey", how="left")
tnic_matched = tnic_with_cik[tnic_with_cik["cik"].notna()]
tnic_unmatched = tnic_with_cik[tnic_with_cik["cik"].isna()]
tnic_ciks = set(tnic_matched["cik"].astype(int).unique())

print(f"\n=== Coverage Comparison (2005 10-K) ===")
print(f"TNIC firms (gvkey):           {len(tnic_gvkeys)}")
print(f"  → matched to CIK:          {len(tnic_ciks)}")
print(f"  → unmatched (no CIK):      {len(tnic_unmatched['gvkey'].unique())}")
print(f"EDGAR 10-K firms (CIK):       {len(edgar_ciks)}")

# Overlap analysis
overlap = tnic_ciks & edgar_ciks
only_tnic = tnic_ciks - edgar_ciks
only_edgar = edgar_ciks - tnic_ciks

print(f"\nOverlap (in both):            {len(overlap)}")
print(f"Only in TNIC:                 {len(only_tnic)}")
print(f"Only in EDGAR:                {len(only_edgar)}")
print(f"Overlap rate (TNIC base):     {len(overlap)/len(tnic_ciks)*100:.1f}%")
print(f"Overlap rate (EDGAR base):    {len(overlap)/len(edgar_ciks)*100:.1f}%")

# %% Characterize EDGAR-only firms by filing type
edgar_only_filings = edgar_10k[edgar_10k["CIK"].isin(only_edgar)]
print(f"\n=== EDGAR-only firms by filing type ===")
print(edgar_only_filings["Type"].value_counts().to_string())

# %% Characterize TNIC-only firms (in TNIC but not in EDGAR 10-K index)
if only_tnic:
    tnic_only_gvkeys = tnic_with_cik[tnic_with_cik["cik"].isin(only_tnic)]["gvkey"].unique()
    print(f"\n=== TNIC-only firms (not in EDGAR 10-K index) ===")
    print(f"  Count: {len(only_tnic)} CIKs")
    # Check if these CIKs have OTHER filing types in EDGAR
    tnic_only_in_edgar = edgar[edgar["CIK"].isin(only_tnic)]
    if len(tnic_only_in_edgar):
        print(f"  These CIKs DO have other filings in EDGAR:")
        print(f"  {tnic_only_in_edgar['Type'].value_counts().head(10).to_string()}")
    else:
        print(f"  These CIKs have NO filings in the 2005 EDGAR index")

# %% Summary table
summary = pd.DataFrame({
    "Source": ["Hoberg-Phillips TNIC", "EDGAR (all 10-K variants)", "Overlap",
               "Only TNIC", "Only EDGAR"],
    "Firms": [len(tnic_ciks), len(edgar_ciks), len(overlap),
              len(only_tnic), len(only_edgar)],
})
print(f"\n=== Summary ===")
print(summary.to_string(index=False))

summary.to_csv(OUTPUT / "coverage_summary.csv", index=False)
print(f"\nAll outputs saved to {OUTPUT}/")
