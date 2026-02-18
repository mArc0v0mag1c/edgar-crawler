"""
Step A9 — Option A: Fetch period_of_report via SEC API with pagination.

The SEC submissions API stores only ~1000 most recent filings in `filings.recent`.
Older filings are in paginated files at `filings.files[]`. For FY2005, many CIKs
need pagination to reach their historical 10-K filings.

This script:
1. Loads the EDGAR 2005-2006 10-K index (from Phase 1 of compare_coverage_robustness.py)
2. For each unique CIK, queries the SEC API and follows ALL pagination files
3. Extracts (CIK, form, filingDate, reportDate) for 10-K variants
4. Saves to edgar_10k_report_dates_paginated.csv
5. Re-does TNIC comparison using exact FY2005 reportDate matching

Usage: uv run python _myworkspace/Code/CoverageValidation/fetch_report_dates_api.py
"""

import json, time
from pathlib import Path

import pandas as pd
import requests

WORKSPACE = Path(__file__).resolve().parents[2]  # _myworkspace/
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"
DATA = WORKSPACE / "Data" / "CoverageValidation"
OUTPUT.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Academic Research marcozhang1231@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}

TEN_K_FORMS = {
    "10-K", "10-K/A", "10-KSB", "10KSB", "10KSB/A", "10-KT", "10-KT/A",
}


def extract_10k_from_filing_block(block):
    """Extract 10-K filing records from an SEC API filing block (recent or paginated)."""
    records = []
    forms = block.get("form", [])
    filing_dates = block.get("filingDate", [])
    report_dates = block.get("reportDate", [])
    for j in range(len(forms)):
        if forms[j] in TEN_K_FORMS:
            records.append({
                "form": forms[j],
                "filingDate": filing_dates[j] if j < len(filing_dates) else "",
                "reportDate": report_dates[j] if j < len(report_dates) else "",
            })
    return records


def fetch_cik_all_filings(cik):
    """Fetch ALL 10-K filings for a CIK, following pagination."""
    try:
        cik_str = f"{cik:010d}"
        url = f"https://data.sec.gov/submissions/CIK{cik_str}.json"
        r = requests.get(url, headers=HEADERS, timeout=30)
        time.sleep(0.15)

        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"

        data = r.json()

        # Extract from recent filings
        records = extract_10k_from_filing_block(data["filings"]["recent"])

        # Follow pagination files
        for file_info in data["filings"].get("files", []):
            fname = file_info["name"]  # e.g. "CIK0000020-submissions-001.json"
            page_url = f"https://data.sec.gov/submissions/{fname}"
            pr = requests.get(page_url, headers=HEADERS, timeout=30)
            time.sleep(0.15)
            if pr.status_code == 200:
                page_data = pr.json()
                records.extend(extract_10k_from_filing_block(page_data))

        # Tag all records with CIK
        for rec in records:
            rec["CIK"] = cik

        return records, None
    except Exception as e:
        return [], str(e)


def main():
    print("Step A9 — Option A: SEC API with pagination")
    print("=" * 60)

    # Load EDGAR 2005-2006 index
    edgar_path = OUTPUT / "edgar_2005_2006_10k.csv"
    edgar = pd.read_csv(edgar_path)
    edgar["CIK"] = edgar["CIK"].astype(int)
    all_ciks = sorted(edgar["CIK"].unique())
    print(f"EDGAR 2005-2006 index: {len(edgar)} filings, {len(all_ciks)} unique CIKs")

    # Resume support
    out_path = OUTPUT / "edgar_10k_report_dates_paginated.csv"
    already_done = set()
    results = []
    if out_path.exists():
        existing = pd.read_csv(out_path)
        already_done = set(existing["CIK"].unique())
        results = existing.to_dict("records")
        print(f"Resuming: {len(already_done)} CIKs already fetched")

    remaining = [c for c in all_ciks if c not in already_done]
    print(f"CIKs to query: {len(remaining)} ({len(already_done)} done, {len(all_ciks)} total)\n")

    errors = []
    for i, cik in enumerate(remaining):
        recs, err = fetch_cik_all_filings(cik)
        if err:
            errors.append((cik, err))
        else:
            results.extend(recs)

        done_total = len(already_done) + i + 1
        if (i + 1) % 500 == 0:
            pct = done_total / len(all_ciks) * 100
            print(f"  {done_total}/{len(all_ciks)} ({pct:.1f}%) — {len(errors)} errors — saving checkpoint...")
            pd.DataFrame(results).to_csv(out_path, index=False)

    # Final save
    df = pd.DataFrame(results)
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} 10-K records for {df['CIK'].nunique()} CIKs → {out_path.name}")
    if errors:
        print(f"Errors: {len(errors)} CIKs (first 5: {errors[:5]})")

    # Phase 3: TNIC comparison
    compare_tnic(df)


