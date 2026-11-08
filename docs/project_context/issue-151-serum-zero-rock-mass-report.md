# Serum background vials: proposed list for review (issue #151)

**Status:** waiting on the experimenters. Nothing in the database has been changed.
**Data:** production backup `docs/sample_data/experiments_20261106_000002.sql` (alembic `f3b7c2a9d4e1`, 2262 experiments, newest created 2026-11-05), restored into a throwaway database on 2026-11-08 and dropped afterwards. 1636 Serum vials (all three type spellings).
**Related:** #152 (formal `is_background` flag), #144 (H₂ background subtraction).

## Why this list

Nothing in the database says "this vial is a background". It is inferred from signals that disagree. Each row below gives the number of vials with the signal, and how many of them the experimenters described as a background ("bg", "background", "no rock", "blank"):

| Signal | Vials | Described as background |
|---|---|---|
| Rock mass 0 | 313 | 286 |
| Rock mass empty | 187 | 78 |
| Sample ID empty | 334 | 91 |
| Sample ID "Sand" | 1 | 0 |
| Description says background | 439 | 439 |

Rock mass 0 usually means a background. An empty sample ID usually just means it was never filled in. "No rock" and "background" are also different facts: the SERUM_MetalBuffer and SERUM_CrTi series (section C) have no rock by design but are samples. #152 proposes an explicit `is_background` flag. This list is what the flag would be set from, once confirmed.

## What we need from the experimenters

1. **Section A (364 vials): confirm or strike.** Each series' groups are described as backgrounds and have no rock mass. A "yes" per series is enough. Strike any group that isn't a background.
2. **Section B (75 vials): was rock actually added?** These are described as backgrounds but have a rock mass, mostly 1 g, and 66 of them report a g/t yield. If no rock went in, the rock mass should be cleared. If the 1 g is a deliberate basis (for example "bg with 5% rock dissolution"), say so.
3. **Section C (136 vials): background or missing rock mass?** These have rock mass 0 or empty but no background wording. Fill in the last column.

## A. Proposed backgrounds (described as background, rock mass 0 or empty)

| Series | Groups (number) | Vials | With H₂ |
|---|---|---|---|
| HPHT | 101 | 1 | 0 |
| SERUM_Al | 002 | 3 | 3 |
| SERUM_BO | 004, 006, 008, 010, 012, 014, 016, 018, 020 | 27 | 24 |
| SERUM_BO2 | 002, 004, 006, 008, 010, 012, 014, 016, 018, 020 | 30 | 29 |
| SERUM_BO3 | 002, 004, 006, 008, 010, 012, 014, 016, 018, 020, 022, 024, 026, 028, 030, 032, 034, 036, 038, 040, 042 | 63 | 57 |
| SERUM_Buffer | 002 | 4 | 4 |
| SERUM_Catalyst | 002, 004, 006, 008, 010, 012, 014, 016, 018, 020, 022, 024, 026, 028, 030, 032, 034, 036, 038, 040, 042, 044, 046, 48 | 72 | 60 |
| SERUM_CatalystCation | 002, 004, 006, 008 | 16 | 16 |
| SERUM_Cation | 016, 017, 018, 019, 020 | 5 | 5 |
| SERUM_cation | 022, 024, 026, 028, 030 | 11 | 11 |
| SERUM_Grain | 004, 006 | 4 | 2 |
| SERUM_JW | 019, 021, 047, 050, 053, 153, 154 | 7 | 0 |
| SERUM_MetalBuffer | 002, 004, 006, 008, 010, 012, 014, 016, 018, 020, 022, 024 | 68 | 46 |
| Serum_MP | 032, 033, 034, 035 | 4 | 0 |
| SERUM_P1Salt | 002, 004, 006, 008, 010, 012, 014, 016, 018 | 11 | 10 |
| SERUM_pH | 002, 004, 006 | 14 | 14 |
| SERUM_pHIS | 002, 004 | 6 | 4 |
| SERUM_Septa | 002, 004, 006 | 9 | 9 |
| SERUM_waterrock | 010, 012, 014, 016, 020, 024 | 9 | 9 |

Total: 129 groups, 364 vials (303 with H₂).

`HPHT_101` is typed Serum, so it appears here. Check whether its type is right. In SERUM_MetalBuffer, the even-numbered groups listed here are the backgrounds of the odd-numbered coupon samples in section C.

