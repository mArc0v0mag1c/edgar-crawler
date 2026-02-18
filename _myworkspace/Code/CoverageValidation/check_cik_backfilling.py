"""
CIK backfilling test: Does any Compustat table preserve historical CIKs?

Part 1: Compare comp.company vs comp.funda vs comp_na_daily_all.fundq
        for 20 TNIC "missing" firms. Tests Professor Ma's suggestion that
        her fundq extract might help close the ~5% crosswalk gap.

Part 2: Compare all Compustat sources against WRDS SEC Analytics sample
        (secsamp_all.wciklink_gvkey). The wciklink table uses 4 sources
        to construct historical CIK-gvkey links. If Compustat disagrees
        with wciklink, that proves Compustat backfills.
"""
import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

WORKSPACE = Path(__file__).resolve().parents[2]
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"
load_dotenv(WORKSPACE.parent / ".env")

conn = psycopg2.connect(
    host="wrds-pgdata.wharton.upenn.edu",
    port=9737,
    dbname="wrds",
    user=os.getenv("WRDS_USERNAME"),
    password=os.getenv("WRDS_PASSWORD"),
    sslmode="require",
)

# ============================================================
# Part 1: fundq vs funda vs company for TNIC missing firms
# ============================================================
print("=" * 60)
print("Part 1: Compustat fundq vs funda vs company")
print("Do any Compustat tables store different CIKs for the same gvkey?")
print("=" * 60)

# Load existing artifacts to identify missing gvkeys
tnic_2005 = pd.read_csv(OUTPUT / "tnic_2005_firms.csv")
crosswalk = pd.read_csv(OUTPUT / "gvkey_cik_crosswalk.csv")
edgar = pd.read_csv(OUTPUT / "edgar_2005_10k.csv")

# Identify TNIC firms missing from EDGAR (calendar year)
tnic_with_cik = tnic_2005.merge(crosswalk, on="gvkey", how="left")
tnic_matched = tnic_with_cik[tnic_with_cik["cik"].notna()]
tnic_ciks = set(tnic_matched["cik"].astype(int).unique())
edgar_ciks = set(edgar["CIK"].astype(int).unique())
missing_ciks = tnic_ciks - edgar_ciks

# Map back to gvkeys, zero-pad to Compustat format
cik_to_gvkey = tnic_matched.set_index("cik")["gvkey"].to_dict()
missing_gvkeys = [str(cik_to_gvkey[c]).zfill(6) for c in missing_ciks if c in cik_to_gvkey]
sample_gvkeys = sorted(missing_gvkeys)[:20]

print(f"\nTNIC CIKs missing from EDGAR 2005: {len(missing_ciks)}")
print(f"Testing {len(sample_gvkeys)} sample gvkeys: {sample_gvkeys[:5]}...")

gvkey_list = ",".join(f"'{g}'" for g in sample_gvkeys)

company_p1 = pd.read_sql(f"""
    SELECT gvkey, cik FROM comp.company WHERE gvkey IN ({gvkey_list}) ORDER BY gvkey
""", conn)
funda_p1 = pd.read_sql(f"""
    SELECT DISTINCT gvkey, cik FROM comp.funda
    WHERE gvkey IN ({gvkey_list})
      AND indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'
    ORDER BY gvkey
""", conn)
fundq_p1 = pd.read_sql(f"""
    SELECT DISTINCT gvkey, cik FROM comp_na_daily_all.fundq
    WHERE gvkey IN ({gvkey_list})
      AND indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'
    ORDER BY gvkey
""", conn)

# Compare
print(f"\n{'gvkey':<10} {'company':<15} {'funda':<15} {'fundq':<15} {'differ?'}")
print("-" * 65)
differ_count = 0
for gvk in sample_gvkeys:
    co = sorted(company_p1[company_p1["gvkey"] == gvk]["cik"].unique().tolist())
    fu = sorted(funda_p1[funda_p1["gvkey"] == gvk]["cik"].unique().tolist())
    fq = sorted(fundq_p1[fundq_p1["gvkey"] == gvk]["cik"].unique().tolist())
    co_s = co[0] if co else "N/A"
    fu_s = fu[0] if fu else "N/A"
    fq_s = fq[0] if fq else "N/A"
    diff = "YES" if len({str(co_s), str(fu_s), str(fq_s)} - {"N/A"}) > 1 else ""
    if diff:
        differ_count += 1
    print(f"{gvk:<10} {str(co_s):<15} {str(fu_s):<15} {str(fq_s):<15} {diff}")

print(f"\nDifferences: {differ_count}/{len(sample_gvkeys)}")
if differ_count == 0:
    print("RESULT: All three Compustat tables return identical CIKs.")
    print("        fundq will NOT help close the crosswalk gap.")
else:
    print("RESULT: Some CIKs differ — investigate further.")

