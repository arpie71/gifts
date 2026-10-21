"""Foreign Gifts to U.S. Federal Officials — Streamlit dashboard.

Run from the repo root:
    ../giftsenv/bin/streamlit run dashboard/app.py
"""

import pandas as pd
import streamlit as st

import cartogram
import charts
import gifmap
from data import (BRANCH_ORDER, METRICS, ROLE_ORDER, US_LEVELS, country_totals, country_year,
                  data_mtime, filtered, fmt_metric, fmt_money, leader_by_year, load_gifts,
                  network_edges, top_givers, wikidata_url)

st.set_page_config(page_title="Foreign Gifts to U.S. Officials", page_icon="🎁", layout="wide")

GIFTS = load_gifts(data_mtime())
YEAR_MIN, YEAR_MAX = int(GIFTS["year"].min()), int(GIFTS["year"].max())


# ---------------------------------------------------------------------------
# Sidebar: filters shared by every page
# ---------------------------------------------------------------------------
def sidebar():
    with st.sidebar:
        st.header("Filters")
        basis = st.radio("Year basis", ["Report year", "Year received"], horizontal=True,
                         help="Report year is the Federal Register report the gift appeared in. "
                              "Some reports are backlogged (e.g. the 2015 Senate report), so "
                              "'Year received' is better for timing questions.")
        years = st.slider("Years", YEAR_MIN, YEAR_MAX, (YEAR_MIN, YEAR_MAX))
        branches = st.multiselect("Recipient branch", BRANCH_ORDER, placeholder="All branches")
        metric_label = st.radio("Measure", list(METRICS), horizontal=True)
        st.caption("Values are the agencies' estimates in nominal dollars.")
    year_col = "year" if basis == "Report year" else "recd_year"
    df = filtered(GIFTS, years, branches, year_col)
    return df, years, METRICS[metric_label]


DF, YEARS, METRIC = sidebar()
YEAR_LABEL = f"{YEARS[0]}–{YEARS[1]}" if YEARS[0] != YEARS[1] else str(YEARS[0])


def scale_toggle(key, default_log=None):
    default = METRIC == "value" if default_log is None else default_log
    return st.toggle("Log colour scale", value=default, key=key,
                     help="Gift values are very skewed; a log scale keeps mid-sized givers visible.")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_map():
    st.title("World map of foreign gifts")
    c1, c2 = st.columns([3, 1])
    mode = c1.radio("View", ["Single year", "Total over selected years", "Animate over selected years"],
                    horizontal=True)
    with c2:
        log = scale_toggle("map_log")
    label = "gifts" if METRIC == "n" else "gift value"

    if mode == "Single year":
        year = st.select_slider("Year", options=list(range(YEARS[0], YEARS[1] + 1)), value=YEARS[1])
        cy = country_year(DF)
        st.plotly_chart(charts.world_map(cy[cy.yr == year], METRIC, log, f"Foreign {label}, {year}"),
                        width="stretch")
    elif mode == "Total over selected years":
        st.plotly_chart(charts.world_map(country_totals(DF), METRIC, log, f"Foreign {label}, {YEAR_LABEL}"),
                        width="stretch")
    else:
        cy = country_year(DF)
        st.plotly_chart(charts.animated_map(cy, METRIC, log, YEARS, f"Foreign {label} by year, {YEAR_LABEL}"),
                        width="stretch")
        st.caption("The colour scale is fixed across years so frames are comparable.")

    st.subheader("Download as animated GIF")
    g1, g2 = st.columns([1, 3])
    speed = g1.slider("Seconds per year", 0.3, 3.0, 0.9, 0.1)
    cy = country_year(DF)
    params = (YEARS, METRIC, log, speed, len(DF), DF["value"].sum())
    if g1.button("Build GIF", type="primary"):
        with st.spinner("Rendering frames…"):
            st.session_state["gif"] = (params, build_gif(cy, YEARS, METRIC, log, speed))
    saved = st.session_state.get("gif")
    if saved and saved[0] == params:
        g2.image(saved[1], width="stretch")
        g1.download_button("Download GIF", saved[1],
                           file_name=f"gifts_map_{METRIC}_{YEARS[0]}_{YEARS[1]}.gif", mime="image/gif")
    elif saved:
        g2.info("Filters changed since the last GIF; build it again to match.")


