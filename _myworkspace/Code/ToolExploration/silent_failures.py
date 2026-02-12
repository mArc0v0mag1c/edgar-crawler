"""
Silent failures & filing type checks (B2, B4, B7).
- B2: Missing data / silent failure patterns in metadata
- B4: 10-KSB presence in test data and EDGAR
- B7: Amendments and transition reports in test data
"""
import pandas as pd
from pathlib import Path

FIXTURES = Path("/Users/marcozhang_1/vscodeproject/edgar-crawler/tests/fixtures")
metadata = pd.read_csv(FIXTURES / "FILINGS_METADATA_TEST.csv", dtype=str)

# ══════════════════════════════════════════════════
# B2: Missing Data / Silent Failures
# ══════════════════════════════════════════════════
print("=" * 70)
print("B2: MISSING DATA / SILENT FAILURES")
print("=" * 70)

# Check for empty Period of Report
empty_por = metadata[metadata["Period of Report"].isna() | (metadata["Period of Report"] == "")]
print(f"\n1. Empty 'Period of Report': {len(empty_por)} out of {len(metadata)} rows")
if len(empty_por) > 0:
    print("   These filings would be SILENTLY SKIPPED during download:")
    for _, r in empty_por.iterrows():
        print(f"   {r['filename']} ({r['Type']}, {r['Date']})")

# Check for missing htm_file_link (falls back to .txt)
no_htm = metadata[metadata["htm_file_link"].isna() | (metadata["htm_file_link"] == "")]
txt_files = metadata[metadata["filename"].str.endswith(".txt")]
htm_files = metadata[metadata["filename"].str.endswith(".htm")]
print(f"\n2. File format distribution:")
print(f"   .txt files: {len(txt_files)} ({len(txt_files)/len(metadata)*100:.1f}%)")
print(f"   .htm files: {len(htm_files)} ({len(htm_files)/len(metadata)*100:.1f}%)")
print(f"   Missing htm_file_link: {len(no_htm)} ({len(no_htm)/len(metadata)*100:.1f}%)")

# Check for missing SIC codes
no_sic = metadata[metadata["SIC"].isna() | (metadata["SIC"] == "")]
print(f"\n3. Missing SIC code: {len(no_sic)} ({len(no_sic)/len(metadata)*100:.1f}%)")

# Check for missing State of Inc
no_state = metadata[metadata["State of Inc"].isna() | (metadata["State of Inc"] == "")]
print(f"   Missing State of Inc: {len(no_state)} ({len(no_state)/len(metadata)*100:.1f}%)")

# Filing types exact matching demonstration
print(f"\n4. Exact filing_types matching:")
all_types = metadata["Type"].value_counts()
print("   All filing types in test metadata:")
for t, c in all_types.items():
    print(f"     '{t}': {c} filings")

# ══════════════════════════════════════════════════
# B4: Small Business Filer Bias (10-KSB)
# ══════════════════════════════════════════════════
print("\n" + "=" * 70)
print("B4: SMALL BUSINESS FILER BIAS (10-KSB)")
print("=" * 70)

ksb = metadata[metadata["Type"].str.contains("KSB|QSB", na=False)]
print(f"\n10-KSB/10-QSB in test metadata: {len(ksb)}")
if len(ksb) > 0:
    print(ksb[["filename", "Type", "Date", "Company"]].to_string())
else:
    print("   None found — small business filings are NOT tested by the repo")

# Check extract_items.py for 10-KSB handling
import re
extract_code = open("/Users/marcozhang_1/vscodeproject/edgar-crawler/extract_items.py").read()
ksb_refs = [line.strip() for line in extract_code.split("\n") if "KSB" in line or "ksb" in line.lower()]
print(f"\nReferences to 'KSB' in extract_items.py: {len(ksb_refs)}")
for ref in ksb_refs:
    print(f"   {ref}")

# ══════════════════════════════════════════════════
# B7: Amendments & Transition Reports
# ══════════════════════════════════════════════════
print("\n" + "=" * 70)
print("B7: AMENDMENTS & TRANSITION REPORTS")
print("=" * 70)

amendments = metadata[metadata["Type"].str.contains("/A", na=False)]
transitions = metadata[metadata["Type"].str.contains("KT|QT", na=False)]
nt_filings = metadata[metadata["Type"].str.startswith("NT", na=False)]

print(f"\nIn test metadata:")
print(f"  Amendments (10-K/A, 10-Q/A, 8-K/A): {len(amendments)}")
print(f"  Transition reports (10-KT, 10-QT): {len(transitions)}")
print(f"  Late filing notifications (NT): {len(nt_filings)}")

if len(amendments) > 0:
    print("\n  Amendment details:")
    for _, r in amendments.iterrows():
        print(f"    {r['filename']} ({r['Type']}, {r['Date']}, {r['Company']})")

# Check download_filings.py for exact matching
dl_code = open("/Users/marcozhang_1/vscodeproject/edgar-crawler/download_filings.py").read()
isin_lines = [line.strip() for line in dl_code.split("\n") if "isin" in line.lower() and "filing" in line.lower()]
print(f"\nfiling_types exact matching in download_filings.py:")
for line in isin_lines:
    print(f"   {line}")

print("\n--- Summary ---")
print("The download config's 'filing_types' uses pandas .isin() for exact matching.")
print("Specifying '10-K' will NOT capture: 10-K/A, 10-KSB, 10-KT, NT 10-K")
print("Specifying '10-Q' will NOT capture: 10-Q/A, 10-QSB, 10-QT, NT 10-Q")
print("Must explicitly include variant types if needed.")