# ============================================================
# Part 2: WRDS SEC Analytics sample vs Compustat
# ============================================================
print(f"\n{'=' * 60}")
print("Part 2: WRDS SEC Analytics (wciklink) vs Compustat")
print("Does the SEC Analytics crosswalk have CIKs that Compustat doesn't?")
print("=" * 60)

# Fetch wciklink sample
wcik = pd.read_sql("""
    SELECT gvkey, cik, source, sec_company_name, link_company_name,
           sec_start_date, sec_end_date, link_start_date, link_end_date
    FROM secsamp_all.wciklink_gvkey
    ORDER BY gvkey, cik
""", conn)
print(f"\nwciklink sample: {len(wcik)} rows, {wcik['gvkey'].nunique()} gvkeys, {wcik['cik'].nunique()} CIKs")

# Get all unique gvkeys from wciklink
wcik_gvkeys = wcik["gvkey"].unique().tolist()
gvkey_list_2 = ",".join(f"'{g}'" for g in wcik_gvkeys)

# Query Compustat for those same gvkeys
company_p2 = pd.read_sql(f"""
    SELECT gvkey, cik FROM comp.company WHERE gvkey IN ({gvkey_list_2}) ORDER BY gvkey
""", conn)
funda_p2 = pd.read_sql(f"""
    SELECT DISTINCT gvkey, cik FROM comp.funda
    WHERE gvkey IN ({gvkey_list_2})
      AND indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'
    ORDER BY gvkey
""", conn)
fundq_p2 = pd.read_sql(f"""
    SELECT DISTINCT gvkey, cik FROM comp_na_daily_all.fundq
    WHERE gvkey IN ({gvkey_list_2})
      AND indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'
    ORDER BY gvkey
""", conn)

conn.close()

# For each gvkey: compare wciklink CIK(s) vs Compustat CIK(s)
print(f"\n{'gvkey':<10} {'wciklink':<15} {'company':<15} {'funda':<15} {'fundq':<15} {'mismatch?'}")
print("-" * 80)

mismatches = []
for gvk in wcik_gvkeys:
    wc = set(wcik[wcik["gvkey"] == gvk]["cik"].unique())
    co = set(company_p2[company_p2["gvkey"] == gvk]["cik"].unique())
    fu = set(funda_p2[funda_p2["gvkey"] == gvk]["cik"].unique())
    fq = set(fundq_p2[fundq_p2["gvkey"] == gvk]["cik"].unique())

    # Mismatch = wciklink CIK differs from any Compustat CIK
    all_comp = co | fu | fq
    mismatch = ""
    if wc != all_comp and len(wc) > 0 and len(all_comp) > 0:
        mismatch = "MISMATCH"
        mismatches.append(gvk)
    elif len(all_comp) == 0:
        mismatch = "no comp"
        mismatches.append(gvk)

    wc_s = ", ".join(str(c) for c in sorted(wc)) if wc else "N/A"
    co_s = ", ".join(str(c) for c in sorted(co)) if co else "N/A"
    fu_s = ", ".join(str(c) for c in sorted(fu)) if fu else "N/A"
    fq_s = ", ".join(str(c) for c in sorted(fq)) if fq else "N/A"

    if mismatch:
        print(f"{gvk:<10} {wc_s:<15} {co_s:<15} {fu_s:<15} {fq_s:<15} {mismatch}")

print(f"\nMismatches: {len(mismatches)}/{len(wcik_gvkeys)} gvkeys")

# Detail the mismatches
if mismatches:
    print(f"\n--- Mismatch details ---")
    for gvk in mismatches:
        wc_rows = wcik[wcik["gvkey"] == gvk][["cik", "source", "sec_company_name",
                                                "sec_start_date", "sec_end_date"]].drop_duplicates()
        co_cik = company_p2[company_p2["gvkey"] == gvk]["cik"].unique()
        print(f"\ngvkey {gvk}:")
        print(f"  Compustat CIK: {co_cik[0] if len(co_cik) else 'N/A'}")
        print(f"  wciklink records:")
        for _, row in wc_rows.iterrows():
            print(f"    CIK {row['cik']} | {row['source']} | {row['sec_company_name']} | {row['sec_start_date']} - {row['sec_end_date']}")

print(f"\n{'=' * 60}")
print("CONCLUSION")
print("=" * 60)
if differ_count == 0:
    print("Part 1: comp.company = comp.funda = comp_na_daily_all.fundq (all backfill)")
if mismatches:
    print(f"Part 2: {len(mismatches)} gvkeys where wciklink has different CIK than Compustat")
    print("        → Only WRDS SEC Analytics (WCIKLINK_GVKEY) preserves historical CIKs")
    print("        → All Compustat tables backfill the current CIK identically")
    print("        → Professor Ma's fundq file will NOT help close the crosswalk gap")