`SERUM_Catalyst_48` (in the SERUM_Catalyst row) is the background partner of SERUM_Catalyst_047. Its ID is missing the leading zero.

## B. Described as background, but rock mass is set

| Group | Vials | Letters | Rock mass | Has g/t | Description | Rock actually added? |
|---|---|---|---|---|---|---|
| OTHER_JW_005 | 1 | — | 1 g | no | Background Ammonia Check: 1mM NO3 | |
| SERUM_BO_002 | 3 | abc | 1 g | yes | BO, R1, #1,bg | |
| SERUM_Buffer_002 | 5 | ac | 1 g | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% Fe dissolution,… | |
| SERUM_Buffer_004 | 9 | abc | 1 g | yes | 20ml 0.01 M NaCl pH 9 boric acid borate buffer, 20% Fe dissolution, bg | |
| SERUM_Buffer_010 | 6 | abc | 1 g | yes | bg with 5% rock dissolution pH 6 phosphate buffer, 0.01M NaCl | |
| SERUM_Buffer_012 | 8 | abcde | 1 g | yes | bg with 10% rock dissolution pH 6 phosphate buffer, 0.01M NaCl | |
| SERUM_Buffer_014 | 3 | abc | 1 g | yes | bg with 5% rock dissolution pH 6 phosphate buffer, 0.01M NaCl | |
| SERUM_Catalyst_008 | 1 | — | 1 g | yes | 1% sodium molybdate, background | |
| SERUM_CatalystHighpH_002 | 6 | abc | 1 g | yes | background 20ml 0.01 M NaCl pH 12 with 1% Cu brine | |
| SERUM_CatalystHighpH_004 | 6 | abc | 1 g | yes | background 20ml 0.01 M NaCl pH 12 with 1% Ni brine | |
| SERUM_CatalystHighpH_006 | 6 | abc | 1 g | yes | background 20ml 0.01 M NaCl pH 12 with 1% Cr brine | |
| SERUM_CatalystHighpH_008 | 6 | abc | 1 g | yes | background 20ml 0.01 M NaCl pH 12 with 1% V brine | |
| SERUM_Chelator_002 | 1 | — | 1 g | yes | Citric Acid BG | |
| SERUM_Chelator_004 | 1 | — | 1 g | yes | Malic Acid BG | |
| SERUM_Chelator_006 | 1 | — | 1 g | yes | Glycine BG | |
| SERUM_Chelator_008 | 1 | — | 1 g | yes | EDTA BG | |
| SERUM_JW_110 | 1 | — | 0.4 g | no | no rock 1000ppm Zn control with NO3 | |
| SERUM_JW_111 | 1 | — | 0.4 g | no | no rock 1000ppm Zn control without NO3 | |
| SERUM_JW_112 | 1 | — | 0.4 g | no | no rock 100ppm Mo control with NO3 | |
| SERUM_JW_113 | 1 | — | 0.4 g | no | no rock 100ppm Mo control without NO3 | |
| SERUM_pH_002 | 1 | — | 1 g | yes | bg, pH 4, t35 (resealed t20) | |
| SERUM_SaltIS_002 | 3 | abc | 1 g | yes | bg 0.5M NaCl, 0.1M KCl. KCl x best ionic strength | |
| SERUM_SaltIS_004 | 3 | abc | 1 g | yes | bg 0.16M NaCl, 0.1M KCl. KCl x second best ionic strength | |

Total: 23 groups, 75 vials, 66 with a g/t yield.

## C. Rock mass 0 or empty, not described as background

The pairing hint compares an even-numbered group with the one before it. In most series the even-numbered group is the no-rock partner of an odd-numbered group with rock.

