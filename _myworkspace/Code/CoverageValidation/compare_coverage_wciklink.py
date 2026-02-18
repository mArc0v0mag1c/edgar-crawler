"""
Step A9: Re-do TNIC coverage comparison using WRDS wciklink_gvkey historical crosswalk.

Steps A3-A7 used Compustat's native CIK (comp.company / comp.funda), which only stores
current links. Hoberg-Phillips used WRDS WCIKLINK_GVKEY, which preserves historical
CIK-gvkey links from 4 sources. Professor Ma provided the full table.

This script replaces the Compustat crosswalk with wciklink and re-runs the comparison.

Usage: uv run python _myworkspace/Code/CoverageValidation/compare_coverage_wciklink.py
"""

from pathlib import Path
import pandas as pd

WORKSPACE = Path(__file__).resolve().parents[2]  # _myworkspace/
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"
DATA = WORKSPACE / "Data" / "CoverageValidation"

# ── Load inputs ──────────────────────────────────────────────────────────────

print("=== Step A9: Coverage comparison with wciklink crosswalk ===\n")

# 1. TNIC 2005 firms
tnic = pd.read_csv(OUTPUT / "tnic_2005_firms.csv")
tnic_gvkeys = set(tnic["gvkey"].unique())
print(f"TNIC 2005 firms: {len(tnic_gvkeys)} gvkeys")

# 2. EDGAR 10-K index (2005-2006, from A8 Phase 1)
edgar = pd.read_csv(OUTPUT / "edgar_2005_2006_10k.csv")
edgar["CIK"] = edgar["CIK"].astype(int)
edgar_ciks = set(edgar["CIK"].unique())
print(f"EDGAR 10-K CIKs (2005-2006): {len(edgar_ciks)}")

# 3. wciklink crosswalk — use RAW file (all CIK-gvkey pairs, no year filter)
# The year-expanded file backfills successor CIKs into historical years while
# excluding the correct historical CIK (e.g., Apache Corp gvkey 1678: original
# CIK 6769 has link_start=2007, so it's absent from year=2005 in the expanded
# file, while successor CIK 1841666 is backfilled to 1960). Using all pairs
# avoids this problem — if ANY CIK for a gvkey is in EDGAR, it's a match.
wciklink_raw = pd.read_csv(DATA / "wciklink_gvkey.csv", dtype=str)
wciklink_raw = wciklink_raw[wciklink_raw["gvkey"].notna() & (wciklink_raw["gvkey"] != "")]
wciklink_raw["cik"] = wciklink_raw["cik"].astype(int)
wciklink_raw["gvkey"] = wciklink_raw["gvkey"].astype(float).astype(int)

wcik_all = wciklink_raw[["gvkey", "cik"]].drop_duplicates()
print(f"wciklink (raw, all pairs): {len(wcik_all)} gvkey-CIK pairs")
print(f"  Unique gvkeys: {wcik_all['gvkey'].nunique()}")
print(f"  Unique CIKs: {wcik_all['cik'].nunique()}")

# 4. Old Compustat crosswalk (for comparison)
comp_crosswalk = pd.read_csv(OUTPUT / "gvkey_cik_crosswalk.csv")
comp_crosswalk["cik"] = comp_crosswalk["cik"].astype(int)
comp_crosswalk["gvkey"] = comp_crosswalk["gvkey"].astype(int)

# ── Map TNIC gvkeys → CIKs using wciklink (gvkey-level matching) ─────────────
# A gvkey may map to multiple CIKs in wciklink (historical changes).
# A gvkey is "covered" if ANY of its CIKs is found in EDGAR.

print(f"\n{'='*60}")
print("Mapping TNIC gvkeys to CIKs via wciklink (gvkey-level)")
print(f"{'='*60}")

# Build gvkey → set of CIKs lookup
gvkey_to_ciks = wcik_all.groupby("gvkey")["cik"].apply(set).to_dict()

