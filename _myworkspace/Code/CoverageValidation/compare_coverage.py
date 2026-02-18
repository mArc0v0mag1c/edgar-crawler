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

# %% Step 5: FY-aligned comparison using Compustat funda
# The EDGAR master index is organized by filing date (calendar year), not fiscal year.
# TNIC year = Compustat fiscal year. A Dec FY-end firm in TNIC year=2005 files in early 2006.
# To do a clean comparison, we use comp.funda to get the exact fiscal year-end dates,
# then fetch the right EDGAR index quarters based on expected filing dates.

print("\n" + "="*60)
print("Step 5: FY-aligned comparison using Compustat funda")
print("="*60)

# Get FY2005 firms from Compustat (same source TNIC uses)
print("\nQuerying Compustat funda for FY2005...")
conn = psycopg2.connect(
    host="wrds-pgdata.wharton.upenn.edu", port=9737, dbname="wrds",
    user=os.getenv("WRDS_USERNAME"), password=os.getenv("WRDS_PASSWORD"),
    sslmode="require",
)
funda = pd.read_sql("""
    SELECT gvkey, cik, datadate, fyear, fyr
    FROM comp.funda
    WHERE fyear = 2005
    AND indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'
    AND cik IS NOT NULL
""", conn)
conn.close()

funda["cik"] = funda["cik"].astype(int)
funda["gvkey"] = funda["gvkey"].astype(int)
funda_ciks = set(funda["cik"].unique())

print(f"Compustat FY2005 firms: {len(funda)} (unique CIKs: {len(funda_ciks)})")
print(f"Fiscal year-end month distribution:")
print(funda["fyr"].value_counts().sort_index().to_string())
print(f"datadate range: {funda['datadate'].min()} to {funda['datadate'].max()}")

# 10-Ks are due 60-90 days after fiscal year-end (depends on filer status).
# For a FY ending Dec 2005 → filed by Mar 2006 (Q1 2006).
# For a FY ending May 2005 → filed by Aug 2005 (Q3 2005).
# The filing window for ALL FY2005 firms spans: ~Aug 2005 to ~Aug 2006.
# We already have 2005 Q1-Q4. Fetch 2006 Q1-Q3 to cover even late filers.

adj_dfs = []
for qtr in [1, 2, 3]:
    print(f"Fetching EDGAR full index for 2006 Q{qtr}...")
    adj_dfs.append(fetch_index(2006, qtr))
    time.sleep(0.2)
edgar_2006 = pd.concat(adj_dfs, ignore_index=True)
edgar_2006["CIK"] = edgar_2006["CIK"].astype(int)

# Combine 2005 full year + 2006 Q1-Q3 for the complete filing window
edgar_wide = pd.concat([edgar, edgar_2006], ignore_index=True)
edgar_wide_10k = edgar_wide[edgar_wide["Type"].isin(TEN_K_VARIANTS)]
edgar_wide_ciks = set(edgar_wide_10k["CIK"].unique())

print(f"\nEDGAR 10-K CIKs (2005Q1-2006Q3 window): {len(edgar_wide_ciks)}")

# %% FY-aligned comparison: Compustat FY2005 CIKs vs EDGAR wide window
# This answers: "For every firm Compustat says had FY2005 data, can we find a 10-K in EDGAR?"
compustat_in_edgar = funda_ciks & edgar_wide_ciks
compustat_not_in_edgar = funda_ciks - edgar_wide_ciks

print(f"\n=== FY-Aligned Coverage (Compustat FY2005 vs EDGAR 2005Q1-2006Q3) ===")
print(f"Compustat FY2005 firms (CIK):  {len(funda_ciks)}")
print(f"Found in EDGAR (10-K):         {len(compustat_in_edgar)} ({len(compustat_in_edgar)/len(funda_ciks)*100:.1f}%)")
print(f"NOT found in EDGAR:            {len(compustat_not_in_edgar)} ({len(compustat_not_in_edgar)/len(funda_ciks)*100:.1f}%)")

# Now compare TNIC against this FY-aligned view
tnic_in_edgar_wide = tnic_ciks & edgar_wide_ciks
tnic_not_in_edgar_wide = tnic_ciks - edgar_wide_ciks

print(f"\n=== TNIC FY2005 vs EDGAR 2005Q1-2006Q3 ===")
print(f"TNIC firms (CIK):              {len(tnic_ciks)}")
print(f"Found in EDGAR (10-K):         {len(tnic_in_edgar_wide)} ({len(tnic_in_edgar_wide)/len(tnic_ciks)*100:.1f}%)")
print(f"NOT found in EDGAR:            {len(tnic_not_in_edgar_wide)} ({len(tnic_not_in_edgar_wide)/len(tnic_ciks)*100:.1f}%)")

