# EDGAR Full Download & Extraction Pipeline

**Date**: 2026-03-21
**Phase**: 3 of N (Pipeline Construction)
**Goal**: Build a production pipeline to download and extract SEC filings (10-K, 10-Q, 10KSB, 10QSB) for all firms, all years (1996–present). Deploy to Mercury cluster, develop and test locally first.
**Report**: `Reports/2026-03-21-edgar-pipeline/main.pdf` — detailed design decisions, architecture, and reasoning.

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
- [x] Step 8: Copy research artifacts (plans + reports) to Docs/
- [x] Step 9: Run minimal local test (2023 × 3 CIKs) — ALL TESTS PASSED
- [ ] Step 10: Deploy to Mercury (awaiting access from Howard)

---

## Project Structure

```
SEC_filings/
├── Code/
│   ├── src/                    # Pipeline scripts (Steps 1–4)
│   ├── utils/                  # Vendored from edgar-crawler (see CHANGELOG.md)
│   ├── test/                   # Local test suite
│   ├── slurm/                  # SLURM job scripts
│   ├── progress/               # Year-level .running/.done markers
│   ├── logs/                   # SLURM output logs
│   ├── CHANGELOG.md            # Modifications to vendored utils/
│   ├── README.md               # How to run
│   └── requirements.txt
├── Data/
│   ├── raw/{filings,indices,manifest.csv}
│   └── extracted/{metadata,json-per-filing,parquet-per-type-year}
├── Docs/{plans,reports}        # Research artifacts for professor
├── CLAUDE.md
└── DATA_DICTIONARY.md
```

---

## Vendored Code Modifications (from upstream edgar-crawler)

| File | Change | Origin |
|------|--------|--------|
| `extract_items.py:169` | `== "10-K"` → `in ["10-K", "10-KT", "10KSB"]` | Tool exploration (2026-02-11) |
| `extract_items.py:171` | `== "8-K"` → `in ["8-K", "8-K/A"]` | Tool exploration (2026-02-11) |
| `extract_items.py:178` | `== "10-Q"` → `in ["10-Q", "10QSB"]` | Tool exploration (2026-02-11) |
| `extract_items.py:1085` | `== "10-Q"` → `in ["10-Q", "10QSB"]` (part splitting) | Tool exploration (2026-02-11) |
| `download_filings.py:322` | Removed interactive `input("Retry (Y/N)")` | Pipeline (2026-03-21) |
| `__init__.py` | New file: configurable `DATASET_DIR` via `set_data_dir()` | Pipeline (2026-03-21) |
| All files | Converted to relative package imports | Pipeline (2026-03-21) |

Full details in `SEC_filings/Code/CHANGELOG.md`.

---

## Mercury Deployment (after access is granted)

### Prerequisites
- SLURM account assigned (e.g., `--account=pi-<advisor>`)
- Read/write access to `/project/textual_analysis/` (or designated project directory)

### Step-by-step

**1. Copy code to Mercury**
```bash
scp -r ~/vscodeproject/SEC_filings/Code mercury:/project/textual_analysis/SEC_filings/
scp ~/vscodeproject/SEC_filings/DATA_DICTIONARY.md mercury:/project/textual_analysis/SEC_filings/
scp -r ~/vscodeproject/SEC_filings/Docs mercury:/project/textual_analysis/SEC_filings/
```

**2. Create Data directories on Mercury**
```bash
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

**5. Build manifest → Download → Extract → Consolidate**
```bash
# Manifest (interactive, ~30 min)
srun --account=pi-<advisor> --mem=4G --time=1:00:00 \
  python3 Code/src/build_manifest.py --start-year 1996 --end-year 2025 --data-dir .

# Download (job array, 30 parallel year-jobs)
sbatch Code/slurm/submit_download.sh

# After downloads complete → extract
sbatch Code/slurm/submit_extract.sh

# After extraction → consolidate
sbatch Code/slurm/submit_consolidate.sh
```

**6. Monitor**
```bash
squeue -u marcozhang
python3 Code/utils/check_progress.py --data-dir .
```

### Troubleshooting
- Failed job mid-year → re-submit. `.running` marker + metadata CSV enable automatic resume.
- Check `Code/logs/download_{year}.out` and `Code/logs/extract_{year}.out` for output.

---

## Results

### Local Test (2023 × 3 CIKs: Apple, Microsoft, Nicholas Financial)

Run via `python Code/test/run_local_test.py`. All tests passed:

| Test | Result |
|------|--------|
| Manifest (4 quarterly indices) | 26,469 filings (7,366 10-K + 19,103 10-Q) |
| Download (12 filings) | 3 10-K + 9 10-Q, metadata CSV + done marker |
| Resumability | Re-run skipped all (done marker detected) |
| Extraction (12 filings) | POR routing correct: 2023 filings with POR 2022 → `10-Q/2022/` |
| Item content | 23 item columns in 10-K JSON, item_7 (MD&A) = 15,096–49,279 chars |
| Parquet | 3 files, selective column access works |
| Progress check | Correct counts and statuses |

### Bug found during testing
`items_to_extract` must be reset to `[]` before each `determine_items_to_extract()` call in `extract_by_year.py`. Otherwise items from a previous filing type (e.g., 10-Q part-based items) persist and cause mismatches for the next type (e.g., 10-K numbered items). Fixed.

### Blocking
Mercury access (SLURM account + `/project/` permissions) — awaiting response from Howard.
