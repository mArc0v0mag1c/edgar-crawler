# EDGAR Full Download & Extraction Pipeline

**Date**: 2026-03-21
**Phase**: 3 of N (Pipeline Construction)
**Goal**: Build a production pipeline to download and extract SEC filings (10-K, 10-Q, 10KSB, 10QSB) for all firms, all years (1996–present). Deploy to Mercury cluster, develop and test locally first.

---

## Overview

- [x] Step 0: Create separate project (`SEC_filings/`) with directory structure
- [x] Step 1: Vendor utils from edgar-crawler + apply modifications
- [x] Step 2: Implement `build_manifest.py` — count expected filings per type × year
- [x] Step 3: Implement `download_by_year.py` — download raw filings for one year
- [x] Step 4: Implement `extract_by_year.py` — extract items for one year
- [x] Step 5: Implement `consolidate_parquet.py` — JSON → Parquet per type × year
- [x] Step 6: Implement `check_progress.py` — progress reporting utility
- [x] Step 7: Create SLURM scripts, README, DATA_DICTIONARY, CHANGELOG
- [x] Step 8: Copy research artifacts (plans + reports) to docs/
- [x] Step 9: Run minimal local test (2023 × 3 CIKs) — ALL TESTS PASSED

---

## Project Structure

```
SEC_filings/                               # Project root (on Mercury or local test)
│
├── Code/
│   ├── src/                               # Pipeline scripts
│   │   ├── build_manifest.py              # Step 1: count expected filings per type × year
│   │   ├── download_by_year.py            # Step 2: download raw filings for one year
│   │   ├── extract_by_year.py             # Step 3: extract items for one year
│   │   └── consolidate_parquet.py         # Step 4: JSON → Parquet per type × year
│   │
│   ├── utils/                             # Vendored from edgar-crawler + utilities
│   │   ├── __init__.py                    # Configurable DATASET_DIR
│   │   ├── download_filings.py            # Original download logic
│   │   ├── extract_items.py               # Original extraction logic
│   │   ├── item_lists.py                  # Item lists for 10-K, 10-Q, 8-K
│   │   ├── logger.py                      # Logging utility
│   │   └── check_progress.py             # Report download/extraction status
│   │
│   ├── slurm/                             # SLURM job submission scripts
│   │   ├── submit_download.sh
│   │   ├── submit_extract.sh
│   │   └── submit_consolidate.sh
│   │
│   ├── progress/                          # Year-level progress markers
│   │   ├── download_1996.done
│   │   ├── download_1997.running
│   │   └── ...
│   │
│   ├── logs/                              # SLURM job logs
│   │
│   ├── requirements.txt                   # Python dependencies
│   ├── CHANGELOG.md                       # Changes to vendored utils/ vs upstream edgar-crawler
│   └── README.md                          # How to run, project overview
│
├── Data/
│   ├── raw/                               # Downloaded raw data
│   │   ├── filings/                       # Raw filing documents by type
│   │   │   ├── 10-K/
│   │   │   ├── 10-Q/
│   │   │   ├── 10KSB/
│   │   │   └── 10QSB/
│   │   ├── indices/                       # EDGAR quarterly index files
│   │   │   ├── 1996_QTR1.tsv
│   │   │   └── ...
│   │   └── manifest.csv                   # Expected filing counts per type × year
│   │
│   └── extracted/                         # Processed output
│       ├── metadata/                      # Per-year metadata CSVs
│       │   ├── FILINGS_METADATA_1996.csv
│       │   └── ...
│       ├── json-per-filing/               # Individual JSON files by type × period_of_report year
│       │   ├── 10-K/
│       │   │   ├── 1996/
│       │   │   │   ├── {CIK}_10K_{year}_{accession}.json
│       │   │   │   └── ...
│       │   │   └── ...
│       │   ├── 10-Q/
│       │   ├── 10KSB/
│       │   └── 10QSB/
│       └── parquet-per-type-year/          # Consolidated Parquet for downstream analysis
│           ├── 10-K/
│           │   ├── 1996.parquet
│           │   └── ...
│           ├── 10-Q/
│           ├── 10KSB/
│           └── 10QSB/
│
├── docs/                                  # Research artifacts for professor's reference
│   ├── plans/
│   │   ├── 2026-02-11-tool-exploration.md
│   │   └── 2026-02-17-coverage-validation.md
│   └── reports/
│       ├── tool-exploration/main.pdf
│       └── coverage-validation/main.pdf
│
└── DATA_DICTIONARY.md                     # Column definitions, JSON/Parquet schema
```