# Characterize the remaining TNIC-only misses
if tnic_not_in_edgar_wide:
    still_missing_filings = edgar_wide[edgar_wide["CIK"].isin(tnic_not_in_edgar_wide)]
    print(f"\n  These {len(tnic_not_in_edgar_wide)} CIKs have other EDGAR filings (2005Q1-2006Q3):")
    if len(still_missing_filings):
        print(f"  {still_missing_filings['Type'].value_counts().head(10).to_string()}")
    else:
        print(f"  None — no filings at all in this window")

# EDGAR-only in wide window (not in TNIC or Compustat)
edgar_not_in_compustat = edgar_wide_ciks - funda_ciks
print(f"\n=== EDGAR-only firms (not in Compustat FY2005) ===")
print(f"Count: {len(edgar_not_in_compustat)}")

# %% Step 6: Verify remaining misses via SEC submissions API (period_of_report)
# For CIKs in TNIC but not in EDGAR wide window, check if they actually filed
# a 10-K with reportDate (=period_of_report) in FY2005 via the SEC API.

if tnic_not_in_edgar_wide:
    print(f"\n{'='*60}")
    print(f"Step 6: Verify {len(tnic_not_in_edgar_wide)} remaining misses via SEC API")
    print(f"{'='*60}")

    TEN_K_FORMS = {"10-K", "10-K/A", "10-KSB", "10KSB", "10KSB/A", "10-KT", "10-KT/A"}
    recovered_via_api = []
    no_10k_found = []
    api_errors = []

    for i, cik in enumerate(sorted(tnic_not_in_edgar_wide)):
        cik_str = f"{cik:010d}"
        url = f"https://data.sec.gov/submissions/CIK{cik_str}.json"
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT})
            time.sleep(0.11)  # SEC rate limit: 10 req/sec
            if r.status_code != 200:
                api_errors.append(cik)
                continue
            data = r.json()
            recent = data["filings"]["recent"]
            found = False
            for j in range(len(recent["form"])):
                form = recent["form"][j]
                report_date = recent["reportDate"][j]
                if form in TEN_K_FORMS and report_date.startswith("2005"):
                    recovered_via_api.append({
                        "cik": cik, "form": form,
                        "reportDate": report_date,
                        "filingDate": recent["filingDate"][j],
                    })
                    found = True
                    break
            if not found:
                no_10k_found.append(cik)
        except Exception as e:
            api_errors.append(cik)

        if (i + 1) % 50 == 0:
            print(f"  Checked {i+1}/{len(tnic_not_in_edgar_wide)} CIKs...")

    print(f"\n=== SEC API Verification Results ===")
    print(f"Recovered (10-K with reportDate in 2005): {len(recovered_via_api)}")
    print(f"No FY2005 10-K found:                     {len(no_10k_found)}")
    print(f"API errors:                               {len(api_errors)}")

    if recovered_via_api:
        recovered_df = pd.DataFrame(recovered_via_api)
        print(f"\nRecovered filings:")
        print(recovered_df.to_string())
        recovered_df.to_csv(OUTPUT / "recovered_via_api.csv", index=False)

# Final summary (Steps 1-6, using comp.company crosswalk)
total_tnic_covered = len(tnic_in_edgar_wide) + len(recovered_via_api) if tnic_not_in_edgar_wide else len(tnic_in_edgar_wide)
print(f"\n{'='*60}")
print(f"STEPS 1-6 SUMMARY (comp.company crosswalk)")
print(f"{'='*60}")
print(f"Compustat FY2005 CIKs:         {len(funda_ciks)}")
print(f"TNIC FY2005 CIKs:              {len(tnic_ciks)}")
print(f"EDGAR 10-K CIKs (wide window): {len(edgar_wide_ciks)}")
print(f"TNIC covered by EDGAR+API:     {total_tnic_covered} ({total_tnic_covered/len(tnic_ciks)*100:.1f}% of TNIC)")
print(f"TNIC truly missing:            {len(tnic_ciks) - total_tnic_covered}")
print(f"Compustat in EDGAR:            {len(compustat_in_edgar)} ({len(compustat_in_edgar)/len(funda_ciks)*100:.1f}% of Compustat)")
print(f"Compustat not in EDGAR:        {len(compustat_not_in_edgar)}")

# %% Step 7: Fix crosswalk — use comp.funda time-varying CIK instead of comp.company
# comp.company returns the firm's CURRENT CIK (successor entity after mergers/reorgs).
# comp.funda WHERE fyear = 2005 returns the CIK that was in use at the time of filing.
# This fixes the ~230 firms mapped to successor CIKs that didn't exist in 2005.

print(f"\n{'='*60}")
print(f"Step 7: Corrected crosswalk using comp.funda time-varying CIK")
print(f"{'='*60}")

