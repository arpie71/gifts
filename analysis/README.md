# Analysis layer

Builds the analysis file and the descriptive statistics used in `paper/`.
Run from the repo root, after `parseandclean_new.py` has refreshed `cleaned/`:

```
python analysis/build_analysis_data.py   # -> analysis/output/
python analysis/descriptives.py          # -> paper/tables, paper/figures, map HTML
```

A Stata version of the main descriptives is in `analysis/descriptives.do`.

## Outputs (`analysis/output/`)

| File | Contents |
|---|---|
| `gifts_analysis.csv` | One row per gift. Adds `gift_id`, `agency`, `agency_std` (spelling variants merged), `branch`, `giver_country`, `giver_country_qid`, `giver_iso3`, `giver_country_source`, `giver_role`, `estval_num`, `travel`, `recd_year`, `recip_has_qid`, `giver_has_qid`. |
| `edges_person.csv` | Giver–recipient pairs (both with QIDs): gift count, total value, first and last year. For the network view. |
| `country_year_panel.csv` | Balanced country × year panel: gifts, value, distinct recipients, `any_gift`. For the map view. |
| `summary.json`, `paper_numbers.json` | The numbers quoted in the paper. |
| `map_gifts_by_country.html` | Interactive choropleth with a year slider (prototype for the Streamlit map). |

## How the added variables are built

- **agency / branch**: from the Federal Register XML. Since 2001, each agency's table has a `<TTITLE>`. In 1999–2000 the agency is a one-cell row. Rows are walked in the same order as `download_data.py`, so they line up with the `Unnamed: 0` index. Branch is a rule-based grouping (`BRANCH_RULES`).
- **giver_country**: first country named in the giver text, else the giver's Wikidata P27 (citizenship) when it is unique. Regime items are folded into the continuing state (`CANONICAL`). International organizations get no country. ISO3 codes come from Wikidata P298 and are cached in `files/country_iso3.csv`.
- **giver_role**: keyword rules on honorifics and titles (`ROLE_RULES`).
- **recd_year**: year of the receipt date where it parses, else the report year. Use it for timing questions, because some reports are backlogged (e.g., the 2015 Senate report).

## Recipient profiles and giver–recipient similarity (`descriptives.py`)

- **tab_recip_profile**: linked recipients by branch, from `files/wikidata_claims.csv`: gender, birth year, military career (P410 rank or a military P106 occupation), diplomat/law occupation groups (`OCC_RULES`), party membership (P102), and schooling outside the US.
- **tab_shared**: for each gift with both parties linked, whether giver and recipient share gender, professional career (excluding "politician"), military service, birth cohort (±5 years), country or institution of education, or employer. Observed rates are compared with 500 random pairings of givers within year and within branch × year (seeded). Panel B keeps only executive agencies (no White House or Congress).
- **Backgrounds (tab_bg_*, tab_office_matrix)**: each person's primary background (Political / Technical / Business / Military / Spouse-family) is the kind of work with the most calendar years in dated P39 positions and P108 employers (`POSITION_RULES`, `EMP_RULES`; undated job = 4 years; general/flag rank = 20; business occupation = 8). People with no classifiable job fall back to the earlier Stata occupation/education codes (`TECH_JOB`, `TECH_EDU`, `TECH_POS`), which are also reported as overlapping indicators. Offices at the time of the gift come from the reporting agency (recipients) and the giver's title (`GIVER_OFFICE_RULES`). Gift types are keyword-coded (`ITEM_RULES`). Employer types (P31) are cached in `files/employer_types.csv`.
- The country of each school (P17) is cached in `files/institution_country.csv`. US professional military education is matched by name (`PME`).

The scripts call the Wikidata API only for codes and labels not already cached in `files/`.
