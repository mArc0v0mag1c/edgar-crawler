# Coverage Validation: edgar-crawler vs Hoberg-Phillips TNIC (2005)

**Date**: 2026-02-17
**Phase**: 2 of N (Coverage Validation)
**Goal**: Validate edgar-crawler against Hoberg-Phillips TNIC (2005) at two levels: (A) file-level coverage — do both tools see the same firms? (B) item-level extraction — how does edgar-crawler's parsing compare to H-P's approach? Deliverable: memo for the team.

---

## Part A: File-Level Coverage

- [x] Step A1: Download Hoberg-Phillips TNIC HHI firm-year panel, filter to 2005
- [x] Step A2: Fetch EDGAR full-index for all 4 quarters of 2005, extract 10-K variant CIKs
- [x] Step A3: Set up WRDS credentials, get CIK ↔ gvkey crosswalk from Compustat
- [x] Step A4: Compare coverage (overlap, unique-to-each, filing type breakdown)
- [x] Step A5: FY-aligned comparison using Compustat funda + EDGAR wide window
- [x] Step A6: Verify remaining misses via SEC submissions API (period_of_report)
- [x] Step A7: Fix crosswalk — rerun comparison with time-varying CIK from comp.funda
- [x] Step A8: Re-do coverage comparison with WRDS wciklink_gvkey historical crosswalk
- [x] Step A9: Robustness — fetch period_of_report for all EDGAR 10-K filings (two methods)

## Part B: Item-Level Extraction

- [x] Step B1: Obtain H-P replication code (parsing pipeline)
- [ ] Step B2: Compare H-P's Item 1 extraction logic vs edgar-crawler's extraction logic (code review)
- [ ] Step B3: Run both parsers on a sample of 10-K filings and diff the extracted text

---

## Results — Part A: File-Level Coverage

### Step A1: Hoberg-Phillips TNIC 2005 Firms
**Why**: Get the benchmark firm list — which firms had 10-K filings processed by Hoberg-Phillips in 2005.
**Expected**: Several thousand firms (typical US public firm universe).
**Actual Result**: TNIC HHI panel has 188,422 firm-year observations spanning 1988-2023. Filtering to year=2005 yields **5,122 unique firms** (by gvkey).
**Interpretation**: Consistent with the typical US public equity universe (NYSE/AMEX/NASDAQ). TNIC only includes firms with CRSP/Compustat data and parseable 10-K business descriptions.

### Step A2: EDGAR Full-Index 2005 10-K Coverage
**Why**: Get edgar-crawler's side of the comparison — all 10-K-related filings in EDGAR for 2005.
**Expected**: Should match or exceed TNIC count since EDGAR includes all filers (foreign, small business, etc.) while TNIC is limited to CRSP/Compustat universe.
**Actual Result**: Total EDGAR filings in 2005: **1,072,289**. After filtering for 9 known 10-K variants:

| Type | Count |
|------|-------|
| 10-K | 9,017 |
| 10KSB | 3,458 |
| NT 10-K | 2,540 |
| 10-K/A | 2,180 |
| 10KSB/A | 1,380 |
| NTN 10K | 81 |
| NT 10-K/A | 37 |
| 10-KT | 8 |
| 10-KT/A | 3 |
| **Total** | **18,704** |

Unique CIKs with any 10-K variant: **12,420**.

**Interpretation**: EDGAR has 2.4× more firms than TNIC. This is expected — EDGAR includes all SEC registrants (small business filers via 10KSB, foreign private issuers, shell companies, etc.) while TNIC is restricted to CRSP/Compustat universe. Note that NT (late filing notifications) and NTN filings are not actual 10-Ks — they're notifications. For a fairer comparison, one could exclude NT/NTN types, which would bring the EDGAR count to ~15,846 filings / ~10,144 CIKs.

### Step A3: CIK ↔ gvkey Crosswalk
**Why**: Reconcile identifiers — EDGAR uses CIK, TNIC uses gvkey (Compustat).
**Expected**: Most TNIC gvkeys should map to CIKs. Some EDGAR CIKs won't have gvkeys (non-Compustat filers).
**Actual Result**: Compustat `comp.company` table provides **37,257** unique gvkey-CIK pairs (1:1 mapping). Of the 5,122 TNIC 2005 gvkeys, **4,992 matched** to CIKs (97.5%). **130 gvkeys unmatched** (no CIK in Compustat company table — possibly non-US firms or data entry gaps).
**Interpretation**: The crosswalk works well. The 2.5% unmatched rate is small and unlikely to affect conclusions. These 130 firms are excluded from the comparison.

### Step A4: Coverage Comparison
**Why**: The core comparison — how well does edgar-crawler's coverage align with the established benchmark?
**Expected**: High overlap for standard 10-K filers. EDGAR should have more firms (non-Compustat filers). TNIC might have a few firms edgar-crawler misses (unlikely).
**Actual Result**:

| Metric | Count |
|--------|-------|
| TNIC firms (matched to CIK) | 4,992 |
| EDGAR 10-K firms (all variants) | 12,420 |
| **Overlap** (in both) | **4,624** |
| Only in TNIC | 368 |
| Only in EDGAR | 7,796 |
| Overlap rate (TNIC base) | **92.6%** |
| Overlap rate (EDGAR base) | 37.2% |

**EDGAR-only firms** (7,796 CIKs) — filing type breakdown:

| Type | Filings |
|------|---------|
| 10-K | 4,729 |
| 10KSB | 3,122 |
| NT 10-K | 1,917 |
| 10KSB/A | 1,222 |
| 10-K/A | 810 |

These are mostly small business filers (10KSB) and firms not in CRSP/Compustat.

**TNIC-only firms** (368 CIKs) — these DO have other EDGAR filings in 2005 (Forms 4, 3, 8-K, S-1/A, etc.) but **no 10-K variant filed in 2005**. Likely explanation: fiscal year mismatch (10-K filed in a different calendar year), or the firm was in transition (IPO, merger, delisting mid-year).

**Interpretation**: The 92.6% overlap rate from the TNIC base confirms that **edgar-crawler's EDGAR index captures virtually all firms in the Hoberg-Phillips universe**. The 7.4% of TNIC firms missing from EDGAR 10-K index are explainable by fiscal-year timing. The large number of EDGAR-only firms (7,796) is expected — these are SEC registrants outside the CRSP/Compustat universe (small business filers, foreign issuers, shells, etc.). This validates that edgar-crawler provides **at least comparable, and actually broader, coverage** than the established Hoberg-Phillips database.

### Step A5: FY-Aligned Comparison (Compustat funda + EDGAR Wide Window)
**Why**: Step A4 uses calendar year 2005 only. But TNIC year = Compustat fiscal year — a Dec FY-end firm in TNIC year=2005 files its 10-K in early 2006 (60-90 day deadline). Calendar-year-only matching underestimates coverage.
**Expected**: Expanding the EDGAR window to include 2006 Q1-Q3 should recover most of the 368 "TNIC-only" firms from Step A4.
**Actual Result**: Added EDGAR full-index for 2006 Q1-Q3 to the 2005 Q1-Q4 data (wide window = 2005Q1–2006Q3).

| Metric | Count |
|--------|-------|
| TNIC firms (CIK) | 4,992 |
| Found in EDGAR wide window | 4,761 |
| Not found in EDGAR | 231 |
| **FY-aligned overlap rate** | **95.4%** |

The wide window recovered **137 additional firms** (from 4,624 → 4,761) compared to the calendar-year-only comparison. These are FY2005 firms whose 10-K was filed in 2006 Q1-Q3.

Side finding — Compustat FY2005 has **9,477 unique CIKs** (with `fyear=2005, indfmt='INDL', datafmt='STD', popsrc='D', consol='C'`). Of these, only 6,493 (68.5%) were found in the EDGAR wide window. The gap is likely non-US firms, firms filing under different form types (20-F, 40-F), and firms that exited mid-year without filing.

**Interpretation**: FY-alignment improves the overlap from 92.6% → 95.4%. The remaining 231 firms are genuinely not in EDGAR's 10-K index for this time window.

### Step A6: SEC API Verification of Remaining Misses
**Why**: Verify the 231 remaining TNIC firms that have no 10-K in EDGAR's wide window. The SEC submissions API (`data.sec.gov/submissions/CIK{cik}.json`) includes `reportDate` (= period_of_report), allowing us to check if a 10-K exists for FY2005 that was filed outside the wide window.
**Expected**: Most of the 231 are genuinely missing — they don't have a 10-K with FY2005 period_of_report anywhere in EDGAR.
**Actual Result**: Queried all 231 CIKs against the SEC submissions API.

| Result | Count |
|--------|-------|
| Recovered (10-K with reportDate in 2005) | 1 |
| No FY2005 10-K found | 230 |
| API errors | 0 |

The single recovered firm: CIK 829499, 10-K filed 2006-10-06 with reportDate 2005-05-28 (extremely late filer, filed 16 months after FY-end).

The 230 truly missing CIKs have other EDGAR filings (Forms 4, 3, 8-K, etc.) but no 10-K variant. These are primarily:
- Foreign issuers filing 6-K instead of 10-K (foreign private issuer exemption)
- Firms in M&A transitions filing Form 425
- Firms that delisted or merged mid-year before filing their 10-K

**Final coverage**: **4,762 / 4,992 = 95.4%** of TNIC firms are covered by EDGAR (wide window + API verification). The 230 truly missing firms (4.6%) are structurally explainable.

**Interpretation**: The SEC API verification confirms that the 4.6% gap is real but benign — these firms genuinely did not file a 10-K for FY2005, mostly due to foreign private issuer status or corporate events. edgar-crawler cannot be expected to find 10-Ks that don't exist.

**Diagnostic (post-hoc)**: Initially hypothesized the 230 "missing" firms were a stale crosswalk artifact (comp.company returning successor CIKs). Step A7 tested this by switching to comp.funda — but found 0 CIK differences (hypothesis disproven for Compustat-native tables). Further investigation of the TNIC readme revealed the root cause → Step A7 interpretation.