# funda was already queried in Step 5 — it has gvkey, cik, fyear for FY2005.
# Use it as the crosswalk instead of comp.company.
funda_crosswalk = funda[["gvkey", "cik"]].drop_duplicates()
print(f"\nFunda FY2005 crosswalk: {len(funda_crosswalk)} gvkey-CIK pairs")
print(f"  Unique gvkeys: {funda_crosswalk['gvkey'].nunique()}")
print(f"  Unique CIKs: {funda_crosswalk['cik'].nunique()}")

# Re-map TNIC gvkeys to CIKs using funda crosswalk
tnic_with_funda_cik = tnic_2005.merge(funda_crosswalk, on="gvkey", how="left")
tnic_funda_matched = tnic_with_funda_cik[tnic_with_funda_cik["cik"].notna()]
tnic_funda_unmatched = tnic_with_funda_cik[tnic_with_funda_cik["cik"].isna()]
tnic_funda_ciks = set(tnic_funda_matched["cik"].astype(int).unique())

print(f"\nTNIC → funda crosswalk results:")
print(f"  TNIC gvkeys:         {len(tnic_gvkeys)}")
print(f"  Matched to CIK:     {len(tnic_funda_ciks)}")
print(f"  Unmatched (no CIK): {len(tnic_funda_unmatched['gvkey'].unique())}")

# Compare: how many comp.company CIKs differ from funda CIKs for the same gvkey?
company_crosswalk_map = crosswalk.set_index("gvkey")["cik"].to_dict()
funda_crosswalk_map = funda_crosswalk.set_index("gvkey")["cik"].to_dict()
changed_ciks = 0
for gvk in tnic_gvkeys:
    co_cik = company_crosswalk_map.get(gvk)
    fu_cik = funda_crosswalk_map.get(gvk)
    if co_cik is not None and fu_cik is not None and co_cik != fu_cik:
        changed_ciks += 1
print(f"  CIKs that differ (company vs funda): {changed_ciks}")

# Overlap analysis with funda crosswalk
overlap_f = tnic_funda_ciks & edgar_wide_ciks
only_tnic_f = tnic_funda_ciks - edgar_wide_ciks
only_edgar_f = edgar_wide_ciks - tnic_funda_ciks

print(f"\n=== Coverage Comparison (funda crosswalk + EDGAR wide window) ===")
print(f"TNIC firms (funda CIK):        {len(tnic_funda_ciks)}")
print(f"EDGAR 10-K CIKs (wide window): {len(edgar_wide_ciks)}")
print(f"Overlap (in both):             {len(overlap_f)}")
print(f"Only in TNIC:                  {len(only_tnic_f)}")
print(f"Only in EDGAR:                 {len(only_edgar_f)}")
print(f"Overlap rate (TNIC base):      {len(overlap_f)/len(tnic_funda_ciks)*100:.1f}%")

# Characterize remaining TNIC-only misses
if only_tnic_f:
    still_missing = edgar_wide[edgar_wide["CIK"].isin(only_tnic_f)]
    print(f"\n  Remaining {len(only_tnic_f)} TNIC-only CIKs — other EDGAR filings:")
    if len(still_missing):
        print(f"  {still_missing['Type'].value_counts().head(10).to_string()}")
    else:
        print(f"  None — no filings at all in 2005Q1-2006Q3")

    # How many have NO filings at all in the wide window?
    missing_with_filings = still_missing["CIK"].nunique()
    missing_no_filings = len(only_tnic_f) - missing_with_filings
    print(f"\n  With other EDGAR filings:  {missing_with_filings}")
    print(f"  No EDGAR filings at all:   {missing_no_filings}")

# Save corrected summary
summary_corrected = pd.DataFrame({
    "Source": ["Hoberg-Phillips TNIC (funda CIK)", "EDGAR 10-K (2005Q1-2006Q3)",
               "Overlap", "Only TNIC", "Only EDGAR"],
    "Firms": [len(tnic_funda_ciks), len(edgar_wide_ciks), len(overlap_f),
              len(only_tnic_f), len(only_edgar_f)],
})
summary_corrected.to_csv(OUTPUT / "coverage_summary_corrected.csv", index=False)

# Improvement over old crosswalk
print(f"\n=== Crosswalk Fix Impact ===")
print(f"comp.company crosswalk: {len(overlap)}/{ len(tnic_ciks)} = {len(overlap)/len(tnic_ciks)*100:.1f}% (calendar year)")
print(f"comp.company + wide:    {len(tnic_in_edgar_wide)}/{len(tnic_ciks)} = {len(tnic_in_edgar_wide)/len(tnic_ciks)*100:.1f}% (wide window)")
print(f"comp.funda + wide:      {len(overlap_f)}/{len(tnic_funda_ciks)} = {len(overlap_f)/len(tnic_funda_ciks)*100:.1f}% (corrected)")
print(f"\nFinal: {len(only_tnic_f)} TNIC firms still not found in EDGAR 10-K index.")