| Group | Vials | Letters | Rock mass | Pairing hint | Description | Background or missing rock mass? |
|---|---|---|---|---|---|---|
| SERUM_Chelator_010 | 1 | — | 0 ×1 | SERUM_Chelator_009 has rock | — | |
| SERUM_Chelator_012 | 1 | — | 0 ×1 | SERUM_Chelator_011 has rock | — | |
| SERUM_Chelator_014 | 1 | — | 0 ×1 | SERUM_Chelator_013 has rock | — | |
| SERUM_Chelator_016 | 1 | — | 0 ×1 | SERUM_Chelator_015 has rock | — | |
| SERUM_CrTi_001 | 5 | ab | empty ×5 | odd-numbered | Passivated Ti in CrCl3 | |
| SERUM_CrTi_002 | 5 | ab | empty ×5 | SERUM_CrTi_001 has no rock either | Unpassivated Ti in CrCl3 | |
| SERUM_CrTi_003 | 5 | ab | empty ×5 | odd-numbered | Passivated Ti in pH 3 water | |
| SERUM_CrTi_004 | 5 | ab | empty ×5 | SERUM_CrTi_003 has no rock either | Unpassivated Ti in pH 3 water | |
| SERUM_Dissolution_002 | 2 | ab | 0 ×2 | SERUM_Dissolution_001 has rock | — | |
| SERUM_MetalBuffer_001 | 7 | abc | empty ×7 | odd-numbered | SS316 coupon + 5% iron dissoution acetate/acetic … | |
| SERUM_MetalBuffer_003 | 6 | abc | empty ×6 | odd-numbered | SS316 coupon + 10% iron dissoution acetate/acetic… | |
| SERUM_MetalBuffer_005 | 9 | abc | empty ×9 | odd-numbered | SS316 coupon + 0.025M AlCl3 | |
| SERUM_MetalBuffer_007 | 9 | abc | empty ×9 | odd-numbered | SS316 coupon + 0.05M AlCl3 | |
| SERUM_MetalBuffer_009 | 6 | abc | empty ×6 | odd-numbered | hastelloy coupon + 5% iron dissoution acetate/ace… | |
| SERUM_MetalBuffer_011 | 6 | abc | empty ×6 | odd-numbered | hastelloy coupon + 10% iron dissoution acetate/ac… | |
| SERUM_MetalBuffer_013 | 7 | abc | empty ×7 | odd-numbered | hastelloy coupon + 0.025M AlCl3 | |
| SERUM_MetalBuffer_015 | 6 | abc | empty ×6 | odd-numbered | hastelloy coupon + 0.05M AlCl3 | |
| SERUM_MetalBuffer_017 | 6 | abc | empty ×6 | odd-numbered | Ti coupon + 5% iron dissoution acetate/acetic aci… | |
| SERUM_MetalBuffer_019 | 6 | abc | empty ×6 | odd-numbered | Ti coupon + 10% iron dissoution acetate/acetic ac… | |
| SERUM_MetalBuffer_021 | 6 | abc | empty ×6 | odd-numbered | Ti coupon + 0.025M AlCl3 | |
| SERUM_MetalBuffer_023 | 6 | abc | empty ×6 | odd-numbered | Ti coupon + 0.05M AlCl3 | |
| SERUM_MH_021 | 1 | — | empty ×1 | odd-numbered | 0.01mM NH4 | |
| SERUM_MH_022 | 1 | — | empty ×1 | SERUM_MH_021 has no rock either | 0.1mM NH4 | |
| SERUM_MH_023 | 1 | — | empty ×1 | odd-numbered | 0.01mM NH4 | |
| SERUM_MH_024 | 1 | — | empty ×1 | SERUM_MH_023 has no rock either | 0.1mM NH4 | |
| SERUM_MH_025 | 1 | — | empty ×1 | odd-numbered | pH 4, 50mM Nitrate Control | |
| SERUM_MH_026 | 1 | — | empty ×1 | SERUM_MH_025 has no rock either | pH 7, 50mM Nitrate Control | |
| SERUM_MH_046 | 1 | — | 0 ×1 | SERUM_MH_045 has rock | 5000ppm Ni Control | |
| SERUM_MH_049 | 1 | — | 0 ×1 | odd-numbered | 1M KCl+H2SO4 Quench Control | |
| SERUM_MH_053 | 1 | — | 0 ×1 | odd-numbered | 0.1mM NH4OH Spiked 1.0M KCl+H2SO4 Quench Control | |
| SERUM_MP_006 | 1 | — | 0 ×1 | SERUM_MP_005 has rock | 0.2g CaO control | |
| Serum_MP_024 | 1 | — | 0 ×1 | Serum_MP_023 has rock | 2.5mL HCl, 2.5mL DI. Additives scaled down 10x HP… | |
| Serum_MP_026 | 1 | — | 0 ×1 | Serum_MP_025 has rock | 2.5mL HCl, 2.5mL DI | |
| SERUM_MP_049 | 1 | — | 0 ×1 | odd-numbered | water+ilmenite | |
| SERUM_P1Salt_000 | 4 | abc | 0 ×4 | — | DI water | |
| SERUM_pH_005 | 3 | abc | 0 ×3 | odd-numbered | pH 12, t35 (resealed t20), r1 | |
| SERUM_waterrock_002 | 4 | — | 0 ×3; empty ×1 | SERUM_waterrock_001 has rock | — | |
| SERUM_waterrock_004 | 4 | — | 0 ×3; empty ×1 | SERUM_waterrock_003 has rock | — | |
| SERUM_waterrock_007 | 1 | — | 0 ×1 | odd-numbered | — | |
| VAE-30 | 1 | — | empty ×1 | — | — | |

