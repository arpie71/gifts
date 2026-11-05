# Revised analysis: bureaucratic careers, revolving doors, and institutional influence

This directory re-analyzes the foreign-gifts data for the revised theory in
`paper/gifts_living_data.tex` (careers, structural embedding, bureaucratic influence). Gifts are **not** the
outcome of interest: each gift record is treated as an observed interaction among a U.S. official, a
reporting agency, a foreign official, and a foreign government.

**The original analysis is untouched.** Nothing outside `analysis_revised/` was modified. The revised
scripts read `analysis/output/gifts_analysis.csv` and the Wikidata files in `files/`, and write only here.
`00_reproduce_original.sh` re-runs the original pipeline in a scratch copy and confirms that it
reproduces exactly (see `REPLICATION_LOG.md`).

| Start here | |
|---|---|
| `EMPIRICAL_MEMO.md` | Which theoretical claims the data support, which stay descriptive, and which cannot be tested |
| `CODEBOOK.md` | Every variable in every dataset (generated; fails if a column is undocumented) |
| `REPLICATION_LOG.md` | Software, packages, seeds, inputs, caches, commands, run times |

## Scripts (run in order; `run_all.sh` does 02-06 and rebuilds the paper)

| Script | Does |
|---|---|
| `00_reproduce_original.sh` | Reproduces the original outputs in a scratch copy and diffs them |
| `01b_fetch_missing_claims.py` | Wikidata claims for linked people missing from the snapshot -> `cache/claims_supplement.csv` |
| `01_fetch_position_metadata.py` | Organization, country, and type of every position/employer -> `cache/position_meta.csv` |
| `02_build_data.py` | Linkage audit, career spells, person-year and organization-year panels, tie and mover files, network measures -> `data/` |
| `03_models.py` | All tables and models -> `output/tables/`, `output/numbers.json` |
| `04_figures.py` | Figures -> `output/figures/` |
| `05_codebook.py` | `CODEBOOK.md` |
| `06_paper_outputs.py` | Paper tables/figures for the revised empirical section -> `output/paper/`, copied to `paper/tables/rev_*.tex` and `paper/figures/rev_*.pdf` (new names only), plus `output/paper/paper_numbers_revised.json` |
| `common.py` | Paths, sector rules, prominence rules, FE estimators, table writer |

## Outputs

**Tables** (`output/tables/`, `.tex` plus a `.csv` twin). Each note states its evidence type.

| Table | Question |
|---|---|
| `tab_audit_status`, `tab_audit_checks`, `tab_audit_career`, `tab_audit_by_group` | Identifier linkage audit |
| `tab_career_desc` | Career duration and mobility by prominence group |
| `tab_transitions` | Sector-to-sector career moves |
| `tab_network_periods` | Network structure and persistence by administration |
| `tab_main_career` | Career duration/mobility and the extent of interaction (between and within person) |
| `tab_brokerage` | Career mobility and brokerage, holding degree fixed |
| `tab_selection` | Pre-entry careers and network position at entry (selection) |
| `tab_event_study` | Interactions before and after career transitions (stacked event study) |
| `tab_hazard` | Organizational exit and career transitions (discrete-time hazards) |
| `tab_org_continuity` | Personnel turnover and agencies' tie continuity (agency-year) |
| `tab_tie_memory` | Do agencies keep a tie when its carriers leave? (agency x country x year) |
| `tab_movers` | Do foreign contacts follow the person or stay with the office? |
| `tab_permutation` | Mobility-brokerage association against degree-preserving null graphs |
| `tab_brokers_ordinary`, `tab_brokers_foreign` | Who brokers below cabinet level; foreign intermediaries |
| `tab_robust_samples`, `tab_robust_transitions`, `tab_robust_windows` | Robustness: excluding prominent people, transition definitions, network windows |

**Figures** (`output/figures/`): `fig_linkage` (share of records that can be followed, by year),
`fig_pathways` (career pathways), `fig_career_timelines` (careers of multi-sector, non-cabinet recipients),
`fig_agency_network` (agencies linked by shared personnel), `fig_personnel_movement` (turnover, moves,
continuity by year), `fig_network_change` (network change over time, with events), `fig_event_study`,
and `fig_permutation`.

## Change log (relative to the original analysis)

Additions only; no original variable, table, or figure was removed or altered.

1. **New environment.** `/home/arpie/envs/revised` with networkx, statsmodels, and scipy, which
   `giftsenv` and `envs/base` lack. The original scripts also run in it.
2. **Supplementary Wikidata claims.** `scripts/wiki_properties.py` enriches only QIDs listed in
   `masterwiki_new.csv`. QIDs assigned by the bare-office rule (`ROLES` in `parseandclean_new.py`) were
   never enriched: George W. Bush (888 records) and Laura Bush (445) had no claims. The revised analysis
   adds them from `cache/claims_supplement.csv`. **Suggested upstream fix:** add the `ROLES` QIDs to the ID
   list in `wiki_properties.py`.
3. **Entity types.** 378 linked giver QIDs (1,108 records) and 4 recipient QIDs are not humans: states,
   ministries, IOs, and 8 Wikimedia categories or flag designs, which are link errors. Person-level
   panels use human items only; organizations remain partners (`org:` ids).
4. **Implausible links.** 23 people whose Wikidata dates cannot match the record (e.g. died before the
   gift) are flagged in `data/audit_implausible_links.csv`. Their gift records are kept, but their
   career measures are not used. These are candidates for correction in `masterwiki_new.csv`.
5. **Career spells.** Built from P39 and P108 with sector rules (`common.SECTOR_RULES`), organization
   (P2389 / P361), and country (P17 / P1001). Open-ended spells are closed at the start of the next spell
   in another organization. Generic labels with no organization are Unclassified and do not count as
   organizations or transitions.
6. **Panels.** Person-year (recipients, givers), organization-year, tie-year, and mover episodes. All
   career and network predictors are lagged.
7. **Prominence groups.** Cabinet level and above / family of officials / legislators / agency,
   military, and diplomatic staff, used to show results without world leaders and senior officials.
8. **Archive.** `run_all.sh` renames earlier `data/` and `output/` folders into `archive/` instead of
   overwriting them.

## The paper (revised empirical section, 2026-11-05)

`paper/gifts_living_data.tex`:
* **Section 7, "Empirical Analysis: Position, Organization, and Brokerage"**, has five parts: data and measures; position versus career; organizational continuity after turnover; positional brokerage; network change over time. It ends with the evidentiary status of each claim.
* **Appendix A** covers variables and sample construction. **Appendix B** is the claim-to-evidence map.
* **Appendix C** holds the former sections "Who Receives Foreign Gifts?", "What Do Givers and Recipients Share?", "Technical, Business, and Political Backgrounds", and "Office Versus Officeholder", moved unchanged and demoted to subsections. Their labels still resolve.
* The subsection "Wikidata Updates What the Gift Record Cannot" moved to the end of Section 8 ("The Wikidata Identifier as a Linking Key").
* The pre-revision draft and PDF are kept as `paper/gifts_living_data_pre_empirical_revision.{tex,pdf}`.
* One preamble fix was needed to compile: the `\title{...}` brace was unclosed (a trailing `\\` with the subtitle removed), already so in the committed version.