@st.cache_data(show_spinner=False)
def build_gif(cy, years, metric, log, speed):
    frames = [(y, dict(zip(g.giver_iso3, g[metric]))) for y, g in
              ((y, cy[cy.yr == y]) for y in range(years[0], years[1] + 1))]
    vmax = float(cy[metric].max()) if len(cy) else 1.0
    fmt = fmt_money if metric == "value" else (lambda v: f"{v:,.0f}")
    title = "Gifts from foreign governments to U.S. officials" if metric == "n" else \
        "Value of gifts from foreign governments to U.S. officials"
    return gifmap.render_gif(frames, vmax, log, charts.METRIC_LABEL[metric], title, fmt,
                             ms_per_frame=int(speed * 1000))


def page_heatmap():
    st.title("Gifts per year by country")
    c = DF.dropna(subset=["giver_country"])
    totals = c.groupby("giver_country")[METRIC].sum().sort_values(ascending=False)
    c1, c2 = st.columns([3, 1])
    mode = c1.radio("Countries", ["Top 10 in selected years", "Choose up to 10"], horizontal=True)
    with c2:
        log = scale_toggle("heat_log")
    if mode == "Choose up to 10":
        chosen = st.multiselect("Countries", list(totals.index), default=list(totals.index[:5]),
                                max_selections=10)
    else:
        chosen = list(totals.index[:10])
    if not chosen:
        st.info("Pick at least one country.")
        return
    mat = (c[c.giver_country.isin(chosen)].groupby(["giver_country", "yr"])[METRIC].sum()
           .unstack(fill_value=0).reindex(index=chosen, columns=range(YEARS[0], YEARS[1] + 1), fill_value=0))
    what = "Gifts" if METRIC == "n" else "Gift value"
    st.plotly_chart(charts.heatmap(mat, METRIC, log, f"{what} per year, {YEAR_LABEL}"), width="stretch")
    with st.expander("Table"):
        st.dataframe(mat, width="stretch")


def giver_table(g, metric):
    cols = {"Giver": st.column_config.TextColumn("Giver", width="large"),
            "n": st.column_config.NumberColumn("Gifts", format="%d"),
            "value": st.column_config.NumberColumn("Value ($)", format="dollar"),
            "Wikidata": st.column_config.LinkColumn("Wikidata", display_text=r"wiki/(Q\d+)"),
            "recipients": st.column_config.NumberColumn("US recipients"),
            "years": st.column_config.NumberColumn("Active years"),
            "first": st.column_config.NumberColumn("First", format="%d"),
            "last": st.column_config.NumberColumn("Last", format="%d")}
    show = [c for c in ["Giver", "Country", "Role", "n", "value", "recipients", "years", "first", "last",
                        "Wikidata"] if c in g.columns]
    st.dataframe(g[show], column_config=cols, hide_index=True, width="stretch")


def page_givers():
    st.title("Top gift givers")
    c1, c2, c3 = st.columns([1, 1, 1])
    kind = c1.radio("Givers", ["Individuals", "Countries"], horizontal=True)
    period = c2.selectbox("Year", ["All selected years"] + list(range(YEARS[1], YEARS[0] - 1, -1)))
    n = c3.slider("How many", 5, 50, 20)
    d = DF if period == "All selected years" else DF[DF.yr == period]
    g = top_givers(d, METRIC, kind, n)
    when = YEAR_LABEL if period == "All selected years" else str(period)
    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(charts.hbar(g["Giver"], g[METRIC], METRIC, f"Top {len(g)} givers, {when}"),
                        width="stretch")
    with right:
        giver_table(g, METRIC)
        if kind == "Individuals":
            st.caption("Individuals are matched to Wikidata where possible. Joint gifts (e.g. a royal "
                       "couple) and unmatched names are listed under the name as published.")

    if kind == "Individuals":
        st.subheader("Top giver in each year")
        lead = leader_by_year(DF, METRIC)
        st.dataframe(lead[["Year", "Giver", "Country", "n", "value", "Wikidata"]], hide_index=True,
                     width="stretch",
                     column_config={"Year": st.column_config.NumberColumn(format="%d"),
                                    "n": st.column_config.NumberColumn("Gifts"),
                                    "value": st.column_config.NumberColumn("Value ($)", format="dollar"),
                                    "Wikidata": st.column_config.LinkColumn(display_text=r"wiki/(Q\d+)")})