# Classify each TNIC gvkey
covered_gvkeys = set()       # at least one CIK in EDGAR
uncovered_gvkeys = set()     # has CIK(s) but none in EDGAR
no_crosswalk_gvkeys = set()  # no wciklink entry at all

for gvk in tnic_gvkeys:
    ciks = gvkey_to_ciks.get(gvk)
    if ciks is None:
        no_crosswalk_gvkeys.add(gvk)
    elif ciks & edgar_ciks:
        covered_gvkeys.add(gvk)
    else:
        uncovered_gvkeys.add(gvk)

matched_gvkeys = covered_gvkeys | uncovered_gvkeys  # have at least one CIK

print(f"TNIC gvkeys:                   {len(tnic_gvkeys)}")
print(f"  → matched to CIK (wciklink): {len(matched_gvkeys)}")
print(f"  → no wciklink entry:         {len(no_crosswalk_gvkeys)}")
print(f"  → covered (any CIK in EDGAR):{len(covered_gvkeys)}")
print(f"  → uncovered (CIK not in EDGAR):{len(uncovered_gvkeys)}")

# Multi-CIK stats
multi_cik = {gvk: ciks for gvk, ciks in gvkey_to_ciks.items() if gvk in tnic_gvkeys and len(ciks) > 1}
print(f"\n  TNIC gvkeys with multiple CIKs: {len(multi_cik)}")
if multi_cik:
    print(f"  Example: gvkey {list(multi_cik.keys())[0]} → CIKs {multi_cik[list(multi_cik.keys())[0]]}")

# Compare match rate vs Compustat crosswalk
tnic_with_comp = tnic.merge(comp_crosswalk, on="gvkey", how="left")
comp_matched_gvkeys = set(tnic_with_comp[tnic_with_comp["cik"].notna()]["gvkey"].unique())
comp_covered_gvkeys = set(
    tnic_with_comp[tnic_with_comp["cik"].isin(edgar_ciks) & tnic_with_comp["cik"].notna()]["gvkey"].unique()
)
print(f"\n  Compustat: {len(comp_matched_gvkeys)} gvkeys matched, {len(comp_covered_gvkeys)} covered (Step A3/A5)")
print(f"  wciklink:  {len(matched_gvkeys)} gvkeys matched, {len(covered_gvkeys)} covered (Step A9)")

# ── Coverage comparison (gvkey-level) ────────────────────────────────────────

print(f"\n{'='*60}")
print("Coverage comparison: TNIC (wciklink) vs EDGAR (2005-2006)")
print(f"{'='*60}")

total_tnic = len(tnic_gvkeys)
n_covered = len(covered_gvkeys)
n_uncovered = len(uncovered_gvkeys)
n_no_xwalk = len(no_crosswalk_gvkeys)
n_missing = n_uncovered + n_no_xwalk

print(f"\nTNIC gvkeys (total):           {total_tnic}")
print(f"Covered (any CIK in EDGAR):    {n_covered} ({n_covered/total_tnic*100:.1f}%)")
print(f"Not covered:                   {n_missing} ({n_missing/total_tnic*100:.1f}%)")
print(f"  - CIK exists, not in EDGAR:  {n_uncovered}")
print(f"  - No wciklink entry at all:  {n_no_xwalk}")

# ── Compare against previous steps (all on 5,122 denominator) ────────────────

print(f"\n{'='*60}")
print(f"Comparison with previous crosswalks (denominator = {total_tnic})")
print(f"{'='*60}")
# Recompute old steps on the full TNIC universe (5,122 gvkeys)
# comp.company matched 4,992 gvkeys to CIKs; covered = those whose CIK was in EDGAR
print(f"Step A4 (comp.company, 2005 only):     4,624/{total_tnic} = {4624/total_tnic*100:.1f}%  (130 no crosswalk)")
print(f"Step A5 (comp.company, wide window):   4,761/{total_tnic} = {4761/total_tnic*100:.1f}%  (130 no crosswalk)")
print(f"Step A7 (comp.funda, wide window):     4,735/{total_tnic} = {4735/total_tnic*100:.1f}%  (156 no crosswalk)")
print(f"        (comp.fundq = same as funda, 0 CIK differences — check_cik_backfilling.py Part 1)")
print(f"Step A9 (wciklink, 2005-2006):         {n_covered}/{total_tnic} = {n_covered/total_tnic*100:.1f}%  ({n_no_xwalk} no crosswalk)")

