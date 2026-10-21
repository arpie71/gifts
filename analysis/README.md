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

The scripts call the Wikidata API only for codes and labels not already cached in `files/`.
