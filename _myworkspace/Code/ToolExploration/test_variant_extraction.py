"""
Test extraction on filing type variants (10-K/A, 10-Q/A, 10KSB) across eras.
Downloads 3 filings per variant per era and runs extraction to verify output.
"""
# %%
import io, itertools, json, os, re, sys, time, zipfile
from pathlib import Path

import pandas as pd
import requests

# Setup paths
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

USER_AGENT = "Academic Research marcozhang1231@gmail.com"
BASE = "https://www.sec.gov/Archives/edgar/full-index"
TEST_DIR = REPO_ROOT / "datasets" / "TEST_VARIANTS"
TEST_DIR.mkdir(parents=True, exist_ok=True)

N_PER_COMBO = 3  # filings per variant × era combo

# Define test matrix
VARIANTS = ["10-K/A", "10-Q/A", "10KSB"]
ERAS = {
    "early": (1998, 2),   # old .txt format
    "mid":   (2005, 2),   # .htm transition, 10KSB peak
    "modern": (2020, 2),  # current format
}

# %% Step 1: Fetch EDGAR indices and find test filings
def fetch_index(year, qtr):
    url = f"{BASE}/{year}/QTR{qtr}/master.zip"
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)).open("master.idx") as f:
        lines = [line.decode("latin-1") for line in itertools.islice(f, 11, None)]
    rows = [line.strip().split("|") for line in lines if "|" in line]
    return pd.DataFrame(rows, columns=["CIK", "Company", "Type", "Date", "Filename"])

print("=== Fetching EDGAR indices ===")
test_filings = []
for era_name, (year, qtr) in ERAS.items():
    print(f"  {era_name}: {year} Q{qtr}...")
    df = fetch_index(year, qtr)
    time.sleep(0.3)

    for variant in VARIANTS:
        # 10KSB only exists pre-2009
        if variant == "10KSB" and era_name == "modern":
            print(f"    {variant} × {era_name}: skipped (discontinued 2009)")
            continue

        matches = df[df.Type == variant]
        if len(matches) == 0:
            print(f"    {variant} × {era_name}: NOT FOUND in index")
            continue

        sample = matches.head(N_PER_COMBO)
        print(f"    {variant} × {era_name}: {len(sample)} filings selected (of {len(matches)} available)")

        for _, row in sample.iterrows():
            test_filings.append({
                "era": era_name,
                "variant": variant,
                "CIK": row.CIK,
                "Company": row.Company,
                "Type": row.Type,
                "Date": row.Date,
                "Filename": row.Filename,
            })

print(f"\nTotal test filings: {len(test_filings)}")

# %% Step 2: Download raw filings
print("\n=== Downloading raw filings ===")
for filing in test_filings:
    # Build URL and local path
    filing_url = f"https://www.sec.gov/Archives/{filing['Filename']}"
    # Filename convention: CIK_Type_Year_accession.ext
    safe_type = filing["Type"].replace("/", "").replace("-", "")
    accession = filing["Filename"].split("/")[-1].replace(".txt", "")
    year = filing["Date"][:4]
    local_name = f"{filing['CIK']}_{safe_type}_{year}_{accession}"
    ext = ".txt"  # SEC index files always point to .txt

    # Save under Type subfolder (e.g., TEST_VARIANTS/10-K/A/filename.txt)
    # This matches extract_items.py's expected path: raw_files_folder/Type/filename
    variant_dir = TEST_DIR / filing["Type"]
    variant_dir.mkdir(parents=True, exist_ok=True)
    local_path = variant_dir / f"{local_name}{ext}"
    filing["local_path"] = str(local_path)
    filing["filename"] = f"{local_name}{ext}"

    if local_path.exists():
        print(f"  [skip] {local_name}")
        continue

    time.sleep(0.2)
    r = requests.get(filing_url, headers={"User-Agent": USER_AGENT})
    if r.status_code == 200:
        local_path.write_bytes(r.content)
        print(f"  [ok]   {local_name} ({len(r.content)//1024}KB)")
    else:
        print(f"  [FAIL] {local_name} (HTTP {r.status_code})")
        filing["local_path"] = None