Total: 40 groups, 136 vials (109 with rock mass empty).

Notes on C:

- **SERUM_MetalBuffer_001–023 (odd) and SERUM_CrTi_001–004** are metal-coupon and titanium tests; the even-numbered MetalBuffer groups are their backgrounds (section A). An empty rock mass is probably correct there. They are samples, not backgrounds, and they are listed only so the answer is on record.
- **SERUM_Chelator_010–016, SERUM_waterrock_002/004, SERUM_Dissolution_002** follow the even-numbered no-rock pattern but have no description. They are probably backgrounds.
- **SERUM_pH_005a/b/c-t35** belong to a sample series (rock 1 g on every other timepoint). Their 0 is probably a missing entry.

## D. Groups where background and rock-bearing vials share a group

In these four groups some vials have rock mass and some don't, so the group's H₂ mean mixes them.

| Group | Vial | Letter | Rock mass | Described as background? | Description |
|---|---|---|---|---|---|
| SERUM_Buffer_002 | SERUM_Buffer_002a-t1 | a | 1 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002a-t20 | a | 1 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002a-t7 | a | 1 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002b-t1 | b | 0 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002b-t20 | b | 0 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002b-t7 | b | 0 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002c-t1 | c | 0 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002c-t20 | c | 1 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Buffer_002 | SERUM_Buffer_002c-t7 | c | 1 | yes | 20ml 0.01 M NaCl pH 4 acetic acid acetate buffer, 20% … |
| SERUM_Catalyst_008 | SERUM_Catalyst_008-t1 | — | 0 | yes | 1% sodium molybdate, background |
| SERUM_Catalyst_008 | SERUM_Catalyst_008-t20 | — | 1 | yes | 1% sodium molybdate, background |
| SERUM_Catalyst_008 | SERUM_Catalyst_008-t3 | — | 0 | yes | 1% sodium molybdate, background |
| SERUM_pH_002 | SERUM_pH_002-t1 | — | 0 | yes | bg, pH 4, t1 |
| SERUM_pH_002 | SERUM_pH_002-t20 | — | 0 | yes | bg, pH 4, t20 |
| SERUM_pH_002 | SERUM_pH_002-t3 | — | 0 | yes | bg, pH 4, t3 |
| SERUM_pH_002 | SERUM_pH_002-t35 | — | 1 | yes | bg, pH 4, t35 (resealed t20) |
| SERUM_pH_002 | SERUM_pH_002-t7 | — | 0 | yes | bg, pH 4, t7 |
| SERUM_pH_005 | SERUM_pH_005a-t1 | a | 1 | no | pH 12, t1, r1 |
| SERUM_pH_005 | SERUM_pH_005a-t20 | a | 1 | no | pH 12, t20, r1 |
| SERUM_pH_005 | SERUM_pH_005a-t3 | a | 1 | no | pH 12, t3, r1 |
| SERUM_pH_005 | SERUM_pH_005a-t35 | a | 0 | no | pH 12, t35 (resealed t20), r1 |
| SERUM_pH_005 | SERUM_pH_005a-t7 | a | 1 | no | pH 12, t7, r1 |
| SERUM_pH_005 | SERUM_pH_005b-t1 | b | 1 | no | pH 12, t1, r2 |
| SERUM_pH_005 | SERUM_pH_005b-t20 | b | 1 | no | pH 12, t20, r2 |
| SERUM_pH_005 | SERUM_pH_005b-t3 | b | 1 | no | pH 12, t3, r2 |
| SERUM_pH_005 | SERUM_pH_005b-t35 | b | 0 | no | pH 12, t35 (resealed t20), r2 |
| SERUM_pH_005 | SERUM_pH_005b-t7 | b | 1 | no | pH 12, t7, r2 |
| SERUM_pH_005 | SERUM_pH_005c-t1 | c | 1 | no | pH 12, t1, r3 |
| SERUM_pH_005 | SERUM_pH_005c-t20 | c | 1 | no | pH 12, t20, r3 |
| SERUM_pH_005 | SERUM_pH_005c-t3 | c | 1 | no | pH 12, t3, r3 |
| SERUM_pH_005 | SERUM_pH_005c-t35 | c | 0 | no | pH 12, t35 (resealed t20), r3 |
| SERUM_pH_005 | SERUM_pH_005c-t7 | c | 1 | no | pH 12, t7, r3 |

