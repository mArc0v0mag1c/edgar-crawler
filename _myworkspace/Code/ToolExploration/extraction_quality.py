"""
Extraction quality checks for edgar-crawler (B3, B5, B6).
Analyzes expected test fixture JSONs to understand:
- B3: Item evolution over time (which items exist when)
- B5: Combined items detection (empty 9A/9B when 9 has content)
- B6: 10-Q part-level vs item-level extraction consistency
"""
import json
import zipfile
import os
import pandas as pd
import numpy as np
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
TMPDIR = Path("/tmp/edgar-crawler")
OUTPUT = Path(__file__).resolve().parents[2] / "Output" / "ToolExploration"

# ── Extract test fixtures ──
for filing_type in ["10-K", "10-Q"]:
    for folder in ["RAW_FILINGS", "EXTRACTED_FILINGS"]:
        zp = FIXTURES / folder / f"{filing_type}.zip"
        if zp.exists():
            zipfile.ZipFile(zp).extractall(TMPDIR / folder)

metadata = pd.read_csv(FIXTURES / "FILINGS_METADATA_TEST.csv", dtype=str)

# ══════════════════════════════════════════════════
# B3: Item Evolution Over Time (10-K)
# ══════════════════════════════════════════════════
print("=" * 70)
print("B3: ITEM EVOLUTION OVER TIME (10-K)")
print("=" * 70)

tenk_dir = TMPDIR / "EXTRACTED_FILINGS" / "10-K"
tenk_meta = metadata[metadata["Type"] == "10-K"].copy()
tenk_meta["year"] = tenk_meta["Date"].str[:4].astype(int)

item_keys = [
    "item_1", "item_1A", "item_1B", "item_1C",
    "item_2", "item_3", "item_4", "item_5", "item_6",
    "item_7", "item_7A", "item_8",
    "item_9", "item_9A", "item_9B", "item_9C",
    "item_10", "item_11", "item_12", "item_13", "item_14",
    "item_15", "item_16"
]

rows = []
for _, row in tenk_meta.iterrows():
    jf = tenk_dir / f"{row['filename'].split('.')[0]}.json"
    if not jf.exists():
        continue
    with open(jf) as f:
        data = json.load(f)
    r = {"filename": row["filename"], "year": row["year"], "company": row["Company"]}
    for ik in item_keys:
        val = data.get(ik, "")
        r[ik] = "present" if val and len(val.strip()) > 50 else ("short" if val and val.strip() else "empty")
    rows.append(r)

df_items = pd.DataFrame(rows)

# Pivot: for each year, which items have content?
print("\nItem availability by year (present/short/empty):")
for year in sorted(df_items["year"].unique()):
    yr_data = df_items[df_items["year"] == year]
    n = len(yr_data)
    print(f"\n  {year} ({n} filings):")
    for ik in item_keys:
        counts = yr_data[ik].value_counts()
        present = counts.get("present", 0)
        short = counts.get("short", 0)
        empty = counts.get("empty", 0)
        if present > 0 or short > 0:
            print(f"    {ik:12s}: {present} present, {short} short, {empty} empty")

# Focus on newer items
print("\n\nFOCUS: Newer Items (1C, 9C, 6)")
for ik in ["item_1C", "item_9C", "item_6"]:
    print(f"\n  {ik}:")
    for year in sorted(df_items["year"].unique()):
        yr_data = df_items[df_items["year"] == year]
        counts = yr_data[ik].value_counts()
        present = counts.get("present", 0)
        short = counts.get("short", 0)
        status = f"{present} present, {short} short" if present + short > 0 else "all empty"
        print(f"    {year}: {status} (out of {len(yr_data)})")

# ══════════════════════════════════════════════════
# B5: Combined Items Detection
# ══════════════════════════════════════════════════
print("\n" + "=" * 70)
print("B5: COMBINED ITEMS DETECTION")
print("=" * 70)

# Check cases where item_9 has content but item_9A or item_9B are empty
combined_cases = []
for _, row in df_items.iterrows():
    jf = tenk_dir / f"{row['filename'].split('.')[0]}.json"
    if not jf.exists():
        continue
    with open(jf) as f:
        data = json.load(f)

    i9 = data.get("item_9", "").strip()
    i9a = data.get("item_9A", "").strip()
    i9b = data.get("item_9B", "").strip()

    if len(i9) > 50 and len(i9a) < 50:
        # Check if item_9 contains "9A" or "Controls and Procedures"
        has_9a_ref = "9A" in i9 or "controls and procedures" in i9.lower() or "9 A" in i9
        combined_cases.append({
            "filename": row["filename"],
            "year": row["year"],
            "item_9_len": len(i9),
            "item_9A_len": len(i9a),
            "item_9B_len": len(i9b),
            "item_9_contains_9A_ref": has_9a_ref,
            "item_9_snippet": i9[:300]
        })

