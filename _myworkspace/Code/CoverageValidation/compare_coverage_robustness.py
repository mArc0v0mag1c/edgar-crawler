"""
Step A8: Robustness — period_of_report matching for EDGAR 10-K coverage validation.

Fetches reportDate (= period_of_report) from SEC submissions API for ALL 10-K
filings in EDGAR full-index 2005-2006, then re-does the TNIC coverage comparison
using exact fiscal-year matching instead of filing-date window heuristics.

Usage: uv run python _myworkspace/Code/CoverageValidation/compare_coverage_robustness.py
"""

import io, itertools, os, time, zipfile
from pathlib import Path

import pandas as pd
import requests

WORKSPACE = Path(__file__).resolve().parents[2]  # _myworkspace/
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"
OUTPUT.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Academic Research marcozhang1231@gmail.com"

TEN_K_VARIANTS = [
    "10-K", "10-K/A", "10KSB", "10KSB/A", "10-KT", "10-KT/A",
]
# Exclude NT/NTN — those are late-filing notifications, not actual 10-Ks.

TEN_K_FORMS_API = {
    "10-K", "10-K/A", "10-KSB", "10KSB", "10KSB/A", "10-KT", "10-KT/A",
}

BASE = "https://www.sec.gov/Archives/edgar/full-index"


# ── Phase 1: Build wide-window EDGAR 10-K index (2005 + 2006) ───────────────

def fetch_index(year, qtr):
    """Fetch EDGAR master index for a given year/quarter."""
    url = f"{BASE}/{year}/QTR{qtr}/master.zip"
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)).open("master.idx") as f:
        lines = [line.decode("latin-1") for line in itertools.islice(f, 11, None)]
    rows = [line.strip().split("|") for line in lines if "|" in line]
    return pd.DataFrame(rows, columns=["CIK", "Company", "Type", "Date", "Filename"])


def phase1_fetch_edgar_index():
    """Fetch EDGAR full-index for 2005 Q1-Q4 and 2006 Q1-Q4, filter to 10-K."""
    cache_path = OUTPUT / "edgar_2005_2006_10k.csv"
    if cache_path.exists():
        print(f"Phase 1: Loading cached {cache_path.name}")
        df = pd.read_csv(cache_path)
        df["CIK"] = df["CIK"].astype(int)
        print(f"  {len(df)} filings, {df['CIK'].nunique()} unique CIKs")
        return df

    dfs = []
    for year in [2005, 2006]:
        for qtr in range(1, 5):
            print(f"  Fetching EDGAR full-index {year} Q{qtr}...")
            dfs.append(fetch_index(year, qtr))
            time.sleep(0.2)

    edgar = pd.concat(dfs, ignore_index=True)
    edgar["CIK"] = edgar["CIK"].astype(int)
    print(f"  Total EDGAR filings 2005-2006: {len(edgar)}")

    edgar_10k = edgar[edgar["Type"].isin(TEN_K_VARIANTS)].copy()
    print(f"  10-K variant filings: {len(edgar_10k)}")
    print(edgar_10k["Type"].value_counts().to_string())

    edgar_10k.to_csv(cache_path, index=False)
    print(f"  Saved to {cache_path.name}")
    return edgar_10k


# ── Phase 2: Fetch reportDate from SEC API ──────────────────────────────────

def phase2_fetch_report_dates(edgar_10k):
    """Query SEC submissions API for each unique CIK, extract reportDate for 10-K filings."""
    out_path = OUTPUT / "edgar_10k_report_dates.csv"

    # Check for partial results (resume support)
    already_done = set()
    if out_path.exists():
        existing = pd.read_csv(out_path)
        already_done = set(existing["CIK"].unique())
        print(f"Phase 2: Found {len(already_done)} CIKs already fetched, resuming...")
        results = existing.to_dict("records")
    else:
        results = []

    all_ciks = sorted(edgar_10k["CIK"].unique())
    remaining = [c for c in all_ciks if c not in already_done]
    total = len(all_ciks)
    print(f"Phase 2: {len(remaining)} CIKs to query ({len(already_done)} done, {total} total)")

    errors = []
    for i, cik in enumerate(remaining):
        cik_str = f"{cik:010d}"
        url = f"https://data.sec.gov/submissions/CIK{cik_str}.json"
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT})
            time.sleep(0.11)  # SEC rate limit: 10 req/sec

            if r.status_code != 200:
                errors.append((cik, f"HTTP {r.status_code}"))
                continue

            data = r.json()
            recent = data["filings"]["recent"]
            for j in range(len(recent["form"])):
                form = recent["form"][j]
                if form in TEN_K_FORMS_API:
                    results.append({
                        "CIK": cik,
                        "form": form,
                        "filingDate": recent["filingDate"][j],
                        "reportDate": recent["reportDate"][j],
                    })

        except Exception as e:
            errors.append((cik, str(e)))

        # Progress + periodic save
        done_total = len(already_done) + i + 1
        if (i + 1) % 500 == 0:
            print(f"  {done_total}/{total} CIKs queried ({len(errors)} errors so far)...")
            # Save checkpoint
            pd.DataFrame(results).to_csv(out_path, index=False)

    # Final save
    df = pd.DataFrame(results)
    df.to_csv(out_path, index=False)
    print(f"\n  Saved {len(df)} 10-K records for {df['CIK'].nunique()} CIKs to {out_path.name}")
    if errors:
        print(f"  Errors: {len(errors)} CIKs failed (first 5: {errors[:5]})")
    return df