## Key Design Decisions

### Year variable: `period_of_report`
- EDGAR index organized by **filing date** → download step uses filing-date-year
- `period_of_report` scraped during `crawl()` from filing HTML index page (line 525-527 in download_filings.py)
- If `period_of_report` is missing, filing is silently skipped (line 529-531)
- **Output organized by `period_of_report` year** (what matters for cross-sectional research)
- **Progress tracking uses filing-date year** (what EDGAR gives us during download)

### Filing types
```python
filing_types = ["10-K", "10-Q", "10KSB", "10QSB"]
```

### Progress tracking
- `manifest.csv` has expected counts per type × filing-date-year (from EDGAR indices)
- `progress/download_{year}.running` created on start, renamed to `.done` on completion
- `.running` file exists → year was interrupted
- Resume: reads existing metadata CSV, skips already-downloaded filings (same logic as original `main()` lines 131-172)

### Output format
- **JSON per filing**: individual files for per-filing inspection/debugging
- **Parquet per type × year**: consolidated for fast downstream analysis (columnar, compressed, selective column reads)

---

## Existing Code to Reuse (vendored into `Code/utils/`)

| Function | Source file | What it does |
|----------|-----------|-------------|
| `download_indices()` | `download_filings.py:226` | Downloads EDGAR quarterly index TSV files |
| `get_specific_indices()` | `download_filings.py:331` | Filters index by filing type + CIK (exact `isin()` match) |
| `crawl()` | `download_filings.py:464` | Fetches filing HTML index, extracts `period_of_report`, SIC, etc. |
| `download()` | `download_filings.py:741` | Downloads actual filing document (HTM/TXT) |
| `requests_retry_session()` | `download_filings.py:429` | HTTP session with exponential backoff |
| `ExtractItems` class | `extract_items.py:122` | Full extraction pipeline (HTML strip → item parse → JSON) |
| `ExtractItems.extract_items()` | `extract_items.py:983` | Extract items from one filing → returns JSON dict |
| `determine_items_to_extract()` | `extract_items.py:163` | Maps filing type → item list |
| Item lists | `item_lists.py` | `item_list_10k`, `item_list_10q`, `item_list_8k` |

**Modifications needed in `utils/`** (all documented in CHANGELOG.md):
- `__init__.py`: Make `DATASET_DIR` configurable (accept a path argument instead of hardcoding `datasets/`)
- `extract_items.py:163-183`: Add `10KSB`, `10QSB` to `determine_items_to_extract()` type matching
- `download_filings.py:322`: Remove interactive retry prompt (replace with auto-skip for batch mode)

**Key behaviors to preserve**:
- `crawl()` returns `None` (silent skip) when `period_of_report` is missing (line 529-531)
- `process_filing()` skips already-extracted files when `skip_extracted_filings=True` (line 1172)
- Metadata CSV uses atomic writes via temp file (line 202-211)

---

## Implementation Details

### Step 1: Vendor Utils

Copy from `edgar-crawler/` repo:
- `download_filings.py` → `Code/utils/download_filings.py`
- `extract_items.py` → `Code/utils/extract_items.py`
- `item_lists.py` → `Code/utils/item_lists.py`
- `logger.py` → `Code/utils/logger.py`

Create new `Code/utils/__init__.py` with configurable `DATASET_DIR`.

