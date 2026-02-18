"""
Step A9 — Option B: Fetch CONFORMED PERIOD OF REPORT from filing SGML headers.

Each EDGAR filing has an SGML header at the start of its .txt file containing:
    CONFORMED PERIOD OF REPORT:    20051231

This script:
1. Loads the EDGAR 2005-2006 10-K index (31K filings with Filename paths)
2. For each filing, fetches the first ~4KB of the .txt file (header only)
3. Extracts CONFORMED PERIOD OF REPORT via regex
4. Saves to edgar_10k_report_dates_headers.csv
5. Re-does TNIC comparison using exact FY2005 reportDate matching

Advantage over Option A: gets reportDate for EVERY filing directly (no pagination),
and is keyed to specific filings (not aggregated at CIK level).

Usage: uv run python _myworkspace/Code/CoverageValidation/fetch_report_dates_headers.py
"""

import re, time
from pathlib import Path

import pandas as pd
import requests

WORKSPACE = Path(__file__).resolve().parents[2]  # _myworkspace/
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"
DATA = WORKSPACE / "Data" / "CoverageValidation"
OUTPUT.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Academic Research marcozhang1231@gmail.com"
HEADERS_HTTP = {"User-Agent": USER_AGENT}

PERIOD_RE = re.compile(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})")


def fetch_period_of_report(filename):
    """Fetch the CONFORMED PERIOD OF REPORT from a filing's SGML header.

    Uses Range header to fetch only the first 4KB (header is typically <2KB).
    """
    url = f"https://www.sec.gov/Archives/{filename}"
    try:
        r = requests.get(url, headers={**HEADERS_HTTP, "Range": "bytes=0-4095"}, timeout=20)
        if r.status_code in (200, 206):
            m = PERIOD_RE.search(r.text)
            if m:
                raw = m.group(1)  # e.g. "20051231"
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return None
    except Exception:
        return None


def main():
    print("Step A9 — Option B: CONFORMED PERIOD OF REPORT from filing headers")
    print("=" * 60)

    # Load EDGAR 2005-2006 index
    edgar_path = OUTPUT / "edgar_2005_2006_10k.csv"
    edgar = pd.read_csv(edgar_path)
    edgar["CIK"] = edgar["CIK"].astype(int)
    print(f"EDGAR 2005-2006 index: {len(edgar)} filings, {edgar['CIK'].nunique()} unique CIKs")

    # Resume support
    out_path = OUTPUT / "edgar_10k_report_dates_headers.csv"
    if out_path.exists():
        existing = pd.read_csv(out_path)
        done_filenames = set(existing["Filename"])
        print(f"Resuming: {len(done_filenames)} filings already fetched")
        results = existing.to_dict("records")
    else:
        done_filenames = set()
        results = []

    remaining = edgar[~edgar["Filename"].isin(done_filenames)]
    total = len(edgar)
    print(f"Filings to fetch: {len(remaining)} ({len(done_filenames)} done, {total} total)\n")

    errors = 0
    for i, (_, row) in enumerate(remaining.iterrows()):
        period = fetch_period_of_report(row["Filename"])
        time.sleep(0.15)

        results.append({
            "CIK": row["CIK"],
            "Company": row["Company"],
            "Type": row["Type"],
            "Date": row["Date"],
            "Filename": row["Filename"],
            "reportDate": period if period else "",
        })

        if period is None:
            errors += 1

        done_total = len(done_filenames) + i + 1
        if (i + 1) % 1000 == 0:
            pct = done_total / total * 100
            print(f"  {done_total}/{total} ({pct:.1f}%) — {errors} missing — saving checkpoint...")
            pd.DataFrame(results).to_csv(out_path, index=False)

    # Final save
    df = pd.DataFrame(results)
    df.to_csv(out_path, index=False)
    filled = df["reportDate"].ne("").sum()
    print(f"\nSaved {len(df)} filings → {out_path.name}")
    print(f"  reportDate found: {filled}/{len(df)} ({filled/len(df)*100:.1f}%)")
    print(f"  reportDate missing: {len(df) - filled}")

    # Phase 3: TNIC comparison
    compare_tnic(df)


def compare_tnic(df):
    """Compare TNIC 2005 firms against EDGAR using exact reportDate matching."""
    print(f"\n{'='*60}")
    print("TNIC comparison using reportDate (filing headers)")
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

    # Filter to FY2005 (reportDate year = 2005)
    df_with_date = df[df["reportDate"].ne("") & df["reportDate"].notna()].copy()
    df_with_date["reportYear"] = pd.to_datetime(df_with_date["reportDate"], errors="coerce").dt.year
    fy2005 = df_with_date[df_with_date["reportYear"] == 2005]
    edgar_fy2005_ciks = set(fy2005["CIK"].unique())
    print(f"EDGAR CIKs with reportDate in 2005: {len(edgar_fy2005_ciks)}")
    print(f"  Total FY2005 10-K filings: {len(fy2005)}")
    print(f"  Form types: {fy2005['Type'].value_counts().to_dict()}")

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
    print(f"\n=== Coverage Summary (Option B: filing headers) ===")
    print(f"TNIC 2005 gvkeys (total):      {total}")
    print(f"Matched to CIK via wciklink:   {total - len(no_crosswalk)}")
    print(f"No wciklink entry:             {len(no_crosswalk)}")
    print(f"Covered (CIK in EDGAR FY2005): {len(covered)} ({len(covered)/total*100:.1f}%)")
    print(f"Uncovered (CIK not in FY2005): {len(uncovered)}")

    print(f"\n=== Comparison with previous steps (all on {total} TNIC gvkeys) ===")
    print(f"A8 (wciklink raw, wide window):  5,112/5,122 = 99.8%")
    print(f"A9 Option B (header reportDate): {len(covered)}/{total} = {len(covered)/total*100:.1f}%")

    # Save summary
    summary = pd.DataFrame([
        {"Step": "A8 (wciklink raw, wide window)", "Covered": 5112, "Total": 5122, "Rate": "99.8%"},
        {"Step": f"A9 Option B (filing headers)", "Covered": len(covered), "Total": total,
         "Rate": f"{len(covered)/total*100:.1f}%"},
    ])
    summary.to_csv(OUTPUT / "coverage_summary_option_b.csv", index=False)
    print(f"\nSaved to coverage_summary_option_b.csv")


if __name__ == "__main__":
    main()