@st.cache_data(show_spinner=False)
def build_cartogram(weights, scale):
    """weights: tuple of (iso3, raw total). Cached per filter setting."""
    iso = [i for i, _ in weights]
    w = cartogram.transform([v for _, v in weights], scale)
    shapes, _ = cartogram.build(dict(zip(iso, w)))
    return shapes


def page_network():
    st.title("Network of gifts")
    layout = st.radio("Layout", ["World cartogram", "Rings", "Force-directed"], horizontal=True,
                      help="World cartogram: each country's area is resized by its total gifts to U.S. "
                           "officials, with lines to the U.S. Rings: U.S. branches/agencies/people inside, "
                           "countries outside. Force-directed: strongly tied nodes pull together.")
    if layout == "World cartogram":
        page_cartogram()
        return
    st.caption("Giving countries (circles) linked to the U.S. side (diamonds). Node size is the "
               "country's or recipient's total; edge width is the gifts or value on that tie.")
    c1, c2, c3, c4 = st.columns(4)
    level = c1.selectbox("U.S. side", list(US_LEVELS), index=0)
    n_c = c2.slider("Countries (top by measure)", 5, 80, 30)
    default_us = {"Branch": 7, "Agency": 20, "Individual recipient": 40}[level]
    n_u = c3.slider("U.S. nodes (top by measure)", 3, 100, default_us)
    floor_max = 20 if METRIC == "n" else 100_000
    min_w = c4.slider("Hide ties below", 0, floor_max, 1 if METRIC == "n" else 0,
                      step=1 if METRIC == "n" else 1000)
    edges = network_edges(DF, METRIC, level, n_c, n_u, min_w)
    st.plotly_chart(charts.network(edges, METRIC, level, layout), width="stretch")
    with st.expander(f"Edge list ({len(edges):,} ties)"):
        st.dataframe(edges[["giver_country", "us_label", "n", "value"]]
                     .sort_values(METRIC, ascending=False),
                     hide_index=True, width="stretch",
                     column_config={"giver_country": "Country", "us_label": "U.S. node",
                                    "n": "Gifts", "value": st.column_config.NumberColumn("Value ($)", format="dollar")})


def page_cartogram():
    st.caption("Each country's area is proportional to its total gifts to U.S. officials in the "
               "selection (after the chosen scaling). Borders stay connected, so big givers swell and "
               "non-givers shrink to slivers. The United States, the recipient, keeps its true size. "
               "Line width is the country's total.")
    c1, c2 = st.columns([2, 1])
    scale = c1.radio("Size scaling", ["Log", "Square root", "Raw"], horizontal=True,
                     help="Raw: area exactly proportional to the total, very lopsided. Square root: same "
                          "order, mid-sized givers stay visible. Log: strongest compression; differences "
                          "between big givers flatten.")
    n_flows = c2.slider("Flow lines (top countries)", 0, 60, 25)
    tot = country_totals(DF)
    tot = tot[tot[METRIC] > 0]
    if tot.empty:
        st.info("No country-attributed gifts in the selected filters.")
        return
    weights = tuple(sorted(zip(tot.giver_iso3, tot[METRIC].astype(float))))
    with st.spinner("Reshaping the world map (about 10 seconds the first time for each setting)…"):
        shapes = build_cartogram(weights, scale)
    totals = {r.giver_iso3: {"name": r.giver_country, "n": int(r.n), "value": float(r.value)}
              for r in tot.itertuples(index=False)}
    what = "gifts" if METRIC == "n" else "gift value"
    st.plotly_chart(charts.cartogram_map(shapes, totals, METRIC, n_flows, cartogram.HUB,
                                         cartogram.anchor, f"Countries sized by {what} ({scale.lower()}), {YEAR_LABEL}"),
                    width="stretch")