Apply 3 modifications:
1. `__init__.py`: `DATASET_DIR` configurable via function/env var
2. `extract_items.py:163-183`: Add `10KSB`, `10QSB` to type matching
3. `download_filings.py:322`: Remove interactive retry prompt

### Step 2: `build_manifest.py` — Count expected filings per year

```python
# Reuses: download_indices(), get_specific_indices() from utils/download_filings.py
# Input: None (fetches from SEC)
# Output: Data/raw/indices/*.tsv + Data/raw/manifest.csv

# manifest.csv schema:
# year | type | quarter | count
# 1996 | 10-K | 1       | 2134
# 1996 | 10-K | 2       | 1876
```

**Why filing-date-year for manifest?** The EDGAR index is organized by filing date. `period_of_report` is only known after crawling each filing's HTML index page (Step 3). So progress tracking uses filing-date-year, but output organization uses `period_of_report` year.

**Implementation**:
- Call `download_indices()` — but wrap to disable the interactive retry prompt
- Call `get_specific_indices()` to filter by `["10-K", "10-Q", "10KSB", "10QSB"]`
- Group by year × type × quarter, save counts to `manifest.csv`
- Fast (~30 min for all indices), only runs once

### Step 3: `download_by_year.py` — Download raw filings for one year

Downloads all filings of our 4 types for a single filing-date-year (all 4 quarters).

```python
# Reuses: get_specific_indices(), crawl(), download() from utils/download_filings.py
# Args: --year 2005 --data-dir SEC_filings [--ciks 320193,789019 (optional, for testing)]
# Input: Data/raw/indices/*.tsv (from Step 2)
# Output: Data/raw/filings/{type}/{filename}, Data/extracted/metadata/FILINGS_METADATA_{year}.csv
```

**Progress tracking**:
1. On start: create `Code/progress/download_{year}.running` with timestamp
2. For each filing: call `crawl()` then `download()` (existing functions)
3. Metadata saved to per-year CSV: `Data/extracted/metadata/FILINGS_METADATA_{year}.csv`
4. On completion: rename `.running` → `.done`
5. On resume (`.running` exists): read the per-year metadata CSV, skip already-downloaded filings

**Detecting incomplete years**:
- `.running` file exists → year was interrupted
- `check_progress.py` compares downloaded count vs manifest expected count

**Key differences from original `main()`**:
- Processes one year at a time (not the full range)
- Per-year metadata CSV (not one giant CSV)
- No interactive retry prompt (batch mode)
- Configurable `data_dir` via CLI arg

### Step 4: `extract_by_year.py` — Extract items for one year

Runs extraction on all downloaded filings for a given filing-date-year, organizing output by `period_of_report` year.

```python
# Reuses: ExtractItems.extract_items() from utils/extract_items.py
# Args: --year 2005 --data-dir SEC_filings
# Input: Data/raw/filings/{type}/{filename}, Data/extracted/metadata/FILINGS_METADATA_{year}.csv
# Output: Data/extracted/json-per-filing/{type}/{por_year}/{filename}.json
```

**Key design**:
- Reads `Data/extracted/metadata/FILINGS_METADATA_{year}.csv` to get filing list + `period_of_report`
- Creates `ExtractItems` instance with config (remove_tables=True, etc.)
- For each filing: calls `extraction.extract_items(filing_metadata)` to get JSON dict, then saves it ourselves to the year-organized path:
  - A filing filed in 2021 with `period_of_report=2020-12-31` → `Data/extracted/json-per-filing/10-K/2020/{filename}.json`