### Step A7: Corrected Crosswalk — comp.funda Time-Varying CIK
**Why**: Steps A3-A6 used `comp.company` (static, current CIK). This maps merged/restructured firms to successor CIKs that didn't exist in 2005, inflating the "missing" count. `comp.funda WHERE fyear = 2005` provides the CIK that was in use at filing time.
**Expected**: Most of the 230 "missing" firms should be recovered, pushing coverage well above 95.4%.
**Actual Result**: The funda crosswalk has 9,477 gvkey-CIK pairs for FY2005. Of 5,122 TNIC gvkeys, **4,966 matched** (vs 4,992 from comp.company — funda has fewer because some TNIC firms lack FY2005 funda data). **0 CIKs differed** between comp.company and comp.funda for TNIC firms — the stale crosswalk hypothesis was wrong.

| Metric | comp.company (Step A4) | + wide window (Step A5) | funda + wide (Step A7) |
|--------|-----------------------|------------------------|-----------------------|
| TNIC matched to CIK | 4,992 | 4,992 | 4,966 |
| Found in EDGAR | 4,624 (92.6%) | 4,761 (95.4%) | 4,735 (95.3%) |
| Not found | 368 | 231 | 231 |

The 231 remaining TNIC-only CIKs: 217 have **no EDGAR filings at all** in the 2005Q1-2006Q3 window; only 14 have other filing types (6-K, 425, etc.). These are genuinely absent from EDGAR — the firms exist in Compustat but either never filed with the SEC under the matched CIK, or filed under a different identifier not captured by either crosswalk.

**Interpretation**: The Compustat-native crosswalk is not the issue — `comp.company` and `comp.funda` agree on CIKs. However, the TNIC readme reveals that **Hoberg-Phillips did NOT use Compustat's native CIK field**. From the readme:

> "We merge each firm's text product description to the CRSP/COMPUSTAT universe using the central index key (CIK). [We thank the Wharton Research Data Service (WRDS) for providing us with an expanded historical mapping of SEC CIK to COMPUSTAT gvkey, **as the base CIK variable in COMPUSTAT only contains current links**.]"

Hoberg-Phillips used the **WRDS `WCIKLINK_GVKEY` table** (SEC Analytics Suite), which constructs historical CIK-gvkey links from four sources: Compustat company table, CUSIP matching from 13D/G filings, Capital IQ, and the CCM link. This is strictly more comprehensive than Compustat's native CIK field. Our WRDS account lacks access to `wrdssec` (permission denied), so we cannot replicate their exact crosswalk.

**Empirical confirmation** (`check_cik_backfilling.py`): Tested all 4 CIK sources against the accessible WRDS SEC Analytics sample (`secsamp_all.wciklink_gvkey`, 74 firms).

- *Part 1*: `comp.company`, `comp.funda`, and `comp_na_daily_all.fundq` return **identical CIKs** for 20 TNIC-missing firms — zero differences. Quarterly fundamentals (fundq) has the same backfilling as annual.
- *Part 2*: Compared wciklink CIKs against all three Compustat sources for the 74 sample firms. **11/74 (15%) have a different CIK in wciklink than in Compustat**. Examples:

| gvkey | Company | wciklink CIK | Compustat CIK | Issue |
|-------|---------|-------------|---------------|-------|
| 001678 | Apache Corp | 0000006769 | 0001841666 | Successor CIK |
| 001762 | Armstrong World | 0000007431 | 0001109304 | Successor CIK |
| 001356 | Howmet Aerospace | 0000004281 | nan | No Compustat CIK |
| 001234 | Astronics Corp | 0000008063 | 0000701288 | Different CIK |

Notably, gvkey `001678` (Apache Corp) is one of our 231 "missing" TNIC firms — Compustat maps it to CIK 0001841666 (post-restructuring entity), but its actual EDGAR CIK is 0000006769.

**Conclusion**: The ~5% gap (231 firms) is a **crosswalk gap** — firms whose historical CIK is only recoverable via the WRDS SEC link table, not from Compustat's native CIK. The 15% mismatch rate in the 74-firm sample confirms this is a systematic issue. This does not reflect a coverage limitation of edgar-crawler (the 10-Ks exist in EDGAR under the correct historical CIK), but rather our inability to replicate Hoberg-Phillips's proprietary crosswalk. **Step A8 confirmed this**: using the raw wciklink crosswalk (all CIK-gvkey pairs) gives **99.8% coverage** — the gap was almost entirely a crosswalk problem.

### Step A8: Coverage with WRDS wciklink_gvkey Historical Crosswalk
**Why**: Steps A3-A7 used Compustat's native CIK (`comp.company` / `comp.funda`), which only stores current/successor CIKs. Hoberg-Phillips used WRDS `WCIKLINK_GVKEY` (SEC Analytics Suite), which preserves historical CIK-gvkey links from 4 sources (Compustat Company, CUSIP matching from 13D/G, Capital IQ, CCM). Professor Ma provided the full table.
**Expected**: wciklink should recover many of the ~363 gvkeys that Compustat couldn't map to an EDGAR CIK, closing the crosswalk gap.

