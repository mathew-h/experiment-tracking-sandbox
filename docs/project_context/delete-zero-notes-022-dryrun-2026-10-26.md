# `delete_zero_notes_022` dry-run report — production mirror, 2026-10-26

**Issue: `docs/issues/issue-zero-note-cells.md`. Status: AWAITING AUDIT by Mat Hearl. `--apply` has NOT been run on production.**

Produced against a **mirror of the lab PC database**: the 2026-10-26 01:00 backup
(`docs/sample_data/experiments_20261026_010002.sql`) restored into the local dev DB
(already at Alembic head `e9a4c1f7b3d2`), then:

```
PYTHONIOENCODING=utf-8 python database/data_migrations/delete_zero_notes_022.py
```

## Summary

| Bucket | Count | Spec table | Action on `--apply` |
|---|---|---|---|
| Targets: exact `'0'`, `master_bulk_upload`, modification / observation | **186** (105 modification + 81 observation) | 105 + 81 | deleted, one ModificationsLog snapshot each |
| Joined zero (`'0'` is one `;`-separated part) | 13 (7 `master_bulk_upload`, 6 `reclassify_notes_020`) | 7 + 6 | report only |
| Exact `'0'`, other author or other note type | 0 | — | report only |
| Exact `'0'`, `created_by IS NULL` | 1 (CF_020-5_Puddle, description) | 1 | report only |
| `'nan'` notes | 31 | 31 | report only |

Every count matches the issue doc's 2026-10-26 table.

## Rehearsal on the mirror (after this dry run)

These ran on the dev mirror only, to check the issue's blast-radius claims. Nothing here touched production.

1. `--apply`: exit 0, "186 notes deleted (matches the dry-run plan)"; notes 5401 → 5215.
2. A second `--apply`: "0 notes deleted". The script is idempotent.
3. Acceptance queries: `'0'` master modification/observation notes = **0**; `modifications_log WHERE modified_by = 'delete_zero_notes_022'` = **186**.
4. Uploaded `docs/sample_data/Master_Results_Tracker_v5.xlsx` (OVERWRITE=TRUE rows) through `MasterBulkUploadService.from_bytes_ex` with the fixed parser, and compared every `master_bulk_upload` note before and after:
   - **0 deleted** (no real text lost), **0 `'0'` notes created**.
   - 7 created, all real text (e.g. HPHT_309 T17 `'Gas, liquid'`).
   - 2 changed: HPHT_297 T14 `'low P gas, cold liquid; 0'` → `'low P gas, cold liquid'` (as the issue predicted), and HPHT_312 T6 `'hot gas, cold liquid'` → `'hot gas, cold liquid, solid'` (a sheet edit made after the backup).
   - Upload result: created 10, updated 296, skipped 27, errors 27. All 27 errors are "Experiment … not found": experiments created after the 01:00 backup, so they are not in the mirror.
5. HPHT_309: no `modification` note on any timepoint (T0, T3, T7, T10, T13, T17).

## Not touched, needs a separate decision

- The 13 joined-zero notes. Six `master_bulk_upload` ones heal on the next OVERWRITE upload if their rows are still on the sheet (HPHT_297 T14 did). The six `reclassify_notes_020` copies and the master copies for timepoints the sheet no longer covers stay as they are.
- CF_020-5_Puddle's description `'0'` (NULL author, predates this bug).
- The 31 `'nan'` observations (NULL author, predate this bug).

## Raw output