- Progress tracking: `.running` / `.done` same as download
- Calls `extract_items()` directly, handles file saving ourselves (don't use `process_filing()` since it hardcodes the output path)

### Step 5: `consolidate_parquet.py` — JSON → Parquet

Converts all JSONs for a given type × period_of_report year into a single Parquet file.

```python
# Args: --type 10-K --year 2005 --data-dir SEC_filings
#   OR: --all --data-dir SEC_filings  (process everything)
# Input: Data/extracted/json-per-filing/10-K/2005/*.json
# Output: Data/extracted/parquet-per-type-year/10-K/2005.parquet
```

**Implementation**:
- Glob all JSONs in `Data/extracted/json-per-filing/{type}/{year}/`
- Load each JSON, flatten to one row
- Concatenate into DataFrame
- Save as Parquet with snappy compression

**Downstream access pattern**:
```python
import pandas as pd
# Load just MD&A (item_7) for all firms in 2020
df = pd.read_parquet("Data/extracted/parquet-per-type-year/10-K/2020.parquet",
                     columns=["cik", "company", "period_of_report", "item_7"])
```

### Step 6: `check_progress.py` (in `utils/`) — Progress reporting

```
# Example output:
# DOWNLOAD PROGRESS (filing-date year):
# Year  | 10-K     | 10-Q      | 10KSB   | 10QSB   | Status
# 1996  | 8234/8234| 21456/21456| 3201/3201| 1892/1892| DONE
# 1997  | 8100/8500| -         | -       | -       | RUNNING (95.3%)
# 1998  | 0/8800   | -         | -       | -       | NOT STARTED
```

### Step 7: SLURM batch scripts + Documentation

**`slurm/submit_download.sh`** — Job array, one year per job:
```bash
#!/bin/bash
#SBATCH --account=pi-<advisor>
#SBATCH --partition=long
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=7-00:00:00
#SBATCH --job-name=edgar_dl
#SBATCH --array=1996-2025
#SBATCH --output=Code/logs/download_%a.out

module load python/booth/3.12
cd /project/SEC_filings
python3 Code/src/download_by_year.py --year=$SLURM_ARRAY_TASK_ID --data-dir=/project/SEC_filings
```

Similar scripts for extraction and consolidation.

**README.md** (in `Code/`): Project overview, folder structure, how to run locally vs Mercury, how to access data, known limitations.

**DATA_DICTIONARY.md** (project root): Metadata CSV column definitions, JSON schema per filing type, Parquet schema, filing type coverage dates.

**CHANGELOG.md** (in `Code/`): All modifications to vendored `utils/` code vs original `lefterisloukas/edgar-crawler`.

### Step 8: Research Artifacts

Copy to `docs/` for professor's reference:
- `Plans/2026-02-11-tool-exploration.md` → `docs/plans/`
- `Plans/2026-02-17-coverage-validation.md` → `docs/plans/`
- `Reports/tool-exploration/main.pdf` → `docs/reports/`
- `Reports/coverage-validation/main.pdf` → `docs/reports/`

---

## Dependencies

```
# requirements.txt
beautifulsoup4>=4.8.2
lxml>=4.9.1
pandas>=1.5.3
requests>=2.31.0
tqdm>=4.42.1
pyarrow>=10.0.0       # For Parquet support
numpy>=1.24.4
cssutils>=1.0.2
pathos>=0.2.9
```

---

## Verification — Minimal Local Test

**Test scope**: 1 year (2023) × 3 CIKs (Apple=320193, Microsoft=789019, small co=1000045)

### Test 1: Manifest
```bash
python3 Code/src/build_manifest.py --start-year=2023 --end-year=2023 --data-dir=test_data
# Verify: manifest.csv has rows for 2023 × {10-K, 10-Q} (10KSB/10QSB = 0 since 2009)
```

### Test 2: Download
```bash
python3 Code/src/download_by_year.py --year=2023 --data-dir=test_data --ciks=320193,789019,1000045
# Verify: Data/raw/filings/10-K/ has files
# Verify: Data/extracted/metadata/FILINGS_METADATA_2023.csv exists
# Verify: Code/progress/download_2023.done exists
```

### Test 3: Resumability
```bash
# Start download, Ctrl+C after 2 filings
# Verify: Code/progress/download_2023.running exists
# Resume same command
# Verify: skips already-downloaded, completes, .running → .done
```

### Test 4: Extraction
```bash
python3 Code/src/extract_by_year.py --year=2023 --data-dir=test_data
# Verify: Data/extracted/json-per-filing/10-K/{por_year}/*.json have non-empty items
# Check: filing filed in 2023 with period_of_report 2022-12-31 → lands in json-per-filing/10-K/2022/
```

### Test 5: Parquet
```bash
python3 Code/src/consolidate_parquet.py --type=10-K --year=2022 --data-dir=test_data
# Verify: Data/extracted/parquet-per-type-year/10-K/2022.parquet exists and loads in pandas
```

### Test 6: Progress check
```bash
python3 Code/utils/check_progress.py --data-dir=test_data
# Verify: shows correct counts and statuses
```

---

## Mercury Deployment (after access is granted)

### Prerequisites
- SLURM account assigned (e.g., `--account=pi-<advisor>`)
- Read/write access to `/project/textual_analysis/` (or designated project directory)

### Step-by-step

**1. Copy code to Mercury**
```bash
# From local Mac:
scp -r ~/vscodeproject/SEC_filings/Code mercury:/project/textual_analysis/SEC_filings/
scp ~/vscodeproject/SEC_filings/DATA_DICTIONARY.md mercury:/project/textual_analysis/SEC_filings/
scp -r ~/vscodeproject/SEC_filings/Docs mercury:/project/textual_analysis/SEC_filings/
```

**2. Create Data directories on Mercury**
```bash
ssh mercury
cd /project/textual_analysis/SEC_filings
mkdir -p Data/raw/{filings/{10-K,10-Q,10KSB,10QSB},indices}
mkdir -p Data/extracted/{metadata,json-per-filing/{10-K,10-Q,10KSB,10QSB},parquet-per-type-year/{10-K,10-Q,10KSB,10QSB}}
```

**3. Install Python dependencies**
```bash
module load python/booth/3.12
pip install --user -r Code/requirements.txt
```

**4. Update SLURM account in all scripts**
```bash
sed -i 's/pi-ADVISOR_ID/pi-<actual_advisor>/' Code/slurm/submit_*.sh
```

**5. Build manifest (interactive job, ~30 min)**
```bash
srun --account=pi-<advisor> --mem=4G --time=1:00:00 \
  python3 Code/src/build_manifest.py --start-year 1996 --end-year 2025 \
  --data-dir /project/textual_analysis/SEC_filings
```

**6. Submit download jobs** (one SLURM job per year, 1996–2025)
```bash
sbatch Code/slurm/submit_download.sh
```

**7. Monitor progress**
```bash
squeue -u marcozhang                                        # SLURM job status
python3 Code/utils/check_progress.py --data-dir .           # pipeline progress
```

**8. After all downloads complete → submit extraction**
```bash
sbatch Code/slurm/submit_extract.sh
```

**9. After extraction → consolidate to Parquet**
```bash
sbatch Code/slurm/submit_consolidate.sh
```

### Expected timeline
- **Manifest**: ~30 min (once)
- **Download**: ~days (30 year-jobs in parallel, each 7-day wall time)
- **Extraction**: ~days (30 year-jobs in parallel)
- **Consolidation**: ~hours (single job)

### Troubleshooting
- If a download job fails mid-year: just re-submit. The `.running` marker and metadata CSV enable automatic resume.
- If extraction fails: re-submit. Existing JSONs are skipped.
- Check `Code/logs/download_{year}.out` and `Code/logs/extract_{year}.out` for SLURM output.

---

## Results

### Step 0: Project Structure
**Expected**: Create `SEC_filings/` with all directories.
**Actual**: Created at `/Users/marcozhang_1/vscodeproject/SEC_filings/` with full directory tree.
**Interpretation**: Ready for implementation.

### Step 1: Vendor Utils
**Expected**: Copy 4 files from edgar-crawler, create `__init__.py`, apply 3 modifications.
**Actual**: Copied `download_filings.py`, `extract_items.py`, `item_lists.py`, `logger.py`. Created new `__init__.py` with `set_data_dir()`. Applied 4 modifications: (1) configurable DATASET_DIR via module-level `_pkg` pattern, (2) removed interactive `input()` prompt in `download_indices()`, (3) converted all imports to relative package imports, (4) `determine_items_to_extract()` already had 10KSB/10QSB support — no change needed.
**Interpretation**: Extra modification needed vs plan: `from . import DATASET_DIR` doesn't update when `set_data_dir()` changes the value. Solved with `importlib.import_module(__package__)` pattern so `_pkg.DATASET_DIR` always reads latest value.

### Step 2: `build_manifest.py`
**Expected**: Download EDGAR indices (1996–present), count filings per type × year × quarter, save to `manifest.csv`.
**Actual**: Test with 2023 only: downloaded 4 quarterly indices, counted 26,469 filings (7,366 10-K + 19,103 10-Q; 0 10KSB/10QSB as expected since discontinued 2009). Manifest saved correctly.
**Interpretation**: Works as designed.

### Step 3: `download_by_year.py`
**Expected**: Download all filings for one year. Per-year metadata CSV. Progress markers. Resumable.
**Actual**: Downloaded 12/12 filings for 3 CIKs (Apple, MSFT, Nicholas Financial). Metadata CSV has all columns. `download_2023.done` marker created. Resumability test: re-run detected done marker and skipped.
**Interpretation**: Works as designed. `crawl()` needed `companies_info.json` in `DATASET_DIR` — added creation in download script.

### Step 4: `extract_by_year.py`
**Expected**: Extract items, organize output by `period_of_report` year.
**Actual**: Extracted 12/12 filings. Period-of-report routing works: filings filed 2023 with POR 2022-12-31 → `json-per-filing/10-Q/2022/`. Apple 10-K has 23 item columns, item_7 (MD&A) = 15,096 chars.
**Interpretation**: Bug found and fixed: `items_to_extract` must be reset to `[]` before each `determine_items_to_extract()` call, otherwise items from previous filing type persist and cause mismatches.

### Step 5: `consolidate_parquet.py`
**Expected**: Convert JSON → Parquet per type × year.
**Actual**: Created 3 Parquet files: 10-K/2023 (3 rows), 10-Q/2022 (3 rows), 10-Q/2023 (6 rows). Columnar access works: `pd.read_parquet(..., columns=["cik", "item_7"])` returns correct data. MD&A lengths: 49,279 / 13,987 / 21,754 chars.
**Interpretation**: Works as designed.

### Step 6: `check_progress.py`
**Expected**: Print progress table.
**Actual**: Shows download status (3/7366 10-K, 9/19103 10-Q), extraction status (DONE), and Parquet summary.
**Interpretation**: Works as designed.

### Step 7: Documentation
**Expected**: SLURM scripts, README, DATA_DICTIONARY, CHANGELOG.
**Actual**: Created all files. SLURM scripts use `--array=1996-2025` for one job per year. README has quick start for local and Mercury. DATA_DICTIONARY documents metadata CSV, JSON, and Parquet schemas. CHANGELOG documents all 4 modifications.
**Interpretation**: SLURM scripts have placeholder `ADVISOR_ID` — update when Mercury access is granted.

### Step 8: Research Artifacts
**Expected**: Copy plans + reports to Docs/.
**Actual**: Copied 2 plan logs and 2 report PDFs to `Docs/plans/` and `Docs/reports/` with date prefixes.
**Interpretation**: Works as designed.

### Step 9: Minimal Local Test
**Expected**: All test cases pass.
**Actual**: ALL TESTS PASSED. Created `Code/test/run_local_test.py` that runs the full pipeline (manifest → download → resumability → extract → parquet → progress check) with assertions. Verifiable: `python Code/test/run_local_test.py`.
**Interpretation**: Pipeline is ready for Mercury deployment once access is granted.