print(f"\nCases where item_9 has content but item_9A is empty: {len(combined_cases)}")
for c in combined_cases:
    print(f"\n  {c['filename']} ({c['year']}):")
    print(f"    item_9: {c['item_9_len']} chars, item_9A: {c['item_9A_len']} chars, item_9B: {c['item_9B_len']} chars")
    print(f"    item_9 contains '9A'/'Controls and Procedures' ref: {c['item_9_contains_9A_ref']}")
    if c['item_9_contains_9A_ref']:
        print(f"    Snippet: {c['item_9_snippet'][:200]}...")

# Also check Part III combined items (10-14)
print("\n\nPart III combined items check (items 10-14):")
part3_combined = []
for _, row in df_items.iterrows():
    jf = tenk_dir / f"{row['filename'].split('.')[0]}.json"
    if not jf.exists():
        continue
    with open(jf) as f:
        data = json.load(f)

    i10 = len(data.get("item_10", "").strip())
    i11 = len(data.get("item_11", "").strip())
    i12 = len(data.get("item_12", "").strip())
    i13 = len(data.get("item_13", "").strip())
    i14 = len(data.get("item_14", "").strip())

    # If item_10 has content but 11-14 are all very short
    if i10 > 100 and i11 < 50 and i12 < 50 and i13 < 50:
        text10 = data.get("item_10", "")
        has_combined_ref = any(x in text10.lower() for x in ["item 11", "item 12", "item 13", "incorporated by reference"])
        part3_combined.append({
            "filename": row["filename"],
            "year": row["year"],
            "lens": f"10:{i10}, 11:{i11}, 12:{i12}, 13:{i13}, 14:{i14}",
            "has_combined_ref": has_combined_ref
        })

print(f"Cases where item_10 has content but items 11-13 are short: {len(part3_combined)}")
for c in part3_combined[:5]:
    print(f"  {c['filename']} ({c['year']}): {c['lens']} | combined ref: {c['has_combined_ref']}")

# ══════════════════════════════════════════════════
# B6: 10-Q Time-Series Consistency
# ══════════════════════════════════════════════════
print("\n" + "=" * 70)
print("B6: 10-Q TIME-SERIES CONSISTENCY (Part-Level vs Item-Level)")
print("=" * 70)

tenq_dir = TMPDIR / "EXTRACTED_FILINGS" / "10-Q"
tenq_meta = metadata[metadata["Type"] == "10-Q"].copy()
tenq_meta["year"] = tenq_meta["Date"].str[:4].astype(int)

tenq_rows = []
for _, row in tenq_meta.iterrows():
    jf = tenq_dir / f"{row['filename'].split('.')[0]}.json"
    if not jf.exists():
        continue
    with open(jf) as f:
        data = json.load(f)

    # Check for item-level keys
    item_keys_present = [k for k in data.keys() if k.startswith("part_1_item_") or k.startswith("part_2_item_")]
    part_keys_present = [k for k in data.keys() if k in ("part_1", "part_2")]

    # Check if item-level keys have content
    item_content = {k: len(data[k].strip()) for k in item_keys_present}
    has_item_content = any(v > 50 for v in item_content.values())

    part1_len = len(data.get("part_1", "").strip())
    part2_len = len(data.get("part_2", "").strip())

    tenq_rows.append({
        "filename": row["filename"],
        "year": row["year"],
        "company": row["Company"],
        "has_item_keys": len(item_keys_present) > 0,
        "has_item_content": has_item_content,
        "n_item_keys": len(item_keys_present),
        "n_nonempty_items": sum(1 for v in item_content.values() if v > 50),
        "part1_len": part1_len,
        "part2_len": part2_len,
        "extraction_type": "item" if has_item_content else "part_only"
    })

df_tenq = pd.DataFrame(tenq_rows)

print("\n10-Q extraction type by year:")
print(f"{'Year':<6} {'Total':<6} {'Item-level':<12} {'Part-only':<12} {'Item %':<8}")
print("-" * 44)
for year in sorted(df_tenq["year"].unique()):
    yr = df_tenq[df_tenq["year"] == year]
    n = len(yr)
    item = (yr["extraction_type"] == "item").sum()
    part = (yr["extraction_type"] == "part_only").sum()
    pct = f"{item/n*100:.0f}%" if n > 0 else "N/A"
    print(f"{year:<6} {n:<6} {item:<12} {part:<12} {pct:<8}")

print("\nDetailed part-only failures (where items exist but are empty):")
part_only = df_tenq[df_tenq["extraction_type"] == "part_only"]
for _, row in part_only.head(10).iterrows():
    print(f"  {row['filename']} ({row['year']}): {row['n_item_keys']} item keys, {row['n_nonempty_items']} with content, part1={row['part1_len']} chars, part2={row['part2_len']} chars")

# Save summary
df_items.to_csv(OUTPUT / "b3_item_evolution_10k.csv", index=False)
df_tenq.to_csv(OUTPUT / "b6_tenq_extraction_type.csv", index=False)
print(f"\nSaved: {OUTPUT / 'b3_item_evolution_10k.csv'}")
print(f"Saved: {OUTPUT / 'b6_tenq_extraction_type.csv'}")