```
## delete_zero_notes_022 -- report

| bucket | count |
|---|---|
| targets (deleted on --apply) | 186 |
| joined-zero (report only) | 13 |
| other-author / other-type zero (report only) | 0 |
| NULL-author zero (report only) | 1 |
| nan notes (report only) | 31 |

Targets by note_type: modification=105, observation=81

### targets (deleted on --apply)
id | experiment_id | note_type | result_id | created_by | note_text
5611 | SERUM_pH_001a-t1 | observation | 1869 | master_bulk_upload | 0
5612 | SERUM_pH_001b-t1 | observation | 1870 | master_bulk_upload | 0
5613 | SERUM_pH_001c-t1 | observation | 1871 | master_bulk_upload | 0
5614 | SERUM_pH_002-t1 | observation | 1872 | master_bulk_upload | 0
5615 | SERUM_pH_003a-t1 | observation | 1873 | master_bulk_upload | 0
5616 | SERUM_pH_003b-t1 | observation | 1874 | master_bulk_upload | 0
5617 | SERUM_pH_003c-t1 | observation | 1875 | master_bulk_upload | 0
5618 | SERUM_pH_004-t1 | observation | 1876 | master_bulk_upload | 0
5619 | SERUM_pH_005a-t1 | observation | 1877 | master_bulk_upload | 0
5620 | SERUM_pH_005b-t1 | observation | 1878 | master_bulk_upload | 0
5621 | SERUM_pH_005c-t1 | observation | 1879 | master_bulk_upload | 0
5622 | SERUM_pH_006-t1 | observation | 1880 | master_bulk_upload | 0
5623 | SERUM_pH_004-t3 | observation | 1926 | master_bulk_upload | 0
5624 | SERUM_pH_006-t3 | observation | 1927 | master_bulk_upload | 0
5625 | SERUM_pH_002-t3 | observation | 1928 | master_bulk_upload | 0
5626 | SERUM_pH_001a-t3 | observation | 1929 | master_bulk_upload | 0
5627 | SERUM_pH_001c-t3 | observation | 1930 | master_bulk_upload | 0
5628 | SERUM_pH_003a-t3 | observation | 1931 | master_bulk_upload | 0
5629 | SERUM_pH_003c-t3 | observation | 1932 | master_bulk_upload | 0
5630 | SERUM_pH_003b-t3 | observation | 1933 | master_bulk_upload | 0
5631 | SERUM_pH_005c-t3 | observation | 1934 | master_bulk_upload | 0
5632 | SERUM_pH_001b-t3 | observation | 1935 | master_bulk_upload | 0
5633 | SERUM_pH_005b-t3 | observation | 1936 | master_bulk_upload | 0
5634 | SERUM_pH_005a-t3 | observation | 1937 | master_bulk_upload | 0
5635 | SERUM_Cation_001b-t5 | observation | 1938 | master_bulk_upload | 0
5636 | SERUM_Cation_002b-t5 | observation | 1939 | master_bulk_upload | 0
5637 | SERUM_Cation_003c-t5 | observation | 1940 | master_bulk_upload | 0
5638 | SERUM_Cation_001c-t5 | observation | 1941 | master_bulk_upload | 0
5639 | SERUM_Cation_001a-t5 | observation | 1942 | master_bulk_upload | 0
5640 | SERUM_Cation_003b-t5 | observation | 1943 | master_bulk_upload | 0
5641 | SERUM_Cation_002a-t5 | observation | 1944 | master_bulk_upload | 0
5642 | SERUM_Cation_016-t5 | observation | 1945 | master_bulk_upload | 0
5643 | SERUM_Cation_002c-t5 | observation | 1946 | master_bulk_upload | 0
5644 | SERUM_Cation_003a-t5 | observation | 1947 | master_bulk_upload | 0
5647 | HPHT_228 | observation | 1925 | master_bulk_upload | 0
5648 | SERUM_pH_001c-t7 | observation | 1948 | master_bulk_upload | 0
5649 | SERUM_pH_002-t7 | observation | 1949 | master_bulk_upload | 0
5650 | SERUM_pH_005a-t7 | observation | 1952 | master_bulk_upload | 0
5651 | SERUM_pH_003a-t7 | observation | 1953 | master_bulk_upload | 0
5652 | SERUM_pH_003c-t7 | observation | 1954 | master_bulk_upload | 0
5653 | SERUM_pH_004-t7 | observation | 1955 | master_bulk_upload | 0
5654 | SERUM_pH_001b-t7 | observation | 1956 | master_bulk_upload | 0
5655 | SERUM_pH_001a-t7 | observation | 1957 | master_bulk_upload | 0
5656 | SERUM_pH_005c-t7 | observation | 1958 | master_bulk_upload | 0
5657 | SERUM_pH_005b-t7 | observation | 1959 | master_bulk_upload | 0
5658 | SERUM_pH_003b-t7 | observation | 1960 | master_bulk_upload | 0
5659 | SERUM_pH_006-t7 | observation | 1961 | master_bulk_upload | 0
5667 | SERUM_Cation_004b-t5 | observation | 1969 | master_bulk_upload | 0
5668 | SERUM_Cation_006a-t5 | observation | 1970 | master_bulk_upload | 0
5732 | SERUM_Cation_008b-t5 | observation | 2024 | master_bulk_upload | 0
5733 | SERUM_Cation_005a-t5 | observation | 2023 | master_bulk_upload | 0
5806 | SERUM_Catalyst_010-t7 | observation | 2101 | master_bulk_upload | 0
5822 | HPHT_222 | observation | 2115 | master_bulk_upload | 0
5823 | HPHT_223 | observation | 2116 | master_bulk_upload | 0
5824 | HPHT_224 | observation | 2117 | master_bulk_upload | 0
5900 | HPHT_232 | observation | 2198 | master_bulk_upload | 0
5901 | HPHT_237 | observation | 2199 | master_bulk_upload | 0
5903 | HPHT_229 | observation | 2200 | master_bulk_upload | 0
5914 | HPHT_240 | observation | 2210 | master_bulk_upload | 0
5915 | HPHT_241 | observation | 2211 | master_bulk_upload | 0
5916 | HPHT_230 | observation | 2212 | master_bulk_upload | 0
5929 | SERUM_CatalystCation_008-t3 | observation | 2225 | master_bulk_upload | 0
5931 | SERUM_CatalystCation_007b-t3 | observation | 2227 | master_bulk_upload | 0
5932 | SERUM_CatalystCation_007c-t3 | observation | 2228 | master_bulk_upload | 0
5936 | SERUM_CatalystCation_006-t3 | observation | 2232 | master_bulk_upload | 0
5937 | SERUM_Catalyst_014a-t5 | observation | 2261 | master_bulk_upload | 0
5981 | SERUM_CatalystCation_005b-t20 | observation | 2279 | master_bulk_upload | 0
5982 | SERUM_CatalystCation_005c-t20 | observation | 2280 | master_bulk_upload | 0
5983 | SERUM_CatalystCation_006-t20 | observation | 2281 | master_bulk_upload | 0
5984 | SERUM_CatalystCation_005a-t20 | observation | 2282 | master_bulk_upload | 0
5985 | SERUM_CatalystCation_005b-t7 | observation | 2283 | master_bulk_upload | 0
5986 | SERUM_CatalystCation_005a-t7 | observation | 2284 | master_bulk_upload | 0
6001 | CF_020-4 | observation | 2298 | master_bulk_upload | 0
6101 | CF_020-5 | observation | 2378 | master_bulk_upload | 0
6379 | HPHT_228-2 | observation | 2693 | master_bulk_upload | 0
6821 | CF_023-3 | observation | 2808 | master_bulk_upload | 0
8010 | SERUM_pHIS_001c-t3 | modification | 2978 | master_bulk_upload | 0
8011 | SERUM_pHIS_002c-t3 | modification | 2981 | master_bulk_upload | 0
8012 | SERUM_pHIS_003c-t3 | modification | 2956 | master_bulk_upload | 0
8013 | SERUM_pHIS_004a-t3 | modification | 2971 | master_bulk_upload | 0
8025 | CF_026-2 | modification | 3020 | master_bulk_upload | 0
8034 | HPHT_301 | modification | 2992 | master_bulk_upload | 0
8439 | HPHT_281 | modification | 3037 | master_bulk_upload | 0
8441 | HPHT_279 | modification | 3038 | master_bulk_upload | 0
8444 | HPHT_297 | modification | 3040 | master_bulk_upload | 0
8446 | CF_027-3 | modification | 3041 | master_bulk_upload | 0
8450 | HPHT_307 | modification | 3043 | master_bulk_upload | 0
8452 | HPHT_308 | modification | 3044 | master_bulk_upload | 0
8454 | HPHT_305 | modification | 3045 | master_bulk_upload | 0
8456 | HPHT_306 | modification | 3046 | master_bulk_upload | 0
8482 | SERUM_Catalyst_035b-t20 | modification | 3010 | master_bulk_upload | 0
8483 | SERUM_Catalyst_033b-t20 | modification | 3016 | master_bulk_upload | 0
8489 | HPHT_298 | modification | 3054 | master_bulk_upload | 0
8491 | HPHT_297-2 | modification | 3055 | master_bulk_upload | 0
8493 | CF_027-4 | modification | 3056 | master_bulk_upload | 0
8501 | CF_029 | modification | 3060 | master_bulk_upload | 0
8503 | HPHT_313 | modification | 3061 | master_bulk_upload | 0
8505 | HPHT_314 | modification | 3062 | master_bulk_upload | 0
8507 | CF_028 | modification | 3063 | master_bulk_upload | 0
8508 | SERUM_Catalyst_037c-t5 | modification | 2993 | master_bulk_upload | 0
8509 | SERUM_Catalyst_039b-t5 | modification | 2998 | master_bulk_upload | 0
8510 | SERUM_Catalyst_041c-t5 | modification | 3003 | master_bulk_upload | 0
8511 | SERUM_Catalyst_043c-t5 | modification | 2996 | master_bulk_upload | 0
8512 | SERUM_waterrock_015a-t1 | modification | 2921 | master_bulk_upload | 0
8513 | SERUM_waterrock_017a-t1 | modification | 2928 | master_bulk_upload | 0
8514 | SERUM_waterrock_019a-t1 | modification | 2929 | master_bulk_upload | 0
8515 | SERUM_waterrock_021a-t1 | modification | 2926 | master_bulk_upload | 0
8516 | SERUM_waterrock_023a-t1 | modification | 2936 | master_bulk_upload | 0
8517 | SERUM_waterrock_009a-t5 | modification | 2950 | master_bulk_upload | 0
8518 | SERUM_waterrock_011c-t5 | modification | 2948 | master_bulk_upload | 0
8519 | SERUM_waterrock_013c-t5 | modification | 2947 | master_bulk_upload | 0
8525 | HPHT_312 | modification | 3066 | master_bulk_upload | 0
8526 | SERUM_Chelator_001a-t5 | modification | 2443 | master_bulk_upload | 0
8527 | SERUM_Chelator_001b-t5 | modification | 2445 | master_bulk_upload | 0
8528 | SERUM_Chelator_003c-t5 | modification | 2446 | master_bulk_upload | 0
8529 | SERUM_Chelator_005a-t5 | modification | 2433 | master_bulk_upload | 0
8530 | SERUM_Chelator_007c-t5 | modification | 2424 | master_bulk_upload | 0
8536 | HPHT_307 | modification | 3068 | master_bulk_upload | 0
8538 | HPHT_308 | modification | 3069 | master_bulk_upload | 0
8744 | CF_030 | modification | 3089 | master_bulk_upload | 0
8780 | HPHT_310 | modification | 3053 | master_bulk_upload | 0
8783 | HPHT_310 | modification | 3059 | master_bulk_upload | 0
8787 | HPHT_297-2 | modification | 3119 | master_bulk_upload | 0
8789 | HPHT_312 | modification | 3120 | master_bulk_upload | 0
8790 | HPHT_313 | observation | 3121 | master_bulk_upload | 0
8791 | HPHT_313 | modification | 3121 | master_bulk_upload | 0
8792 | HPHT_314 | observation | 3122 | master_bulk_upload | 0
8793 | HPHT_314 | modification | 3122 | master_bulk_upload | 0
8797 | HPHT_310 | modification | 3124 | master_bulk_upload | 0
8798 | HPHT_315 | observation | 3125 | master_bulk_upload | 0
8800 | HPHT_305 | modification | 3126 | master_bulk_upload | 0
8802 | HPHT_306 | modification | 3127 | master_bulk_upload | 0
8813 | HPHT_309 | modification | 3052 | master_bulk_upload | 0
8814 | HPHT_309 | modification | 3058 | master_bulk_upload | 0
8816 | HPHT_309 | modification | 3123 | master_bulk_upload | 0
8821 | CF_030-2 | modification | 3137 | master_bulk_upload | 0
9048 | CF_026-3 | modification | 3139 | master_bulk_upload | 0
9050 | HPHT_318 | modification | 3140 | master_bulk_upload | 0
9052 | HPHT_319 | modification | 3141 | master_bulk_upload | 0
9054 | HPHT_316 | modification | 3142 | master_bulk_upload | 0
9056 | HPHT_311 | modification | 3143 | master_bulk_upload | 0
9064 | CF_026-4 | modification | 3149 | master_bulk_upload | 0
9066 | CF_030-3 | modification | 3150 | master_bulk_upload | 0
9068 | CF_027-5 | modification | 3151 | master_bulk_upload | 0
9069 | SERUM_Catalyst_002-t7 | modification | 2067 | master_bulk_upload | 0
9070 | SERUM_Catalyst_010-t3 | modification | 2019 | master_bulk_upload | 0
9071 | SERUM_Catalyst_004-t7 | modification | 2090 | master_bulk_upload | 0
9072 | SERUM_Catalyst_008-t7 | modification | 2095 | master_bulk_upload | 0
9073 | SERUM_Catalyst_012b-t5 | modification | 2263 | master_bulk_upload | 0
9074 | SERUM_BO3_005a-t5 | modification | 3072 | master_bulk_upload | 0
9075 | SERUM_BO3_003c-t5 | modification | 3076 | master_bulk_upload | 0
9076 | SERUM_BO3_001b-t5 | modification | 3088 | master_bulk_upload | 0
9079 | HPHT_310 | modification | 3145 | master_bulk_upload | 0
9080 | HPHT_309 | modification | 3146 | master_bulk_upload | 0
9103 | HPHT_304 | modification | 3118 | master_bulk_upload | 0
9104 | SERUM_BO3_017a-t5 | modification | 3153 | master_bulk_upload | 0
9105 | SERUM_BO3_013b-t5 | modification | 3155 | master_bulk_upload | 0
9106 | SERUM_BO3_007b-t5 | modification | 3159 | master_bulk_upload | 0
9107 | SERUM_BO3_009a-t5 | modification | 3163 | master_bulk_upload | 0
9108 | SERUM_BO3_011c-t5 | modification | 3164 | master_bulk_upload | 0
9109 | SERUM_BO3_015b-t5 | modification | 3165 | master_bulk_upload | 0
9115 | HPHT_304 | modification | 3178 | master_bulk_upload | 0
9117 | HPHT_304 | modification | 3179 | master_bulk_upload | 0
9126 | HPHT_319 | modification | 3185 | master_bulk_upload | 0
9138 | HPHT_316 | modification | 3192 | master_bulk_upload | 0
9184 | SERUM_BO3_025a-t5 | modification | 3205 | master_bulk_upload | 0
9185 | SERUM_BO3_027c-t5 | modification | 3216 | master_bulk_upload | 0
9186 | SERUM_BO3_023a-t5 | modification | 3222 | master_bulk_upload | 0
9187 | SERUM_BO3_029a-t5 | modification | 3223 | master_bulk_upload | 0
9188 | SERUM_BO3_021a-t5 | modification | 3229 | master_bulk_upload | 0
9195 | SERUM_BO3_019c-t5 | modification | 3241 | master_bulk_upload | 0
9282 | HPHT_314 | modification | 3242 | master_bulk_upload | 0
9283 | HPHT_313 | modification | 3247 | master_bulk_upload | 0
9285 | CF_027-5 | modification | 3248 | master_bulk_upload | 0
9287 | HPHT_315 | modification | 3249 | master_bulk_upload | 0
9289 | HPHT_309 | modification | 3250 | master_bulk_upload | 0
9296 | HPHT_317 | modification | 3256 | master_bulk_upload | 0
9311 | HPHT_307 | observation | 3266 | master_bulk_upload | 0
9312 | HPHT_307 | modification | 3266 | master_bulk_upload | 0
9313 | HPHT_308 | observation | 3267 | master_bulk_upload | 0
9314 | HPHT_308 | modification | 3267 | master_bulk_upload | 0
9316 | CF_027-5 | modification | 3268 | master_bulk_upload | 0
9318 | HPHT_312 | modification | 3269 | master_bulk_upload | 0
9320 | HPHT_326 | modification | 3270 | master_bulk_upload | 0
9322 | HPHT_304 | modification | 3271 | master_bulk_upload | 0
9338 | HPHT_310 | modification | 3286 | master_bulk_upload | 0

### joined-zero (report only)
id | experiment_id | note_type | result_id | created_by | note_text
5537 | HPHT_229 | observation | 1924 | reclassify_notes_020 | 0; Gas, liquid
5563 | SERUM_CatalystCation_007a-t3 | result_note | 2226 | reclassify_notes_020 | 0; Liq
5564 | SERUM_CatalystCation_005a-t3 | result_note | 2229 | reclassify_notes_020 | 0; Liq
5565 | SERUM_CatalystCation_005b-t3 | result_note | 2230 | reclassify_notes_020 | 0; Liq
5566 | SERUM_CatalystCation_005c-t3 | result_note | 2231 | reclassify_notes_020 | 0; Liq
5569 | SERUM_Catalyst_011c-t1 | result_note | 2341 | reclassify_notes_020 | 0; Gas, GC-A, DI
5645 | HPHT_229 | observation | 1924 | master_bulk_upload | 0; Gas, liquid
5930 | SERUM_CatalystCation_007a-t3 | observation | 2226 | master_bulk_upload | 0; Liq
5933 | SERUM_CatalystCation_005a-t3 | observation | 2229 | master_bulk_upload | 0; Liq
5934 | SERUM_CatalystCation_005b-t3 | observation | 2230 | master_bulk_upload | 0; Liq
5935 | SERUM_CatalystCation_005c-t3 | observation | 2231 | master_bulk_upload | 0; Liq
6056 | SERUM_Catalyst_011c-t1 | observation | 2341 | master_bulk_upload | 0; Gas, GC-A, DI
8443 | HPHT_297 | observation | 3040 | master_bulk_upload | low P gas, cold liquid; 0

### other-author / other-type zero (report only)
(none)

### NULL-author zero (report only)
id | experiment_id | note_type | result_id | created_by | note_text
3337 | CF_020-5_Puddle | description | None | None | 0

### nan notes (report only)
id | experiment_id | note_type | result_id | created_by | note_text
619 | OTHER_JW_002 | observation | None | None | nan
620 | OTHER_JW_003 | observation | None | None | nan
621 | OTHER_JW_004 | observation | None | None | nan
622 | OTHER_JW_001 | observation | None | None | nan
2630 | SERUM_Catalyst_009a-t1 | observation | None | None | nan
2631 | SERUM_Catalyst_009b-t1 | observation | None | None | nan
2632 | SERUM_Catalyst_009c-t1 | observation | None | None | nan
4104 | SERUM_waterrock_001a-t1 | observation | None | None | nan
4105 | SERUM_waterrock_001b-t1 | observation | None | None | nan
4106 | SERUM_waterrock_001c-t1 | observation | None | None | nan
4107 | SERUM_waterrock_001a-t7 | observation | None | None | nan
4108 | SERUM_waterrock_001b-t7 | observation | None | None | nan
4109 | SERUM_waterrock_001c-t7 | observation | None | None | nan
4110 | SERUM_waterrock_001a-t20 | observation | None | None | nan
4111 | SERUM_waterrock_001b-t20 | observation | None | None | nan
4112 | SERUM_waterrock_001c-t20 | observation | None | None | nan
4113 | SERUM_waterrock_002-t1 | observation | None | None | nan
4114 | SERUM_waterrock_002-t7 | observation | None | None | nan
4115 | SERUM_waterrock_002-t20 | observation | None | None | nan
4116 | SERUM_waterrock_003a-t1 | observation | None | None | nan
4117 | SERUM_waterrock_003b-t1 | observation | None | None | nan
4118 | SERUM_waterrock_003c-t1 | observation | None | None | nan
4119 | SERUM_waterrock_003a-t7 | observation | None | None | nan
4120 | SERUM_waterrock_003b-t7 | observation | None | None | nan
4121 | SERUM_waterrock_003c-t7 | observation | None | None | nan
4122 | SERUM_waterrock_003a-t20 | observation | None | None | nan
4123 | SERUM_waterrock_003b-t20 | observation | None | None | nan
4124 | SERUM_waterrock_003c-t20 | observation | None | None | nan
4125 | SERUM_waterrock_004-t1 | observation | None | None | nan
4126 | SERUM_waterrock_004-t7 | observation | None | None | nan
4127 | SERUM_waterrock_004-t20 | observation | None | None | nan

before: {'notes_total': 5401, 'targets': 186, 'snapshots_by_022': 0}

Dry run — pass --apply to commit changes.
```