**Data choice**: Professor Ma provided two files:
- `wciklink_gvkey.csv` (raw, 1M+ rows) — all CIK-gvkey pairs with `link_start_date` / `link_end_date`
- `wciklink_gvkey_year_expanded_clean.csv` (expanded, 687K rows) — expanded to firm-year level

Initially used the expanded file filtered to `year=2005`, which gave 94.9% coverage. However, investigation of the 166 remaining "uncovered" gvkeys revealed a **backfilling problem in the expanded file**:
- e.g., Apache Corp (gvkey 1678): original CIK 6769 has `link_start=2007` in wciklink, so it's absent from year=2005 in the expanded file. Instead, the successor CIK 1841666 (APA Corp, created 2021) is backfilled to 1960 and appears for year=2005 — but that CIK has no EDGAR filings until 2021.
- Same pattern for General Motors (gvkey 5073), Bank of NY Mellon (gvkey 2019), DuPont (gvkey 4060), Eaton Corp (gvkey 4199), etc. — all successor entities.

**Fix**: Switched to the **raw wciklink file** with no year filter. A gvkey is "covered" if ANY of its CIKs (across all link periods) is found in EDGAR 2005-2006.

**Actual Result** (raw wciklink, all CIK-gvkey pairs):

| Metric | Value |
|--------|-------|
| TNIC 2005 gvkeys (total) | 5,122 |
| Matched to CIK via wciklink | 5,121 (99.98%) |
| No wciklink entry | 1 |
| **Covered** (any CIK in EDGAR) | **5,112 (99.8%)** |
| Uncovered (CIK not in EDGAR) | 9 |

915 TNIC gvkeys map to **multiple CIKs** in wciklink (historical changes); matching on any one suffices.

**Filing type breakdown** of the 5,112 covered gvkeys (priority hierarchy — best available type per gvkey):

| Type | Count | % | Notes |
|------|-------|---|-------|
| 10-K | 4,833 | 94.5% | Original annual report |
| 10-K/A | 5 | 0.1% | All 5 also have 10KSB (small business filers with amendment) |
| 10KSB | 274 | 5.4% | Small business filers — no standard 10-K |

- **0 gvkeys** have only an amendment with no original filing — every covered firm has a real 10-K or 10KSB
- 2,012 gvkeys have multiple filing types (mostly 10-K + 10-K/A, i.e., original + amendment — normal)
- 279 gvkeys are small business filers (10KSB but no 10-K)
- **Action item**: 10KSB filings have a different item structure than standard 10-K (e.g., "Item 1. Description of Business" vs "Item 1. Business"). We need to verify/write extraction code for 10KSB ourselves — edgar-crawler's existing parser may not handle 10KSB-specific formatting.

**Unified comparison** (all on denominator = 5,122 TNIC gvkeys):

| Step | Crosswalk | Covered / 5,122 | No crosswalk |
|------|-----------|-----------------|--------------|
| A4 | comp.company, 2005 only | 4,624 (90.3%) | 130 |
| A5 | comp.company, wide window | 4,761 (93.0%) | 130 |
| A7 | comp.funda, wide window | 4,735 (92.4%) | 156 |
| | (comp.fundq = same, 0 diff) | | |
| A8 (expanded, year=2005) | wciklink expanded | 4,860 (94.9%) | 96 |
| **A8 (raw, all pairs)** | **wciklink raw** | **5,112 (99.8%)** | **1** |

**Recovery analysis**: Of the 363 gvkeys previously missing under the Compustat crosswalk:
- **353 recovered** — wciklink provided historical CIKs that ARE in EDGAR
- 9 still missing — wciklink CIK exists but has zero EDGAR 10-K filings in 2005-2006
- 1 still missing — no wciklink entry at all

**Diagnosis of the 9 remaining uncovered gvkeys** (SEC API verification):

All 9 have legitimate reasons for absence — **none are edgar-crawler coverage failures**:

| gvkey | CIK | Company | Reason |
|-------|-----|---------|--------|
| 15822 | 850414 | New Horizons Worldwide | Late filer — NT 10-K filed 2005, actual FY2004 & FY2005 10-Ks never filed during 2005-2006 |
| 19932 | 1366367 | Yadkin Financial | Later entity — CIK's earliest 10-K in SEC API is FY2005 (filed 2006), not found in index |
| 29886 | 866535 | Retail Pro | Late filer — NT 10-K for FY2005 only; actual 10-K not filed until 2007 |
| 63120 | 898427 | AXA S.A. | Foreign private issuer — files 6-K/13F only, never files 10-K |
| 65570 | 849667 | American Italian Pasta | Late filer — FY2005 10-K filed in **2008** (3 years late) |
| 127234 | 1428156 | Celera Corp | Spinoff — CIK didn't exist as separate filer until 2008 |
| 145416 | 1156295 | SeraCare Life Sciences | Late filer — earliest 10-K is FY2007 (filed 2008) |
| 147175 | 1424847 | Lorillard LLC | Spinoff — spun off from Loews in 2008, CIK started filing 2009 |
| 151928 | 1122832+1383183 | CombiMatrix Corp | Later entity — neither CIK had 10-K filings in 2005-2006 |

