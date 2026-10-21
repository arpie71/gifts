"""Data loading and aggregation for the gifts dashboard.

Everything here reads the pipeline output ``analysis/output/gifts_analysis.csv``,
so the dashboard updates whenever the pipeline is re-run.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_CSV = BASE_DIR / "analysis" / "output" / "gifts_analysis.csv"

BRANCH_ORDER = ["White House", "Diplomatic", "Defense", "Legislative",
                "Intelligence", "Other executive", "Judicial"]
ROLE_ORDER = ["Head of state/govt", "Royalty", "Minister", "Military", "Diplomat",
              "Legislator", "Intelligence/security", "International org.", "Other/unknown"]

METRICS = {"Number of gifts": "n", "Total value ($)": "value"}

# Recipient/giver codes that are not people; these never become individual nodes.
NON_PERSON = {"NIL", "FAMILY", "GROUP", "UNCLEAR", "Unclear", "unclear"}

COLUMNS = [
    "gift_id", "year", "recd_year", "recd", "agency", "agency_std", "branch",
    "recip", "recip_name", "recip_wiki", "recip_wikiname",
    "giver", "giver_name", "giver_wiki", "giver_wikiname", "giver_role",
    "giver_country", "giver_iso3", "item", "estval", "estval_num",
    "disposition", "reason", "travel",
]


@st.cache_data(show_spinner=False)
def load_gifts(mtime=None):
    """All gifts, with display keys for givers and recipients.

    `mtime` is only there to bust the cache when the CSV is rebuilt.
    """
    df = pd.read_csv(DATA_CSV, usecols=COLUMNS, low_memory=False)
    df["value"] = df["estval_num"]
    df["n"] = 1

    is_q = df["giver_wiki"].fillna("").str.match(r"^Q\d+$")
    named = ~df["giver_wiki"].isin(NON_PERSON - {"FAMILY", "GROUP"}) & df["giver"].notna()
    # People resolve to their QID; joint gifts from royal couples and delegations
    # keep their own (unlinked) name so they still show up among top givers.
    df["giver_key"] = np.where(is_q, df["giver_wiki"], np.where(named, "txt:" + df["giver"].fillna(""), None))
    df["giver_label"] = np.where(is_q, df["giver_wikiname"],
                                 df["giver_name"].fillna(df["giver"]).str.slice(0, 80))

    r_q = df["recip_wiki"].fillna("").str.match(r"^Q\d+$")
    df["recip_key"] = np.where(r_q, df["recip_wiki"], None)
    df["recip_label"] = np.where(r_q, df["recip_wikiname"], df["recip"])
    for col in ["item", "giver", "recip", "disposition", "reason"]:
        df[col] = df[col].fillna("").str.split().str.join(" ")
    return df


def data_mtime():
    return DATA_CSV.stat().st_mtime


def filtered(df, years, branches, year_col):
    out = df[df[year_col].between(*years)]
    if branches:
        out = out[out["branch"].isin(branches)]
    return out.assign(yr=out[year_col])


def wikidata_url(qid):
    return f"https://www.wikidata.org/wiki/{qid}" if isinstance(qid, str) and qid.startswith("Q") else None


def fmt_money(x):
    if pd.isna(x):
        return "—"
    for div, suf in [(1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if abs(x) >= div:
            return f"${x / div:,.1f}{suf}"
    return f"${x:,.0f}"


def fmt_metric(x, metric):
    return fmt_money(x) if metric == "value" else f"{int(x):,}"


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------
def country_year(df):
    """Country x year totals (countries with at least one gift in df)."""
    c = df.dropna(subset=["giver_iso3"])
    return (c.groupby(["giver_iso3", "giver_country", "yr"])
            .agg(n=("n", "sum"), value=("value", "sum"), recipients=("recip_key", "nunique"))
            .reset_index())


def country_totals(df):
    c = df.dropna(subset=["giver_iso3"])
    return (c.groupby(["giver_iso3", "giver_country"])
            .agg(n=("n", "sum"), value=("value", "sum"), recipients=("recip_key", "nunique"),
                 years=("yr", "nunique"))
            .reset_index())


def top_givers(df, metric, kind="Individuals", n=20):
    if kind == "Countries":
        g = country_totals(df).rename(columns={"giver_country": "Giver"})
        g["Country"] = g["Giver"]
        g["Wikidata"] = None
    else:
        d = df.dropna(subset=["giver_key"])
        g = (d.groupby("giver_key")
             .agg(Giver=("giver_label", "first"), Country=("giver_country", "first"),
                  Role=("giver_role", lambda s: s.mode().iat[0] if len(s) else ""),
                  n=("n", "sum"), value=("value", "sum"),
                  first=("yr", "min"), last=("yr", "max"), recipients=("recip_key", "nunique"))
             .reset_index())
        g["Wikidata"] = g["giver_key"].map(wikidata_url)
    return g.sort_values([metric, "n"], ascending=False).head(n).reset_index(drop=True)


def leader_by_year(df, metric):
    """The single top individual giver in each year."""
    d = df.dropna(subset=["giver_key"])
    g = (d.groupby(["yr", "giver_key"])
         .agg(Giver=("giver_label", "first"), Country=("giver_country", "first"),
              n=("n", "sum"), value=("value", "sum"))
         .reset_index())
    g = g.sort_values(["yr", metric, "n"], ascending=[True, False, False]).groupby("yr").head(1)
    g["Wikidata"] = g["giver_key"].map(wikidata_url)
    return g.drop(columns="giver_key").rename(columns={"yr": "Year"})


US_LEVELS = {"Branch": "branch", "Agency": "agency_std", "Individual recipient": "recip_key"}


def network_edges(df, metric, us_level, n_countries, n_us, min_weight):
    """Country -> US node edges, keeping the top countries and top US nodes."""
    col = US_LEVELS[us_level]
    d = df.dropna(subset=["giver_country", col])
    if us_level == "Individual recipient":
        labels = d.groupby("recip_key")["recip_label"].first()
    else:
        labels = None
    top_c = d.groupby("giver_country")[metric].sum().nlargest(n_countries).index
    d = d[d["giver_country"].isin(top_c)]
    top_u = d.groupby(col)[metric].sum().nlargest(n_us).index
    d = d[d[col].isin(top_u)]
    e = (d.groupby(["giver_country", col]).agg(n=("n", "sum"), value=("value", "sum"))
         .reset_index().rename(columns={col: "us"}))
    e = e[e[metric] >= min_weight]
    e["us_label"] = e["us"].map(labels) if labels is not None else e["us"]
    return e