# %% Step 3: Crawl HTML index pages to get filing details (Period of Report, etc.)
print("\n=== Crawling filing index pages for metadata ===")
for filing in test_filings:
    if filing.get("local_path") is None:
        continue
    # Build index URL from filename
    idx_url = f"https://www.sec.gov/Archives/{filing['Filename'].replace('.txt', '-index.html')}"
    time.sleep(0.2)
    try:
        r = requests.get(idx_url, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            # Extract Period of Report
            por_match = re.search(r'Period of Report.*?(\d{4}-\d{2}-\d{2})', r.text)
            filing["Period of Report"] = por_match.group(1) if por_match else filing["Date"]
            # Extract htm_file_link (the actual filing document)
            htm_match = re.search(r'href="(/Archives/edgar/data/\d+/\d+/[^"]+\.htm)"', r.text)
            filing["htm_file_link"] = f"https://www.sec.gov{htm_match.group(1)}" if htm_match else None
        else:
            filing["Period of Report"] = filing["Date"]
            filing["htm_file_link"] = None
    except Exception as e:
        print(f"  [warn] Could not crawl index for {filing['filename']}: {e}")
        filing["Period of Report"] = filing["Date"]
        filing["htm_file_link"] = None

# %% Step 4: Create metadata CSV and run extraction
print("\n=== Running extraction ===")

# Build metadata CSV
metadata_rows = []
for filing in test_filings:
    if filing.get("local_path") is None:
        continue
    metadata_rows.append({
        "CIK": filing["CIK"],
        "Company": filing["Company"],
        "Type": filing["Type"],
        "Date": filing["Date"],
        "complete_text_file_link": "",
        "html_index": "",
        "Filing Date": filing["Date"],
        "Period of Report": filing.get("Period of Report", filing["Date"]),
        "SIC": "",
        "htm_file_link": filing.get("htm_file_link", ""),
        "State of Inc": "",
        "State location": "",
        "Fiscal Year End": "",
        "filename": filing["filename"],
    })

metadata_df = pd.DataFrame(metadata_rows)
metadata_path = TEST_DIR / "TEST_METADATA.csv"
metadata_df.to_csv(metadata_path, index=False)
print(f"Metadata saved: {len(metadata_df)} rows")

# Run extraction using the edgar-crawler ExtractItems class
from extract_items import ExtractItems

results = []
for _, row in metadata_df.iterrows():
    raw_path = TEST_DIR / row["Type"] / row["filename"]

    if not raw_path.exists():
        results.append({"filename": row["filename"], "type": row["Type"], "status": "FILE_MISSING"})
        continue

    try:
        # ExtractItems expects raw_files_folder such that files are at raw_files_folder/Type/filename
        extractor = ExtractItems(
            remove_tables=False,
            items_to_extract=[],
            include_signature=False,
            raw_files_folder=str(TEST_DIR),
            extracted_files_folder=str(TEST_DIR / "EXTRACTED"),
            skip_extracted_filings=False,
        )

        filing_metadata = row.to_dict()
        extractor.determine_items_to_extract(filing_metadata)
        extraction = extractor.extract_items(filing_metadata)

        if extraction is None:
            results.append({"filename": row["filename"], "type": row["Type"], "status": "EMPTY"})
            continue

        # Count items with content
        item_keys = [k for k in extraction if k.startswith("item_") or k.startswith("part_")]
        items_with_content = {k: len(v) for k, v in extraction.items()
                             if (k.startswith("item_") or k.startswith("part_")) and v and len(v) > 50}

        results.append({
            "filename": row["filename"],
            "type": row["Type"],
            "date": row["Date"],
            "status": "OK" if items_with_content else "NO_ITEMS",
            "total_keys": len(item_keys),
            "keys_with_content": len(items_with_content),
            "content_lengths": items_with_content,
        })

        # Save extracted JSON
        out_dir = TEST_DIR / "EXTRACTED" / row["Type"]
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / row["filename"].replace(".txt", ".json").replace(".htm", ".json")
        with open(json_path, "w") as f:
            json.dump(extraction, f, indent=2)

    except Exception as e:
        results.append({"filename": row["filename"], "type": row["Type"], "status": f"ERROR: {e}"})

# %% Step 5: Report
print("\n" + "=" * 80)
print("VARIANT EXTRACTION TEST RESULTS")
print("=" * 80)

for filing_info, result in zip(test_filings, results):
    era = filing_info["era"]
    variant = result["type"]
    status = result["status"]
    print(f"\n  [{era:6s}] {variant:8s} | {result['filename'][:50]}")
    print(f"           Status: {status}")
    if status == "OK":
        print(f"           Items with content (>50 chars): {result['keys_with_content']}/{result['total_keys']}")
        top_items = sorted(result["content_lengths"].items(), key=lambda x: -x[1])[:5]
        for k, v in top_items:
            print(f"             {k}: {v:,} chars")

# Summary table
print("\n\n=== SUMMARY ===")
print(f"{'Variant':10s} {'Era':8s} {'OK':>4s} {'Empty':>6s} {'Error':>6s}")
for variant in VARIANTS:
    for era_name in ERAS:
        if variant == "10KSB" and era_name == "modern":
            continue
        era_results = [r for r, f in zip(results, test_filings)
                       if f["variant"] == variant and f["era"] == era_name]
        ok = sum(1 for r in era_results if r["status"] == "OK")
        empty = sum(1 for r in era_results if r["status"] in ["EMPTY", "NO_ITEMS"])
        error = sum(1 for r in era_results if r["status"].startswith("ERROR"))
        print(f"{variant:10s} {era_name:8s} {ok:4d} {empty:6d} {error:6d}")