# ── Analyze the remaining uncovered gvkeys ───────────────────────────────────

if uncovered_gvkeys:
    print(f"\n{'='*60}")
    print(f"Remaining {n_uncovered} uncovered gvkeys (have CIK, not in EDGAR)")
    print(f"{'='*60}")

    # Collect their CIKs and check EDGAR
    uncovered_ciks = set()
    for gvk in uncovered_gvkeys:
        uncovered_ciks |= gvkey_to_ciks[gvk]

    uncovered_in_edgar = edgar[edgar["CIK"].isin(uncovered_ciks)]
    with_filings = uncovered_in_edgar["CIK"].nunique()
    print(f"  Their wciklink CIKs: {len(uncovered_ciks)}")
    print(f"  CIKs with any EDGAR filings: {with_filings}")
    print(f"  CIKs with zero EDGAR filings: {len(uncovered_ciks) - with_filings}")

    if len(uncovered_in_edgar):
        print(f"\n  Filing types for these CIKs:")
        print(f"  {uncovered_in_edgar['Type'].value_counts().head(10).to_string()}")

# ── Recovery analysis: how many old missing firms did wciklink recover? ───────

print(f"\n{'='*60}")
print("Recovery analysis: old missing firms from Step A5")
print(f"{'='*60}")

# Old missing = TNIC gvkeys not covered by Compustat crosswalk + EDGAR wide window
old_missing_gvkeys = tnic_gvkeys - comp_covered_gvkeys

# Of those, how many does wciklink now cover?
recovered = [gvk for gvk in old_missing_gvkeys if gvk in covered_gvkeys]
still_missing_no_xwalk = [gvk for gvk in old_missing_gvkeys if gvk in no_crosswalk_gvkeys]
still_missing_no_edgar = [gvk for gvk in old_missing_gvkeys if gvk in uncovered_gvkeys]

print(f"Old missing gvkeys:              {len(old_missing_gvkeys)}")
print(f"  Recovered via wciklink:        {len(recovered)}")
print(f"  Still missing (no wciklink):   {len(still_missing_no_xwalk)}")
print(f"  Still missing (CIK not in EDGAR): {len(still_missing_no_edgar)}")

if recovered:
    print(f"\n  Sample recovered firms (gvkey → wciklink CIK):")
    for gvk in sorted(recovered)[:15]:
        matched_cik = (gvkey_to_ciks[gvk] & edgar_ciks).pop()
        print(f"    gvkey {gvk:>6d} → CIK {matched_cik}")

# ── Save outputs ─────────────────────────────────────────────────────────────

summary = pd.DataFrame({
    "Metric": [
        "TNIC gvkeys (total)",
        "Covered (any CIK in EDGAR)",
        "Uncovered (CIK not in EDGAR)",
        "No wciklink entry",
        "Coverage rate",
    ],
    "Value": [
        total_tnic,
        n_covered,
        n_uncovered,
        n_no_xwalk,
        f"{n_covered/total_tnic*100:.1f}%",
    ],
})
summary.to_csv(OUTPUT / "coverage_summary_wciklink.csv", index=False)

if recovered:
    recovered_df = pd.DataFrame({"gvkey": recovered})
    recovered_df["wciklink_cik"] = recovered_df["gvkey"].apply(
        lambda gvk: (gvkey_to_ciks[gvk] & edgar_ciks).pop()
    )
    recovered_df.to_csv(OUTPUT / "wciklink_recovered_firms.csv", index=False)

print(f"\nSaved to {OUTPUT}/")
print(f"  coverage_summary_wciklink.csv")
if recovered:
    print(f"  wciklink_recovered_firms.csv ({len(recovered)} firms)")
