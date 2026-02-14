"""
B2 Verification: filing_types exact matching behavior
Downloads one real EDGAR quarterly index, shows what .isin(["10-K"]) misses,
and fetches one filing per variant to confirm they're accessible.
"""
# %%
import io, itertools, zipfile, time
import pandas as pd
import requests

USER_AGENT = "Academic Research marcozhang1231@gmail.com"
BASE = "https://www.sec.gov/Archives/edgar/full-index"

# Check two quarters: Q2 2005 for 10-KSB era, Q1 2005 as fallback
QUARTERS = [(2005, 2), (2005, 1)]

def fetch_index(year, qtr):
    url = f"{BASE}/{year}/QTR{qtr}/master.zip"
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)).open("master.idx") as f:
        lines = [line.decode("latin-1") for line in itertools.islice(f, 11, None)]
    rows = [line.strip().split("|") for line in lines if "|" in line]
    return pd.DataFrame(rows, columns=["CIK", "Company", "Type", "Date", "Filename"])

# Combine both quarters
dfs = []
for year, qtr in QUARTERS:
    print(f"Fetching EDGAR full index for {year} Q{qtr}...")
    dfs.append(fetch_index(year, qtr))
    time.sleep(0.2)
df = pd.concat(dfs, ignore_index=True)

print(f"Total filings in index: {len(df)}")

# %% Step 2: Show all 10-K-like types in the index
# Note: EDGAR uses "10KSB" (no hyphen), not "10-KSB" — must match both patterns
mask_10k = df.Type.str.contains("10-K|10K", na=False)
print(f"\nAll filing types containing '10-K' or '10K':")
print(df[mask_10k].Type.value_counts().to_string())

# %% Step 3: Show what .isin(["10-K"]) keeps vs misses
naive_filter = df[mask_10k].copy()
naive_filter["kept_by_isin"] = naive_filter.Type.isin(["10-K"])

print(f"\n=== .isin(['10-K']) filtering ===")
for ftype, group in naive_filter.groupby("Type"):
    kept = group.kept_by_isin.sum()
    total = len(group)
    status = "KEPT" if kept == total else "MISSED"
    print(f"  {ftype:15s}: {total:5d} filings → {status}")

# %% Step 4: Fetch one filing per variant to confirm accessibility
variants = naive_filter.Type.unique()
print(f"\n=== Fetching one filing per variant ===")
for variant in sorted(variants):
    row = naive_filter[naive_filter.Type == variant].iloc[0]
    filing_url = f"https://www.sec.gov/Archives/{row.Filename}"
    print(f"\n  {variant}:")
    print(f"    Company: {row.Company}")
    print(f"    URL: {filing_url}")

    time.sleep(0.2)  # SEC rate limit
    resp = requests.head(filing_url, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
    print(f"    Status: {resp.status_code} ({'accessible' if resp.status_code == 200 else 'FAILED'})")

print("\nDone. Variants exist in EDGAR and are fetchable — .isin() requires explicit listing.")
