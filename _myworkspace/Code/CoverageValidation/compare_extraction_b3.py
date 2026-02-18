"""
Step B3: Extraction Diff — run H-P and edgar-crawler parsers on the same 10-K files
and compare the extracted Item 1 text.

Uses the 62 raw 10-K test fixtures (tests/fixtures/RAW_FILINGS/10-K.zip).
"""

import codecs
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

# ── Path setup ──
REPO_ROOT = Path(__file__).resolve().parents[3]  # Code/CoverageValidation → _myworkspace → repo
WORKSPACE = REPO_ROOT / "_myworkspace"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
OUTPUT = WORKSPACE / "Output" / "CoverageValidation"

# Add repo root to sys.path so we can import extract_items
sys.path.insert(0, str(REPO_ROOT))

from extract_items import ExtractItems  # noqa: E402

# ═══════════════════════════════════════════════════════════════════
# H-P Extraction (standalone, exact replication of Notebook 2 logic)
# ═══════════════════════════════════════════════════════════════════

def hp_extract_item1(filepath):
    """
    Hoberg-Phillips Item 1 extraction (exact logic from Notebook 2).

    Steps:
    1. Read file, replace all newlines with space (flatten to single line)
    2. Strip HTML if present (BeautifulSoup html.parser)
    3. 4-pattern regex cascade (including ^Z bug in patterns 2/3/4)
    4. Longest match (disambiguate ToC vs body)
    5. Clean up (remove "table of contents", collapse whitespace)
    6. Filter: skip if < 2KB
    """
    with codecs.open(str(filepath), "r", encoding="utf8", errors="replace") as f:
        ftext = f.read().replace("\n", " ")

    if "<html>" in ftext.lower():
        ftext = BeautifulSoup(ftext, "html.parser").get_text()

    # Step 1: Greedy check — does any "item 1 ... item 1a" region exist?
    section = re.findall(
        r"item[^a-zA-Z\n]*1.*item[^a-zA-Z\n]*1a",
        ftext, re.IGNORECASE | re.DOTALL,
    )

    if section:
        # Narrow with reluctant + period
        narrow = re.findall(
            r"item[^a-zA-Z\n]*1\..*?item[^a-zA-Z\n]*1a",
            ftext, re.IGNORECASE | re.DOTALL,
        )
        if not narrow:
            # Try item 1. → item 1b (note: ^Z bug preserved)
            narrow = re.findall(
                r"item[^a-zA-Z\n]*1\..*?item[^a-zA^Z\n]*1b",
                ftext, re.IGNORECASE | re.DOTALL,
            )
        section = narrow if narrow else section
    else:
        # No greedy match → try lenient (no period)
        section = re.findall(
            r"item[^a-zA-Z\n]*1.*?item[^a-zA^Z\n]*1a",
            ftext, re.IGNORECASE | re.DOTALL,
        )
        if not section:
            section = re.findall(
                r"item[^a-zA-Z\n]*1.*?item[^a-zA^Z\n]*1b",
                ftext, re.IGNORECASE | re.DOTALL,
            )

    if not section:
        return None

    result = max(section, key=len)
    result = re.sub(r"table of contents", " ", result, flags=re.IGNORECASE)
    result = result.strip()
    result = re.sub(r"\s+", " ", result).strip()

    # H-P's size filter: skip if < 2KB
    if len(result.encode("utf-8")) <= 2000:
        return None

    return result


# ═══════════════════════════════════════════════════════════════════
# Comparison utilities
# ═══════════════════════════════════════════════════════════════════

def tokenize(text):
    """Simple word tokenizer for Jaccard similarity."""
    if not text:
        return set()
    return set(re.findall(r"\w+", text.lower()))