def page_roles():
    st.title("Who gives to whom")
    st.caption("Type of foreign giver (from honorifics and titles) against the branch of the U.S. "
               "agency that reported the gift.")
    normalize = st.radio("Show", ["Share of each branch's gifts", "Counts"], horizontal=True) != "Counts"
    shown = [b for b in BRANCH_ORDER if b in set(DF.branch)]
    t = pd.crosstab(DF.branch, DF.giver_role, values=DF[METRIC], aggfunc="sum").fillna(0)
    t = t.reindex(index=shown, columns=[r for r in ROLE_ORDER if r in t.columns]).fillna(0)
    if normalize:
        t = t.div(t.sum(axis=1).replace(0, 1), axis=0) * 100
    what = "gifts" if METRIC == "n" else "gift value"
    st.plotly_chart(charts.role_branch(t, normalize, f"Foreign {what} by giver type and recipient branch, {YEAR_LABEL}"),
                    width="stretch")


def page_country():
    st.title("Country profile")
    totals = DF.dropna(subset=["giver_country"]).groupby("giver_country")["n"].sum().sort_values(ascending=False)
    if totals.empty:
        st.info("No country-attributed gifts in the selected filters.")
        return
    country = st.selectbox("Country", list(totals.index))
    d = DF[DF.giver_country == country]
    k = st.columns(4)
    k[0].metric("Gifts", f"{len(d):,}")
    k[1].metric("Total value", fmt_money(d.value.sum()))
    k[2].metric("Years with gifts", f"{d.yr.nunique()} of {YEARS[1] - YEARS[0] + 1}")
    k[3].metric("U.S. recipients", f"{d.recip_key.nunique():,}")

    left, right = st.columns(2)
    by_year = d.groupby("yr")[METRIC].sum().reindex(range(YEARS[0], YEARS[1] + 1), fill_value=0)
    left.plotly_chart(charts.columns_by_year(by_year, METRIC, f"{country}: by year"), width="stretch")
    br = d.groupby("branch")[METRIC].sum().reindex([b for b in BRANCH_ORDER if b in set(d.branch)])
    right.plotly_chart(charts.hbar(br.index, br.values, METRIC, "By recipient branch", height=320),
                       width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("Top givers")
        giver_table(top_givers(d, METRIC, "Individuals", 15), METRIC)
    with right:
        st.subheader("Top U.S. recipients")
        r = (d.dropna(subset=["recip_key"]).groupby("recip_key")
             .agg(Recipient=("recip_label", "first"), Branch=("branch", lambda s: ", ".join(sorted(set(s)))),
                  n=("n", "sum"), value=("value", "sum")).reset_index()
             .sort_values(METRIC, ascending=False).head(15))
        r["Wikidata"] = r.recip_key.map(wikidata_url)
        st.dataframe(r.drop(columns="recip_key"), hide_index=True, width="stretch",
                     column_config={"n": "Gifts", "value": st.column_config.NumberColumn("Value ($)", format="dollar"),
                                    "Wikidata": st.column_config.LinkColumn(display_text=r"wiki/(Q\d+)")})

    st.subheader("Most valuable gifts")
    top = d.sort_values("value", ascending=False).head(10)
    st.dataframe(top[["yr", "recip_label", "giver_label", "item", "estval", "disposition"]],
                 hide_index=True, width="stretch",
                 column_config={"yr": st.column_config.NumberColumn("Year", format="%d"),
                                "recip_label": "Recipient", "giver_label": "Giver",
                                "item": st.column_config.TextColumn("Item", width="large"),
                                "estval": "Value"})


def page_explorer():
    st.title("Gift explorer")
    c1, c2, c3 = st.columns([2, 2, 1])
    text = c1.text_input("Search item, giver, or recipient", placeholder="e.g. jewelry, Karzai, Senator")
    countries = c2.multiselect("Giving country", sorted(DF.giver_country.dropna().unique()))
    travel = c3.selectbox("Gift type", ["All", "Tangible only", "Travel only"])
    vmax = float(DF.value.max()) if DF.value.notna().any() else 0.0
    lo, hi = st.slider("Estimated value ($)", 0.0, vmax, (0.0, vmax), step=50.0)

    d = DF
    if text:
        pat = text.strip()
        mask = (d.item.str.contains(pat, case=False, regex=False) |
                d.giver.str.contains(pat, case=False, regex=False) |
                d.recip.str.contains(pat, case=False, regex=False))
        d = d[mask]
    if countries:
        d = d[d.giver_country.isin(countries)]
    if travel != "All":
        d = d[d.travel == (1 if travel == "Travel only" else 0)]
    if (lo, hi) != (0.0, vmax):
        d = d[d.value.between(lo, hi)]

    st.caption(f"{len(d):,} gifts · total value {fmt_money(d.value.sum())}")
    cols = ["yr", "recip", "agency_std", "giver", "giver_country", "item", "estval", "value",
            "recd", "disposition", "reason", "recip_wiki", "giver_wiki", "gift_id"]
    st.dataframe(d[cols].sort_values(["yr", "gift_id"]), hide_index=True, width="stretch", height=560,
                 column_config={"yr": st.column_config.NumberColumn("Year", format="%d"),
                                "recip": "Recipient", "agency_std": "Agency", "giver": "Giver",
                                "giver_country": "Country",
                                "item": st.column_config.TextColumn("Item", width="large"),
                                "estval": "Value (as reported)",
                                "value": st.column_config.NumberColumn("Value ($)", format="dollar"),
                                "recd": "Received", "disposition": "Disposition",
                                "reason": "Circumstances"})
    st.download_button("Download these gifts (CSV)", d[cols].to_csv(index=False).encode("utf-8"),
                       file_name="gifts_filtered.csv", mime="text/csv")


def page_about():
    st.title("About the data")
    st.markdown(f"""
Every year the U.S. Department of State publishes in the *Federal Register* the gifts that
federal employees reported receiving from foreign governments (5 U.S.C. § 7342). This dashboard
reads the output of the gifts pipeline (`analysis/output/gifts_analysis.csv`), which downloads
each report, parses the free-text fields, and links givers and recipients to Wikidata.

* **{len(GIFTS):,} gifts**, report years {YEAR_MIN}–{YEAR_MAX}, from
  **{GIFTS.giver_country.nunique()} countries**.
* **Branch** is the branch of the agency that filed the report.
* **Country** comes from the giver's description, falling back on Wikidata citizenship.
  International organizations, and givers withheld under § 7342(f)(4) (most intelligence-community
  gifts), have no country.
* **Values** are the agencies' estimates, in nominal dollars. Only gifts above the "minimal value"
  threshold must be reported, and that threshold rises every three years.
* **Year basis.** *Report year* is the report the gift appeared in. *Year received* comes from the
  gift's date where it can be parsed.

To refresh: re-run the pipeline (`parseandclean_new.py`, then
`analysis/build_analysis_data.py`) and reload this page.
""")


pages = [
    st.Page(page_map, title="World map", icon="🗺️", url_path="map", default=True),
    st.Page(page_heatmap, title="Country heatmap", icon="🟦", url_path="heatmap"),
    st.Page(page_givers, title="Top givers", icon="🏅", url_path="givers"),
    st.Page(page_network, title="Network", icon="🕸️", url_path="network"),
    st.Page(page_roles, title="Who gives to whom", icon="🔀", url_path="roles"),
    st.Page(page_country, title="Country profile", icon="📍", url_path="country"),
    st.Page(page_explorer, title="Gift explorer", icon="🔎", url_path="explorer"),
    st.Page(page_about, title="About the data", icon="ℹ️", url_path="about"),
]
st.navigation(pages).run()