def compare_tnic(report_dates):
    """Compare TNIC 2005 firms against EDGAR using exact reportDate matching."""
    print(f"\n{'='*60}")
    print("TNIC comparison using reportDate (paginated API)")
    print(f"{'='*60}")

    # Load TNIC 2005 firms
    tnic = pd.read_csv(OUTPUT / "tnic_2005_firms.csv")
    tnic_gvkeys = set(tnic["gvkey"].unique())
    print(f"\nTNIC 2005 firms: {len(tnic_gvkeys)} gvkeys")

    # Load wciklink crosswalk (raw — all pairs, no year filter)
    wcik_raw = pd.read_csv(DATA / "wciklink_gvkey.csv", dtype=str)
    wcik_raw = wcik_raw[wcik_raw["gvkey"].notna() & (wcik_raw["gvkey"] != "")]
    wcik_raw["cik"] = wcik_raw["cik"].astype(int)
    wcik_raw["gvkey"] = wcik_raw["gvkey"].astype(float).astype(int)
    wcik_all = wcik_raw[["gvkey", "cik"]].drop_duplicates()
    gvkey_to_ciks = wcik_all.groupby("gvkey")["cik"].apply(set).to_dict()

    # Filter report_dates to FY2005
    rd = report_dates.copy()
    rd["reportYear"] = pd.to_datetime(rd["reportDate"], errors="coerce").dt.year
    fy2005 = rd[rd["reportYear"] == 2005]
    edgar_fy2005_ciks = set(fy2005["CIK"].unique())
    print(f"EDGAR CIKs with reportDate in 2005: {len(edgar_fy2005_ciks)}")
    print(f"  Total FY2005 10-K filings: {len(fy2005)}")
    print(f"  Form types: {fy2005['form'].value_counts().to_dict()}")

    # Match TNIC gvkeys to EDGAR FY2005 CIKs via wciklink
    covered = set()
    no_crosswalk = set()
    uncovered = set()
    for gvk in tnic_gvkeys:
        ciks = gvkey_to_ciks.get(gvk)
        if ciks is None:
            no_crosswalk.add(gvk)
            continue
        if ciks & edgar_fy2005_ciks:
            covered.add(gvk)
        else:
            uncovered.add(gvk)

    total = len(tnic_gvkeys)
    print(f"\n=== Coverage Summary (Option A: SEC API with pagination) ===")
    print(f"TNIC 2005 gvkeys (total):      {total}")
    print(f"Matched to CIK via wciklink:   {total - len(no_crosswalk)}")
    print(f"No wciklink entry:             {len(no_crosswalk)}")
    print(f"Covered (CIK in EDGAR FY2005): {len(covered)} ({len(covered)/total*100:.1f}%)")
    print(f"Uncovered (CIK not in FY2005): {len(uncovered)}")

    print(f"\n=== Comparison with previous steps (all on {total} TNIC gvkeys) ===")
    print(f"A8 (wciklink raw, wide window):  5,112/5,122 = 99.8%")
    print(f"A9 Option A (reportDate match):  {len(covered)}/{total} = {len(covered)/total*100:.1f}%")

    # Save summary
    summary = pd.DataFrame([
        {"Step": "A8 (wciklink raw, wide window)", "Covered": 5112, "Total": 5122, "Rate": "99.8%"},
        {"Step": f"A9 Option A (paginated API)", "Covered": len(covered), "Total": total,
         "Rate": f"{len(covered)/total*100:.1f}%"},
    ])
    summary.to_csv(OUTPUT / "coverage_summary_option_a.csv", index=False)
    print(f"\nSaved to coverage_summary_option_a.csv")


if __name__ == "__main__":
    main()