def jaccard(set_a, set_b):
    """Word-level Jaccard similarity."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def categorize(ec_text, hp_text, j_sim):
    """Categorize the comparison result."""
    ec_empty = not ec_text or ec_text.strip() == ""
    hp_empty = not hp_text or hp_text.strip() == ""

    if ec_empty and hp_empty:
        return "BOTH_EMPTY"
    if ec_empty and not hp_empty:
        return "HP_ONLY"
    if not ec_empty and hp_empty:
        return "EC_ONLY"
    if j_sim >= 0.95:
        return "MATCH"
    if j_sim >= 0.70:
        return "BOUNDARY_DIFF"
    return "MAJOR_DIFF"


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    # ── Phase 1: Setup ──
    print("=" * 70)
    print("Step B3: Extraction Diff — H-P vs edgar-crawler on 10-K test fixtures")
    print("=" * 70)

    # Extract raw fixtures to temp dir
    tmpdir = tempfile.mkdtemp(prefix="b3_")
    raw_dir = os.path.join(tmpdir, "RAW_FILINGS")
    ext_dir = os.path.join(tmpdir, "EXTRACTED_FILINGS")
    os.makedirs(ext_dir, exist_ok=True)

    print(f"\nExtracting test fixtures to {tmpdir}...")
    with zipfile.ZipFile(FIXTURES / "RAW_FILINGS" / "10-K.zip") as zf:
        zf.extractall(raw_dir)

    # Load metadata
    meta = pd.read_csv(FIXTURES / "FILINGS_METADATA_TEST.csv", dtype=str)
    meta_10k = meta[meta["Type"] == "10-K"].reset_index(drop=True)
    print(f"Loaded {len(meta_10k)} 10-K filings from test metadata")

    # Verify raw files exist
    available = []
    for _, row in meta_10k.iterrows():
        raw_path = os.path.join(raw_dir, row["Type"], row["filename"])
        if os.path.exists(raw_path):
            available.append(row)
    available = pd.DataFrame(available).reset_index(drop=True)
    print(f"Raw files found: {len(available)} / {len(meta_10k)}")

    # Create edgar-crawler extractor
    extractor = ExtractItems(
        remove_tables=True,
        items_to_extract=["1"],
        include_signature=False,
        raw_files_folder=raw_dir,
        extracted_files_folder=ext_dir,
        skip_extracted_filings=False,
    )

    # ── Phase 2: Run both extractors ──
    print("\nRunning both extractors on each filing...\n")

    results = []
    for idx, row in available.iterrows():
        filename = row["filename"]
        raw_path = os.path.join(raw_dir, row["Type"], filename)

        # edgar-crawler extraction
        extractor.determine_items_to_extract(row)
        try:
            ec_json = extractor.extract_items(row)
            ec_item1 = ec_json.get("item_1", "") if ec_json else ""
        except Exception as e:
            ec_item1 = ""
            print(f"  EC ERROR on {filename}: {e}")

        # H-P extraction
        try:
            hp_item1 = hp_extract_item1(raw_path) or ""
        except Exception as e:
            hp_item1 = ""
            print(f"  HP ERROR on {filename}: {e}")

        # Compare
        ec_words = tokenize(ec_item1)
        hp_words = tokenize(hp_item1)
        j_sim = jaccard(ec_words, hp_words)
        cat = categorize(ec_item1, hp_item1, j_sim)

        results.append({
            "filename": filename,
            "cik": row["CIK"],
            "company": row["Company"],
            "period_of_report": row.get("Period of Report", ""),
            "ec_len": len(ec_item1),
            "hp_len": len(hp_item1),
            "ec_words": len(ec_words),
            "hp_words": len(hp_words),
            "jaccard": round(j_sim, 4),
            "category": cat,
            "ec_start": ec_item1[:80].replace("\n", "\\n") if ec_item1 else "",
            "hp_start": hp_item1[:80] if hp_item1 else "",
            "ec_end": ec_item1[-80:].replace("\n", "\\n") if ec_item1 else "",
            "hp_end": hp_item1[-80:] if hp_item1 else "",
        })

        # Progress
        status = f"J={j_sim:.2f}" if cat not in ("BOTH_EMPTY", "HP_ONLY", "EC_ONLY") else cat
        print(f"  [{idx+1:2d}/{len(available)}] {cat:<14} {status:<10} "
              f"EC={len(ec_item1):>7,} HP={len(hp_item1):>7,}  {filename[:50]}")

    # ── Phase 3: Summary ──
    df = pd.DataFrame(results)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Category counts
    cat_counts = df["category"].value_counts()
    total = len(df)
    print(f"\n{'Category':<16} {'Count':>5} {'%':>7}")
    print("-" * 30)
    for cat in ["MATCH", "BOUNDARY_DIFF", "MAJOR_DIFF", "EC_ONLY", "HP_ONLY", "BOTH_EMPTY"]:
        c = cat_counts.get(cat, 0)
        print(f"{cat:<16} {c:>5} {c/total*100:>6.1f}%")
    print(f"{'TOTAL':<16} {total:>5}")

    # Extraction success rates
    ec_nonempty = (df["ec_len"] > 0).sum()
    hp_nonempty = (df["hp_len"] > 0).sum()
    print(f"\nExtraction success:")
    print(f"  edgar-crawler: {ec_nonempty}/{total} ({ec_nonempty/total*100:.1f}%)")
    print(f"  H-P:           {hp_nonempty}/{total} ({hp_nonempty/total*100:.1f}%)")

    # Jaccard distribution for non-empty pairs
    both_nonempty = df[(df["ec_len"] > 0) & (df["hp_len"] > 0)]
    if len(both_nonempty) > 0:
        print(f"\nJaccard similarity (both non-empty, n={len(both_nonempty)}):")
        print(f"  Mean:   {both_nonempty['jaccard'].mean():.3f}")
        print(f"  Median: {both_nonempty['jaccard'].median():.3f}")
        print(f"  Min:    {both_nonempty['jaccard'].min():.3f}")
        print(f"  Max:    {both_nonempty['jaccard'].max():.3f}")

    # Length comparison for non-empty pairs
    if len(both_nonempty) > 0:
        len_ratio = both_nonempty["ec_len"] / both_nonempty["hp_len"]
        print(f"\nLength ratio (edgar-crawler / H-P):")
        print(f"  Mean:   {len_ratio.mean():.3f}")
        print(f"  Median: {len_ratio.median():.3f}")
        print(f"  Min:    {len_ratio.min():.3f}")
        print(f"  Max:    {len_ratio.max():.3f}")

    # ── Phase 4: Detailed diffs for non-MATCH filings ──
    non_match = df[~df["category"].isin(["MATCH", "BOTH_EMPTY"])]
    if len(non_match) > 0:
        print(f"\n{'=' * 70}")
        print(f"DETAILED DIFFS ({len(non_match)} non-match filings)")
        print(f"{'=' * 70}")

        for _, r in non_match.iterrows():
            print(f"\n--- {r['filename']} ({r['company']}) ---")
            print(f"  Category:  {r['category']}")
            print(f"  Jaccard:   {r['jaccard']}")
            print(f"  EC length: {r['ec_len']:,} chars, {r['ec_words']} words")
            print(f"  HP length: {r['hp_len']:,} chars, {r['hp_words']} words")
            if r["ec_start"]:
                print(f"  EC start:  {r['ec_start'][:100]}")
            if r["hp_start"]:
                print(f"  HP start:  {r['hp_start'][:100]}")
            if r["ec_end"]:
                print(f"  EC end:    {r['ec_end'][-100:]}")
            if r["hp_end"]:
                print(f"  HP end:    {r['hp_end'][-100:]}")

    # ── Save results ──
    csv_path = OUTPUT / "extraction_comparison_b3.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nResults saved to {csv_path}")

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