**Effect on the group mean** (day buckets containing a vial with rock mass 0 or empty; outliers excluded, as in `v_results_scalar_rollup`):

| Group | Day | Vials (of which rock 0 or empty) | Mean H₂ µmol, all | Mean H₂ µmol, rock vials only |
|---|---|---|---|---|
| SERUM_Buffer_002 | 1 | 3 (2) | 0 | 0 |
| SERUM_Buffer_002 | 7 | 3 (1) | 0.0236 | 0.0217 |
| SERUM_Buffer_002 | 20 | 3 (1) | 0.0517 | 0.0499 |
| SERUM_Catalyst_008 | 1 | 1 (1) | 0.7 | — |
| SERUM_Catalyst_008 | 3 | 1 (1) | 0 | — |
| SERUM_pH_002 | 1 | 1 (1) | 0 | — |
| SERUM_pH_002 | 3 | 1 (1) | 0 | — |
| SERUM_pH_002 | 7 | 1 (1) | 0.0236 | — |
| SERUM_pH_002 | 20 | 1 (1) | 0.104 | — |
| SERUM_pH_005 | 35 | 3 (3) | 0.0768 | — |

- **SERUM_Buffer_002, SERUM_Catalyst_008 and SERUM_pH_002 are background series** by their descriptions. The odd vials are the ones with rock mass 1 g (Buffer_002a and c, Catalyst_008-t20, pH_002-t35), and they appear in section B. Only SERUM_Buffer_002 actually mixes values within a day: +9% on day 7 and +4% on day 20.
- **SERUM_pH_005 is a sample series.** Its three t35 vials have rock mass 0 and are the only vials on day 35, so the day-35 group value rests on them alone. They appear in section C.

## Outside Serum

Rock mass 0 also appears on 35 HPHT, 10 Core Flood, 8 Other and 1 Autoclave conditions rows. HPHT sand controls (for example HPHT_297, sample "Sand", 5 g) have a real solid mass, so rock mass can't identify HPHT backgrounds at all. These are left to #152.

## After the answers

- **Rock mass corrections** (sections B and C): Conditions tab or the new-experiments bulk upload. Conditions recalculate on save, so g/t and Fe²⁺ yields update.
- **Background flag** (#152): once the field exists, a backfill script with a dry run sets it on the confirmed vials. The rollups then leave backgrounds out of sample means, and the #144 picker offers them as backgrounds.

## Query

Read-only. A vial is "described as background" when its description note matches `\m(bg|bkg)\M|background|blank|no rock|rock[- ]free|without rock` (case-insensitive). The pairing hint and the per-series grouping are done in post-processing.

```sql
SELECT COALESCE(e.base_experiment_id, e.experiment_id) AS grp, e.experiment_id, e.replicate_label,
       e.sample_id, e.is_outlier, ec.rock_mass_g,
       COALESCE((SELECT string_agg(n.note_text, ' ' ORDER BY n.id) FROM experiment_notes n
                 WHERE n.experiment_fk = e.id AND n.note_type = 'description'), '') AS descr,
       EXISTS (SELECT 1 FROM experimental_results er JOIN scalar_results sr ON sr.result_id = er.id
               WHERE er.experiment_fk = e.id AND er.is_primary_timepoint_result
                 AND sr.h2_concentration IS NOT NULL) AS has_h2
FROM experiments e JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE lower(regexp_replace(btrim(ec.experiment_type), '\s+', ' ', 'g')) IN ('serum', 'serum vial')
ORDER BY 1, 2;
```
