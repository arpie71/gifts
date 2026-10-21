# Foreign gifts dashboard

A Streamlit app built on the pipeline output `analysis/output/gifts_analysis.csv`.
To refresh the data, re-run the pipeline and reload the page.

```
cd dashboard
../../giftsenv/bin/streamlit run app.py
```

Run it from `dashboard/` so Streamlit picks up `.streamlit/config.toml`.

## Pages

| Page | What it shows |
|---|---|
| World map | Choropleth by number of gifts or total value: one year, the total over a range, or an animation with a play button. **Build GIF** renders an animated GIF to download. |
| Country heatmap | Countries × years. Shows the top 10 for the selected years, or a list of up to 10 countries you choose. |
| Top givers | Top individuals or countries for one year or all selected years, plus the top giver in each year. Links go to Wikidata. |
| Network | **World cartogram** (default): a contiguous cartogram where each country's area is resized by its total gifts to U.S. officials (log, square-root, or raw scaling), with flow lines to the U.S. sized by that total. Or a graph of giving countries linked to U.S. branches, agencies, or individual recipients, in a ring or force-directed layout. |
| Who gives to whom | Giver type × recipient branch, as row shares or counts. |
| Country profile | One country: totals, gifts by year, recipient branches, top givers, top U.S. recipients, and most valuable items. |
| Gift explorer | Searchable, filterable list of individual gifts, with CSV download. |

The sidebar filters (year basis, year range, recipient branch, measure) apply to every page.

## Files

- `app.py`: the pages and sidebar.
- `data.py`: loading (cached) and aggregations.
- `charts.py`: plotly figures, including the network layouts.
- `cartogram.py`: contiguous cartogram using the rubber-sheet algorithm of Dougenik, Chrisman & Niemeyer (1985), vectorized in numpy. Each new filter or scaling setting takes about 12 seconds the first time; results are then cached.
- `gifmap.py`: GIF renderer using Pillow and Natural Earth 1:50m boundaries (`assets/`). It needs no browser.

Requirements in `giftsenv`: streamlit, pandas, plotly, networkx, pillow.