# ── Phase 3: TNIC comparison using reportDate ───────────────────────────────

def phase3_compare(report_dates):
    """Re-do TNIC vs EDGAR comparison using reportDate year = 2005."""
    print(f"\n{'='*60}")
    print("Phase 3: TNIC coverage comparison using reportDate")
    print(f"{'='*60}")

    # Load TNIC 2005 firms
    tnic = pd.read_csv(OUTPUT / "tnic_2005_firms.csv")
    tnic_gvkeys = set(tnic["gvkey"].unique())
    print(f"\nTNIC 2005 firms: {len(tnic_gvkeys)} gvkeys")

    # Load crosswalk
    crosswalk = pd.read_csv(OUTPUT / "gvkey_cik_crosswalk.csv")
    crosswalk["cik"] = crosswalk["cik"].astype(int)
    crosswalk["gvkey"] = crosswalk["gvkey"].astype(int)

    # Map TNIC gvkeys to CIKs
    tnic_with_cik = tnic.merge(crosswalk, on="gvkey", how="left")
    tnic_matched = tnic_with_cik[tnic_with_cik["cik"].notna()]
    tnic_ciks = set(tnic_matched["cik"].astype(int).unique())
    print(f"TNIC matched to CIK: {len(tnic_ciks)}")

    # Filter report_dates to FY2005 (reportDate year = 2005)
    report_dates = report_dates.copy()
    report_dates["reportYear"] = report_dates["reportDate"].str[:4].astype(int)

    fy2005 = report_dates[report_dates["reportYear"] == 2005]
    edgar_fy2005_ciks = set(fy2005["CIK"].unique())
    print(f"\nEDGAR CIKs with reportDate in 2005: {len(edgar_fy2005_ciks)}")
    print(f"  Total 10-K filings with reportDate in 2005: {len(fy2005)}")
    print(f"  Form types:")
    print(fy2005["form"].value_counts().to_string())

    # Overlap analysis
    overlap = tnic_ciks & edgar_fy2005_ciks
    only_tnic = tnic_ciks - edgar_fy2005_ciks
    only_edgar = edgar_fy2005_ciks - tnic_ciks

    print(f"\n=== Robustness Coverage Comparison (reportDate = FY2005) ===")
    print(f"TNIC firms (CIK):              {len(tnic_ciks)}")
    print(f"EDGAR FY2005 firms (CIK):      {len(edgar_fy2005_ciks)}")
    print(f"Overlap (in both):             {len(overlap)}")
    print(f"Only in TNIC:                  {len(only_tnic)}")
    print(f"Only in EDGAR:                 {len(only_edgar)}")
    print(f"Overlap rate (TNIC base):      {len(overlap)/len(tnic_ciks)*100:.1f}%")
    print(f"Overlap rate (EDGAR base):     {len(overlap)/len(edgar_fy2005_ciks)*100:.1f}%")

    # Compare against previous results
    print(f"\n=== Comparison with Previous Steps ===")
    print(f"Step A4 (calendar year):       4,624/4,992 = 92.6%")
    print(f"Step A5 (wide window):         4,761/4,992 = 95.4%")
    print(f"Step A8 (reportDate match):    {len(overlap)}/{len(tnic_ciks)} = {len(overlap)/len(tnic_ciks)*100:.1f}%")

    # Save summary
    summary = pd.DataFrame({
        "Source": [
            "Hoberg-Phillips TNIC (CIK)",
            "EDGAR FY2005 (reportDate match)",
            "Overlap",
            "Only TNIC",
            "Only EDGAR",
        ],
        "Firms": [
            len(tnic_ciks),
            len(edgar_fy2005_ciks),
            len(overlap),
            len(only_tnic),
            len(only_edgar),
        ],
    })
    summary.to_csv(OUTPUT / "coverage_summary_robustness.csv", index=False)
    print(f"\nSaved to coverage_summary_robustness.csv")

    return only_tnic


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Step A8: Robustness — period_of_report matching")
    print("=" * 60)

    print("\n--- Phase 1: EDGAR full-index 2005-2006 ---")
    edgar_10k = phase1_fetch_edgar_index()

    print("\n--- Phase 2: Fetch reportDate from SEC API ---")
    report_dates = phase2_fetch_report_dates(edgar_10k)

    print("\n--- Phase 3: TNIC comparison using reportDate ---")
    only_tnic = phase3_compare(report_dates)

    print(f"\nDone. All outputs in {OUTPUT}/")