Three categories: (1) **Late filers** (4 firms) — filed 10-K years after deadline, outside 2005-2006 window; (2) **Foreign issuer** (1 firm) — AXA S.A. uses 6-K exemption; (3) **Spinoffs/new entities** (4 firms) — CIK didn't exist or wasn't filing in 2005. The EDGAR index already includes all 10-K variants (10-K, 10-K/A, 10KSB, 10KSB/A, 10-KT, 10-KT/A) — the absence is not due to missing form types.

**Interpretation**: The raw wciklink crosswalk resolves virtually the entire gap. The previous ~7% "missing" rate was almost entirely a crosswalk problem — Compustat's native CIK only has current links, and even the expanded wciklink file has a backfilling issue (successor CIKs overwrite historical ones). Using the raw file with all CIK-gvkey pairs gives **99.8% coverage** — only 10 gvkeys out of 5,122 are genuinely absent from EDGAR, all for structurally legitimate reasons (late filers, foreign issuers, spinoffs).

### Step A9: Robustness — period_of_report via SEC API
**Why**: Steps A4-A8 match TNIC to EDGAR using CIK set intersection over a wide filing-date window (2005Q1-2006Q3). This is approximate — a 10-K filed in 2006Q2 might be for FY2005 or FY2006. A cleaner approach is to fetch `period_of_report` (= `reportDate`) for every EDGAR 10-K filing and match on exact fiscal period instead of filing date.

**Approach**: Two independent methods to obtain `period_of_report`:
- **Option A** (`fetch_report_dates_api.py`): Query SEC submissions API (`data.sec.gov/submissions/CIK{cik}.json`) for all 14,962 unique CIKs, **with full pagination** (following `filings.files[]` for CIKs with >1000 filings). Extracts `reportDate` from all 10-K forms.
- **Option B** (`fetch_report_dates_headers.py`): Fetch `CONFORMED PERIOD OF REPORT` directly from each filing's SGML header (`https://www.sec.gov/Archives/{filename}`, first 4KB via Range header) for all 31,213 filings in the 2005-2006 index.

**Initial attempt (no pagination)** gave only 58.9% overlap due to the SEC API `filings.recent` array only holding ~1,000 most recent filings per CIK — FY2005 data is 20 years old, pushing many filings beyond the cutoff.

**Actual Result (with pagination / filing headers)**:

| Method | FY2005 CIKs | TNIC Covered | Rate |
|--------|-------------|-------------|------|
| Option A (API + pagination) | 12,038 | 5,084 | **99.3%** |
| Option B (filing headers) | 11,941 | 5,073 | **99.0%** |

**Cross-validation**: The two methods agree on 11,940 out of 12,038 FY2005 CIKs (99.2%). The 98 CIKs found only by Option A are FY2005 filings filed outside the 2005-2006 index window (the API sees all filing dates; Option B only queries filings in the index). Only 1 CIK appears in B but not A.

**Detail** (Option A):

| Metric | Value |
|--------|-------|
| EDGAR CIKs queried (all 2005-2006) | 14,962 |
| Total 10-K records (all years) | 199,620 |
| FY2005 10-K filings | 15,024 |
| FY2005 CIKs | 12,038 |
| API errors | 2 |

FY2005 filing type breakdown (Option A): 10-K: 9,003 | 10KSB: 3,223 | 10-K/A: 1,517 | 10KSB/A: 1,262 | 10-KT: 14 | 10-KT/A: 5

**Detail** (Option B):

| Metric | Value |
|--------|-------|
| EDGAR filings fetched | 31,213 |
| reportDate extracted | 30,991 (99.3%) |
| reportDate missing | 222 |
| FY2005 filings | 14,544 |
| FY2005 CIKs | 11,941 |

**Unified comparison** (all on 5,122 TNIC gvkeys):

| Step | Method | Covered | Rate |
|------|--------|---------|------|
| A8 | wciklink raw, wide window (CIK overlap) | 5,112 | **99.8%** |
| A9 Option A | SEC API + pagination (exact reportDate) | 5,084 | **99.3%** |
| A9 Option B | Filing headers (exact reportDate) | 5,073 | **99.0%** |

The 0.5-0.8% drop from A8 to A9 is expected: A8 counts any CIK appearing anywhere in the 2005-2006 index (regardless of fiscal year), while A9 requires the filing's fiscal period to be exactly 2005. The ~28-39 firms lost are those whose FY doesn't end in calendar year 2005 but whose 10-K was filed within the 2005-2006 window.

**Interpretation**: Using the stricter `period_of_report` matching, **99.0-99.3%** of TNIC firms are covered. This confirms that the wide-window heuristic (Step A8: 99.8%) was already a very good approximation. The period_of_report data is also a valuable artifact for future work (FY-aligned extraction).

## Results — Part B: Item-Level Extraction

### Step B1: Inventory H-P Data & Code Sources
**Why**: Determine what Hoberg-Phillips publish — data (scores) vs code (parsing logic) — to scope what validation is possible at the item level.
**Expected**: TNIC publishes similarity scores; parsing code may or may not be available.
**Actual Result**:

**Data** ([hobergphillips.tuck.dartmouth.edu](https://hobergphillips.tuck.dartmouth.edu/)): Published TNIC datasets contain only **pairwise similarity scores** (gvkey1, gvkey2, year, score) — not the raw Item 1 text extracted from 10-Ks. A firm's presence in TNIC confirms its Item 1 was successfully parsed, but the text itself is not available. This means we can only use TNIC data to validate **gvkey-level coverage** (Part A), not extraction quality.

**Code** ([replication exercise zip](https://hobergphillips.tuck.dartmouth.edu/computational_linguistics_exercise.zip), ~756MB): H-P do provide a **full-pipeline Python replication exercise** by Yuhan Ye (2022), containing 3 Jupyter notebooks plus ND-SRAF utility modules and sample 10-K files (2018 Q1, 61 filings):

| Notebook | Purpose |
|----------|---------|
| `1_EDGAR_DownloadForms.ipynb` | Download 10-K forms from EDGAR via `master.idx` full-index |
| `2_Data Extraction.ipynb` | Extract Item 1 (Business Description) from raw 10-K files |
| `3_Data Cleaning _ Computation.ipynb` | Clean text, build word vectors, compute pairwise cosine similarity |

**H-P Item 1 extraction method** (Notebook 2):
1. Read raw 10-K file, replace `\n` with space
2. If HTML, strip tags with BeautifulSoup (`html.parser`)
3. Regex extraction — cascade of 4 patterns:
   - `item[^a-zA-Z\n]*1\..*?item[^a-zA-Z\n]*1a` (item 1. → item 1a, period required)
   - `item[^a-zA-Z\n]*1\..*?item[^a-zA-Z\n]*1b` (item 1. → item 1b)
   - `item[^a-zA-Z\n]*1.*?item[^a-zA-Z\n]*1a` (item 1 → item 1a, no period)
   - `item[^a-zA-Z\n]*1.*?item[^a-zA-Z\n]*1b` (item 1 → item 1b)
4. When multiple matches, take the **longest** (skips Table of Contents matches)
5. Filter out extractions <2KB

**Interpretation**: The parsing approach is simple regex-based, conceptually identical to edgar-crawler's item extraction. Both tools find item boundaries via regex patterns in the filing text. Key differences to investigate in Step B2: edgar-crawler handles more items (not just Item 1), more filing types, and has additional heuristics (e.g., table removal, header/footer stripping).

### Step B2: Code Comparison — H-P vs edgar-crawler
**Why**: Understand specific differences in how the two tools extract Item 1 from 10-K filings. Differences in regex patterns, HTML handling, edge-case logic, or post-processing could lead to different extraction results.

**Source files**: H-P Notebook 2 (`/tmp/hp_code/code/2_Data Extraction.ipynb`, cells 25-54) vs edgar-crawler (`extract_items.py`, class `ExtractItems`).

#### Side-by-side comparison

| Dimension | H-P (Notebook 2) | edgar-crawler (`extract_items.py`) |
|-----------|-------------------|-------------------------------------|
| **File reading** | `codecs.open(f, 'r', encoding='utf8', errors='replace')` | `open(f, 'r', errors='backslashreplace')` |
| **Document isolation** | None — reads entire file | Finds `<DOCUMENT>` tags, selects the one with `<TYPE>` starting with "10" |
| **HTML detection** | Simple string check: `'<html>' in ftext.lower()` | Structural: checks for `<td>` AND `<tr>` tags after BeautifulSoup parse |
| **HTML parser** | BeautifulSoup `html.parser` → `.get_text()` | BeautifulSoup `lxml` + custom `HtmlStripper` (adds `\n\n` after div/tr/p/li, spaces after th/td, then strips remaining tags) |
| **Newline handling** | **Replaces ALL `\n` with space** before regex | **Preserves newlines**; regex requires `\n` at start of item header |
| **Embedded PDFs** | Not handled | Removed: `re.sub(r"<PDF>.*?</PDF>", ...)` |
| **Table removal** | None | Optional heuristic: removes HTML tables with numerical data (checks digit %, background color) |
| **Span handling** | None | Handles margin spans (replace with space/newline) and text-splitting spans (unwrap) |
| **Special chars** | None | Extensive: smart quotes → ASCII, Unicode dashes → hyphen, etc. (lines 257-274) |
| **Broken headers** | None | Fixes spaced-out letters: "I T E M" → "ITEM", "P A R T" → "PART" (lines 285-302) |
| **Page headers** | Removes "table of contents" string | Removes TABLE OF CONTENTS, INDEX TO FINANCIAL STATEMENTS, BACK TO CONTENTS, QUICKLINKS, page numbers |

#### Regex pattern comparison (core Item 1 extraction)

**H-P** uses 4 regex patterns in a cascade:

```
# Priority 1: greedy scan to check if any match exists
item[^a-zA-Z\n]*1.*item[^a-zA-Z\n]*1a

# If matches found, narrow with reluctant + period:
regexTxt  = item[^a-zA-Z\n]*1\..*?item[^a-zA-Z\n]*1a    # item 1. → item 1a
regexTxt2 = item[^a-zA-Z\n]*1\..*?item[^a-zA^Z\n]*1b    # item 1. → item 1b  ← BUG: ^Z

# If no matches, try without period:
regexTxtEx  = item[^a-zA-Z\n]*1.*?item[^a-zA^Z\n]*1a    # item 1 → item 1a
regexTxtEx2 = item[^a-zA-Z\n]*1.*?item[^a-zA^Z\n]*1b    # item 1 → item 1b  ← BUG: ^Z
```

Logic: First greedy pass finds any "item 1...item 1a" region. If found, narrows with reluctant patterns requiring a period. If not, tries without period. Falls through to 1b boundaries.

**Bug**: `regexTxt2`, `regexTxtEx`, and `regexTxtEx2` use `[^a-zA^Z\n]` instead of `[^a-zA-Z\n]`. The `^` inside the character class is literal, so this excludes `a-z, A, ^, Z, \n` but **allows uppercase B-Y**. Minor in practice — just means these patterns are slightly more permissive.

**edgar-crawler** uses a structured approach:

```
# Start pattern (for any item):
\n[^\S\r\n]*ITEMS?\s*{item_number}[.*~\-:\s\(]

# End pattern: same format but for the next item in sequence
# Tries ITEM 1A first, then 1B, 1C, 2, 3, ..., 16, SIGNATURE
```

Key: requires `\n` at start (item must be on its own line) and tries case-sensitive match firstirthen falls back to case-insensitive.

#### Disambiguation (when multiple matches found)

| | H-P | edgar-crawler |
|---|-----|---------------|
| **Strategy** | `max(section, key=len)` — longest match wins | Longest match **that starts after the previous item's end position** |
| **ToC handling** | Relies on body section being longer than ToC entry | Positional ordering eliminates ToC matches (they appear early, before other items) |
| **Robustness** | Can fail if ToC entry is unusually long | More robust — sequential position constraint is structural, not heuristic |

#### Quality filters

| | H-P | edgar-crawler |
|---|-----|---------------|
| **Per-item filter** | `len(result.encode('utf-8')) > 2000` — skip if <2KB | None per item |
| **Per-filing filter** | None | If ALL items are empty → skip entire filing |

#### Architectural differences summary

1. **Newline handling is the critical difference.** H-P flattens everything to one line; edgar-crawler preserves line structure and anchors regex to line starts. This means:
   - H-P: more permissive — matches "Item 1" anywhere, including mid-paragraph or in headers
   - edgar-crawler: more precise — requires "ITEM 1" at line start, reducing false positives but may miss items where the header doesn't start on its own line

2. **Boundary search strategy differs.** H-P only looks for Item 1 → Item 1A/1B. edgar-crawler searches through ALL subsequent items (1A, 1B, 1C, 2, 3, ...) so it can still find Item 1 even if Item 1A is missing from the filing.

3. **edgar-crawler is significantly more engineered.** Table removal, span handling, broken header repair, special character normalization, embedded PDF removal — these all address real edge cases in EDGAR filings that H-P ignores. The trade-off: H-P's simplicity makes it easier to reason about but may produce noisier extractions.

4. **H-P has no 10KSB handling.** The regex patterns assume standard "Item 1...Item 1A/1B" boundaries. 10KSB filings use different item titles ("Description of Business" vs "Business") and may not have Item 1A at all.

**Expected practical impact**: For well-formatted modern 10-K filings, both should produce similar Item 1 text (same start/end boundaries). Differences are most likely on: (a) older .txt filings with irregular formatting, (b) filings with long Table of Contents entries, (c) filings with tables inside Item 1 (edgar-crawler removes them, H-P doesn't), (d) 10KSB filings (edgar-crawler doesn't support; H-P might partially capture via loose regex).

### Step B3: Extraction Diff on Sample Filings (planned)
**Why**: Code review identifies theoretical differences; running both parsers on the same filings reveals practical impact.
**Approach**: Select ~20 10-K filings from the overlap set (firms in both TNIC and EDGAR). Run edgar-crawler's extraction and H-P's regex on the same raw files. Diff the extracted Item 1 text. Categorize differences: boundary differences (start/end markers), content differences (table inclusion, header pollution), or no difference.
**Status**: Planned.

---

## Artifacts

| Artifact | Location |
|----------|----------|
| Plan log (this file) | `Plans/2026-02-17-coverage-validation.md` |
| Comparison script | `Code/CoverageValidation/compare_coverage.py` |
| CIK backfilling test | `Code/CoverageValidation/check_cik_backfilling.py` |
| TNIC 2005 firms | `Output/CoverageValidation/tnic_2005_firms.csv` |
| EDGAR 2005 10-K filings | `Output/CoverageValidation/edgar_2005_10k.csv` |
| gvkey-CIK crosswalk | `Output/CoverageValidation/gvkey_cik_crosswalk.csv` |
| Coverage summary (Step 4) | `Output/CoverageValidation/coverage_summary.csv` |
| Corrected summary (Step 7) | `Output/CoverageValidation/coverage_summary_corrected.csv` |
| SEC API recovered filings | `Output/CoverageValidation/recovered_via_api.csv` |
| wciklink comparison (A8) | `Code/CoverageValidation/compare_coverage_wciklink.py` |
| Robustness script — initial (A9) | `Code/CoverageValidation/compare_coverage_robustness.py` |
| EDGAR 2005-2006 10-K index | `Output/CoverageValidation/edgar_2005_2006_10k.csv` |
| wciklink crosswalk (raw) | `Data/CoverageValidation/wciklink_gvkey.csv` |
| wciklink crosswalk (expanded) | `Data/CoverageValidation/wciklink_gvkey_year_expanded_clean.csv` |
| wciklink coverage summary | `Output/CoverageValidation/coverage_summary_wciklink.csv` |
| wciklink recovered firms | `Output/CoverageValidation/wciklink_recovered_firms.csv` |
| A9 Option A script (API pagination) | `Code/CoverageValidation/fetch_report_dates_api.py` |
| A9 Option B script (filing headers) | `Code/CoverageValidation/fetch_report_dates_headers.py` |
| A9 reportDates — API paginated | `Output/CoverageValidation/edgar_10k_report_dates_paginated.csv` |
| A9 reportDates — filing headers | `Output/CoverageValidation/edgar_10k_report_dates_headers.csv` |
| A9 coverage summary (Option A) | `Output/CoverageValidation/coverage_summary_option_a.csv` |
| A9 coverage summary (Option B) | `Output/CoverageValidation/coverage_summary_option_b.csv` |
| A9 reportDates — initial (no pagination) | `Output/CoverageValidation/edgar_10k_report_dates.csv` |
| H-P replication exercise | `/tmp/hp_code/code/` (extracted from [zip](https://hobergphillips.tuck.dartmouth.edu/computational_linguistics_exercise.zip)) |

---

## Outcome

### Part A conclusion: File-level coverage validated

**Coverage breadth**: EDGAR is 3× broader than TNIC.

| Universe | Unique 10-K filers |
|----------|--------------------|
| **EDGAR full-index** (2005-2006) | **14,962** CIKs |
| Hoberg-Phillips TNIC (2005) | 5,122 gvkeys |
| Compustat funda FY2005 | 9,477 CIKs |

**Coverage overlap** (all on 5,122 TNIC gvkeys):

| Step | Crosswalk / Method | Covered | Rate | No crosswalk |
|------|-------------------|---------|------|--------------|
| A4 | comp.company (2005 only) | 4,624 | 90.3% | 130 |
| A5 | comp.company (wide window) | 4,761 | 93.0% | 130 |
| A7 | comp.funda (wide window) | 4,735 | 92.4% | 156 |
| | comp.fundq (= same as funda) | — | — | — |
| A8 | wciklink (expanded, year=2005) | 4,860 | 94.9% | 96 |
| **A8** | **wciklink (raw, all pairs)** | **5,112** | **99.8%** | **1** |
| A9 | reportDate match (API pagination) | 5,084 | 99.3% | 1 |
| A9 | reportDate match (filing headers) | 5,073 | 99.0% | 1 |

**Remaining gap** (10 gvkeys / 0.2% under A8; 37-48 under A9) — all structurally explained:
- 4 **late filers** — 10-K for FY2005 filed years late (2007-2008), outside the 2005-2006 index window
- 4 **spinoffs/new entities** — CIK didn't exist or wasn't filing in 2005
- 1 **foreign private issuer** — AXA S.A. files 6-K only, never files 10-K
- 1 gvkey has no wciklink entry at all
- A9's additional ~28 uncovered firms (vs A8) are firms whose fiscal year doesn't end in calendar 2005 but whose 10-K was filed within the 2005-2006 index window

**Root cause progression**:
- Steps A4-A7: Compustat's native CIK is backfilled (company = funda = fundq), missing historical links → ~7-10% gap
- Step A7: Discovered H-P used WRDS `WCIKLINK_GVKEY` (SEC Analytics Suite) with 4 sources
- Step A8 (expanded): wciklink's year-expanded file still backfills successor CIKs into historical years → 94.9%
- Step A8 (raw): Using raw wciklink with ALL CIK-gvkey pairs (no year filter) → **99.8%**
- Step A9: Exact fiscal-year matching via reportDate → **99.0-99.3%** (two independent methods cross-validate)
- The ~7% gap was **almost entirely a crosswalk problem**, not a coverage problem

**edgar-crawler's EDGAR source covers 99.0-99.8% of the Hoberg-Phillips TNIC universe** depending on matching method. The remaining 10-48 gvkeys (0.2-0.9%) are genuinely absent from EDGAR or have non-2005 fiscal years.

### Part B conclusion: Item-level extraction — in progress

TNIC published data contains only pairwise similarity scores, so we can only validate **gvkey coverage** (Part A), not extraction quality. However, H-P's publicly available replication code provides a reference parsing implementation for direct code comparison (Steps B2-B3 pending).
