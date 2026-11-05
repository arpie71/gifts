# Replication log: revised analysis

Built 2026-11-05. Repository commit at build: `1bf9c30` (working tree had uncommitted edits to the
paper and `analysis/descriptives.py`; untracked inputs `files/employer_types.csv` and
`files/institution_country.csv`. Commit these before archiving a release, since the revised analysis reads
`files/employer_types.csv`).

## Software

| Item | Version |
|---|---|
| OS | Linux 6.18.54.1-microsoft-standard-WSL2 (WSL2 on Windows) |
| Python | 3.12.3, virtual environment `/home/arpie/envs/revised` (created for this analysis; the existing `giftsenv` and `envs/base` were not modified) |
| Packages | pinned in `analysis_revised/requirements_revised.txt` (pandas 3.0.2, numpy 2.4.4, networkx 3.7, statsmodels 0.15.0, scipy 1.18.1, matplotlib 3.10.8, requests 2.34.2, beautifulsoup4 4.15.0, plotly 7.1.0) |

To recreate the environment:

```
python3 -m venv /home/arpie/envs/revised
/home/arpie/envs/revised/bin/pip install -r analysis_revised/requirements_revised.txt
```

## Random seeds

All randomness uses `SEED = 20261105` (`analysis_revised/common.py`):
Louvain community detection (networkx `seed=`), degree-preserving rewiring (200 per administration),
label permutations (200), placebo event assignment (200), sign-flip tests for movers (5,000), and the
spring layout of `fig_agency_network`. numpy's `default_rng(SEED)` is created once per test, so results
do not depend on the order of earlier calls within the script.

## Inputs (read only)

| File | Role |
|---|---|
| `analysis/output/gifts_analysis.csv` | original analysis file (built by `analysis/build_analysis_data.py`) |
| `files/wikidata_claims.csv` | Wikidata statements snapshot (from `scripts/wiki_properties.py`) |
| `files/employer_types.csv` | P31 of employers (cached by `analysis/descriptives.py`) |
| `files/masterwiki_new.csv` | name -> QID lookup (audit only) |
| `files/country_iso3.csv` | country QIDs (to recognize P1001 countries) |
| `parseandclean_new.py` | read (not run) to list the bare offices in `ROLES` |

SHA-256 hashes of every input and cache at build time are in `analysis_revised/logs/input_checksums.txt`.

## Caches created by this analysis (network access, Wikidata API, read only)

| File | Script | Retrieved | Contents |
|---|---|---|---|
| `cache/position_meta.csv` | `01_fetch_position_metadata.py` | 2026-11-05 | P31, P279, P17, P1001, P2389, P361 (+ labels) for all 4,025 position/employer items |
| `cache/claims_supplement.csv` | `01b_fetch_missing_claims.py` | 2026-11-05 | claims for 5 linked QIDs absent from the snapshot (3 returned: George W. Bush, Laura Bush, Raymond Joseph) |

The first metadata pass hit HTTP 429 rate limits and 13 batches failed. The script was changed so a failed
batch is never cached as empty, and the next two passes filled the gaps (`logs/01_fetch*.log`). Reruns
now make no network calls unless `--fetch` is given. Wikidata changes over time, so a rerun with
`--fetch` on another date can change results; the committed caches are the snapshot behind every
reported number.

## Commands (from the repo root)

```
# 0. Reproduce the original analysis in a scratch copy and compare outputs (does not modify the repo)
bash analysis_revised/00_reproduce_original.sh

# 1. (optional) refresh Wikidata caches
/home/arpie/envs/revised/bin/python analysis_revised/01b_fetch_missing_claims.py
/home/arpie/envs/revised/bin/python analysis_revised/01_fetch_position_metadata.py

# 2-5. Build data, estimate models, draw figures, write codebook
bash analysis_revised/run_all.sh            # add --fetch to run step 1 as well
```

From raw data, run the original pipeline first: `download_data.py` (only for new report years) ->
`parseandclean_new.py` -> `scripts/wiki_properties.py` (only to refresh claims) ->
`analysis/build_analysis_data.py`, then the commands above.

Run times on this machine: `02_build_data.py` about 2.5 minutes; `03_models.py` about 20 minutes, mostly the
200 placebo event stacks and 1,400 rewired graphs; `04_figures.py` under a minute.

## Reproduction of the original results (step 0)

Run on 2026-11-05 with the revised environment (`logs/00_reproduce_original.log`):

* byte-identical: `gifts_analysis.csv`, `edges_person.csv`, `country_year_panel.csv`, `summary.json`,
  `paper_numbers.json`, all 15 `paper/tables/*.tex`, and all 6 figure PNGs;
* differ only in embedded metadata: the 6 figure PDFs (creation date) and `map_gifts_by_country.html`
  (plotly random div ids).

The original analysis therefore reproduces exactly. Its scripts need `requests`, `beautifulsoup4`, and
`plotly`, which were installed in the new environment; `envs/base` lacks `plotly`.

## Intermediate and output files

* `analysis_revised/data/`: analysis datasets and audit files (see `CODEBOOK.md`)
* `analysis_revised/output/tables/`: LaTeX tables, each with a CSV twin
* `analysis_revised/output/figures/`: PDF + PNG, each with a CSV of the plotted values
* `analysis_revised/output/numbers.json`: every number quoted in `EMPIRICAL_MEMO.md`
* `analysis_revised/logs/`: run logs, `checksums.txt` (SHA-256 of all data and table CSVs from the last run)
* `analysis_revised/archive/`: earlier builds renamed by `run_all.sh` (never deleted)

## Estimator notes

* Poisson PML and OLS with high-dimensional fixed effects are implemented in `common.py` (IRLS with
  alternating-projection demeaning, as in `ppmlhdfe`/`reghdfe`). They were checked against statsmodels
  GLM/OLS with dummy variables on simulated data: coefficients agree to 5 decimals. Clustered SEs are about
  3% smaller because FE nested in clusters are not counted in the small-sample correction (the `reghdfe`
  convention).
* Singleton groups and groups whose outcome is always zero are dropped before PPML estimation.
* Discrete-time hazards: statsmodels `Logit` with year dummies, SEs clustered by person.
