"""Descriptive statistics for the foreign gifts paper.

Reads ``analysis/output/gifts_analysis.csv`` (built by build_analysis_data.py)
and the Wikidata claims, and writes

* LaTeX tables to ``paper/tables/``
* PDF figures to ``paper/figures/``
* an interactive country-year map to ``analysis/output/map_gifts_by_country.html``
* the numbers quoted in the text to ``analysis/output/paper_numbers.json``

Run from the repo root: ``python analysis/descriptives.py``
"""

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATA = BASE_DIR / "analysis" / "output" / "gifts_analysis.csv"
CLAIMS = BASE_DIR / "files" / "wikidata_claims.csv"
OUT_DIR = BASE_DIR / "analysis" / "output"
TAB_DIR = BASE_DIR / "paper" / "tables"
FIG_DIR = BASE_DIR / "paper" / "figures"


# ---------------------------------------------------------------------------
# Style: one palette, fixed entity -> colour assignment
# ---------------------------------------------------------------------------
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE = "#2a78d6"
SEQ_BLUES = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

BRANCH_ORDER = ["White House", "Diplomatic", "Defense", "Legislative",
                "Intelligence", "Other executive", "Judicial"]
BRANCH_COLOR = dict(zip(BRANCH_ORDER, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                                       "#e87ba4", "#008300", "#4a3aa7"]))
BRANCH_MARKER = dict(zip(BRANCH_ORDER, ["o", "s", "^", "D", "v", "P", "X"]))
ROLE_ORDER = ["Head of state/govt", "Royalty", "Minister", "Military", "Diplomat",
              "Legislator", "Intelligence/security", "International org.", "Other/unknown"]

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 9, "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlecolor": INK, "axes.titlesize": 9.5, "axes.titleweight": "semibold",
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.bbox": "tight",
})


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{name}.pdf")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# LaTeX tables (booktabs, no jinja dependency)
# ---------------------------------------------------------------------------
class Raw(str):
    """A cell that is already LaTeX and must not be escaped."""


def tex_escape(x):
    if isinstance(x, Raw):
        return x
    if isinstance(x, float):
        return "" if np.isnan(x) else f"{x:,.0f}"
    if isinstance(x, (int, np.integer)):
        return f"{x:,}"
    s = str(x)
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}")]:
        s = s.replace(a, b)
    return s


def write_table(df, name, align=None):
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    align = align or "l" + "r" * (df.shape[1] - 1)
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule",
             " & ".join(df.columns) + r" \\", r"\midrule"]  # headers are written as LaTeX
    lines += [" & ".join(tex_escape(v) for v in row) + r" \\" for row in df.itertuples(index=False)]
    lines += [r"\bottomrule", r"\end{tabular}"]
    (TAB_DIR / f"{name}.tex").write_text("\n".join(lines) + "\n")


def pct(x):
    return Raw(f"{100 * x:.0f}\\%")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def table_overview(df):
    """Gifts, unique parties, linkage and value, by five-year period."""
    df = df.assign(period=pd.cut(df["year"], [1998, 2003, 2008, 2013, 2018, 2023],
                                 labels=["1999--2003", "2004--2008", "2009--2013",
                                         "2014--2018", "2019--2023"]))
    rows = []
    for period, g in list(df.groupby("period", observed=True)) + [("All years", df)]:
        rows.append({
            "Period": period, "Gifts": len(g),
            "Recipients (QID)": g.loc[g.recip_has_qid == 1, "recip_wiki"].nunique(),
            "Givers (QID)": g.loc[g.giver_has_qid == 1, "giver_wiki"].nunique(),
            "Countries": g["giver_country"].nunique(),
            "Recip.\\ linked": pct(g.recip_has_qid.mean()),
            "Giver linked": pct(g.giver_has_qid.mean()),
            "Median value (\\$)": g.loc[g.travel == 0, "estval_num"].median(),
        })
    out = pd.DataFrame(rows)
    write_table(out, "tab_overview")
    return out


def table_top(df, side, n=15):
    q = df[df[f"{side}_has_qid"] == 1]
    g = (q.groupby(f"{side}_wiki")
         .agg(Name=(f"{side}_wikiname", "first"), Gifts=("gift_id", "size"),
              Years=("year", lambda s: f"{s.min()}--{s.max()}" if s.min() != s.max() else str(s.min())),
              Value=("estval_num", "sum"))
         .sort_values("Gifts", ascending=False).head(n).reset_index())
    if side == "giver":
        g["Country"] = g[f"{side}_wiki"].map(q.groupby("giver_wiki")["giver_country"].first()).fillna("(intl. org.)")
        cols = ["Name", "Country", f"{side}_wiki", "Gifts", "Years", "Value"]
    else:
        g["Branch"] = g[f"{side}_wiki"].map(q.groupby("recip_wiki")["branch"].agg(
            lambda s: ", ".join(b for b in BRANCH_ORDER if b in set(s))))
        cols = ["Name", "Branch", f"{side}_wiki", "Gifts", "Years", "Value"]
    g = g[cols].rename(columns={f"{side}_wiki": "Wikidata", "Value": "Value (\\$)"})
    write_table(g, f"tab_top_{side}s", align="lllrrr")
    return g


def table_countries(df, n=20):
    c = df.dropna(subset=["giver_country"])
    g = (c.groupby(["giver_country", "giver_iso3"])
         .agg(Gifts=("gift_id", "size"), Years=("year", "nunique"),
              Recipients=("recip_wiki", "nunique"), Value=("estval_num", "sum"))
         .sort_values("Gifts", ascending=False).head(n).reset_index())
    top_branch = c.groupby("giver_country")["branch"].agg(lambda s: s.value_counts().index[0])
    g["Main recipient branch"] = g["giver_country"].map(top_branch)
    g = g.rename(columns={"giver_country": "Country", "giver_iso3": "ISO3",
                          "Years": "Active years", "Value": "Value (\\$)"})
    write_table(g, "tab_top_countries", align="llrrrrl")
    return g


def table_branch(df):
    rows = []
    for b in BRANCH_ORDER:
        g = df[df.branch == b]
        rows.append({"Branch": b, "Gifts": len(g), "Share": pct(len(g) / len(df)),
                     "Agencies": g["agency"].nunique(),
                     "Recip.\\ linked": pct(g.recip_has_qid.mean()),
                     "Giver linked": pct(g.giver_has_qid.mean()),
                     "Confidential giver": pct(g.giver.fillna("").str.contains(r"7342|403-", regex=True).mean()),
                     "Travel": pct(g.travel.mean())})
    out = pd.DataFrame(rows)
    write_table(out, "tab_branch")
    return out


def careers(df):
    """Recipients seen under more than one branch: office vs officeholder."""
    q = df[df.recip_has_qid == 1]
    by = q.groupby("recip_wiki")
    g = by.agg(Name=("recip_wikiname", "first"), Gifts=("gift_id", "size"),
               n_branch=("branch", "nunique"), n_agency=("agency", "nunique"))
    multi = g[g.n_branch > 1].sort_values("Gifts", ascending=False)
    spells = (q[q.recip_wiki.isin(multi.index)]
              .groupby(["recip_wiki", "branch"])["recd_year"].agg(["min", "max", "size"]).reset_index())

    def path(qid):
        s = spells[spells.recip_wiki == qid].sort_values("min")
        return Raw(" $\\rightarrow$ ".join(
            f"{r.branch} ({r['min']}" + (f"--{r['max']})" if r["max"] != r["min"] else ")")
            for _, r in s.iterrows()))
    tab = multi.head(15).reset_index()
    tab["Sequence of reporting branches (years received)"] = tab["recip_wiki"].map(path)
    tab = tab[["Name", "recip_wiki", "Gifts", "Sequence of reporting branches (years received)"]]
    tab = tab.rename(columns={"recip_wiki": "Wikidata"})
    write_table(tab, "tab_careers", align="llrp{0.55\\linewidth}")
    return multi, spells


def wikidata_coverage(df, claims):
    """Share of linked people for whom Wikidata supplies each attribute."""
    props = [("P21", "Gender"), ("P569", "Date of birth"), ("P27", "Citizenship"),
             ("P106", "Occupation"), ("P39", "Position held"), ("P69", "Educated at"),
             ("P102", "Party membership"), ("P108", "Employer"), ("P410", "Military rank"),
             ("P26", "Spouse"), ("P40", "Child"), ("P22", "Father")]
    have = claims.groupby("property")["item"].apply(set)
    rows = []
    for side, label in [("recip", "Recipients"), ("giver", "Givers")]:
        ids = set(df.loc[df[f"{side}_has_qid"] == 1, f"{side}_wiki"])
        ids_c = ids & set(claims["item"])
        rows.append((label, len(ids), {p: len(ids_c & have.get(p, set())) / len(ids) for p, _ in props}))
    out = pd.DataFrame({"Attribute (property)": [f"{n} ({p})" for p, n in props]})
    for label, n, shares in rows:
        out[f"{label} (N={n:,})"] = [pct(shares[p]) for p, _ in props]
    write_table(out, "tab_wikidata_coverage", align="lrr")
    return out


# Position-held labels for chambers covered by the Comparative Legislators Database.
CLD_CHAMBERS = {
    "United States": r"^United States (?:senator|representative)$|^non-voting member of the U\.S\. House",
    "United Kingdom": r"member of the \d+\w\w Parliament of the United Kingdom",
    "Germany": r"member of the German Bundestag",
    "France": r"member of the French National Assembly",
    "Italy": r"member of the Chamber of Deputies of the Italian Republic",
    "Japan": r"member of the House of Representatives of Japan",
    "Israel": r"Knesset member",
    "Ireland": r"Teachta Dála",
    "Canada": r"member of the House of Commons of Canada",
    "Turkey": r"member of the Grand National Assembly of Turkey",
    "Spain": r"Member of the Congress of Deputies",
    "Austria": r"member of the National Council of Austria",
    "Czech Republic": r"member of the chamber of deputies of the parliament of the Czech Republic",
    "Netherlands": r"member of the House of Representatives of the Netherlands",
    "Brazil": r"member of the Chamber of Deputies of Brazil",
    "Scotland": r"Member of the \d+\w\w Scottish Parliament|member of the Scottish Parliament",
}


def cld_linkable(df, claims):
    """People who ever sat in a CLD chamber, so join to it on wikidataid."""
    p39 = claims[claims["property"] == "P39"]
    hits = []
    for chamber, pattern in CLD_CHAMBERS.items():
        ids = set(p39.loc[p39["valueLabel"].str.contains(pattern, case=False, regex=True, na=False), "item"])
        for side in ("recip", "giver"):
            people = set(df.loc[df[f"{side}_has_qid"] == 1, f"{side}_wiki"]) & ids
            gifts = df[f"{side}_wiki"].isin(people).sum()
            hits.append({"Legislature": chamber, "side": side, "people": len(people), "gifts": gifts})
    h = pd.DataFrame(hits)
    wide = h.pivot(index="Legislature", columns="side", values=["people", "gifts"]).fillna(0).astype(int)
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide[(wide.sum(axis=1) > 0)].sort_values("gifts_giver", ascending=False).reset_index()
    out = wide.rename(columns={"people_recip": "Recipients", "gifts_recip": "Gifts received",
                               "people_giver": "Givers", "gifts_giver": "Gifts given"})
    out = out[["Legislature", "Recipients", "Gifts received", "Givers", "Gifts given"]]
    write_table(out, "tab_cld_link")
    return out


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_by_year(df):
    counts = df.groupby("year").size()
    fig, ax = plt.subplots(figsize=(6.5, 2.6))
    ax.bar(counts.index, counts.values, width=0.6, color=BLUE, edgecolor="white", linewidth=0.8)
    for yr, label in [(2001, "Bush"), (2009, "Obama"), (2017, "Trump"), (2021, "Biden")]:
        ax.axvline(yr - 0.5, color=AXIS, linewidth=0.8)
        ax.text(yr - 0.35, counts.max() * 1.02, label, color=INK2, fontsize=8, va="bottom")
    ax.set_ylim(0, counts.max() * 1.12)
    ax.set_xlim(1998.3, counts.index.max() + 0.7)
    ax.set_ylabel("Gifts reported")
    ax.grid(axis="x", visible=False)
    ax.set_xticks(range(1999, counts.index.max() + 1, 2))
    save(fig, "fig_gifts_by_year")


def fig_branch_multiples(df):
    counts = df.groupby(["branch", "year"]).size().unstack(0).reindex(columns=BRANCH_ORDER).fillna(0)
    shown = [b for b in BRANCH_ORDER if b != "Judicial"]
    fig, axes = plt.subplots(2, 3, figsize=(6.5, 3.6), sharex=True, sharey=True)
    for ax, b in zip(axes.flat, shown):
        ax.fill_between(counts.index, counts[b], color=BLUE, alpha=0.10, linewidth=0)
        ax.plot(counts.index, counts[b], color=BLUE, linewidth=1.6, solid_capstyle="round")
        ax.set_title(f"{b}  (n={int(counts[b].sum()):,})", loc="left")
        ax.grid(axis="x", visible=False)
        ax.set_xticks([2000, 2010, 2020])
    for ax in axes[:, 0]:
        ax.set_ylabel("Gifts")
    fig.tight_layout()
    save(fig, "fig_branch_multiples")


def heatmap(ax, mat, fmt, vmax=None):
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("blues", SEQ_BLUES)
    vmax = vmax or np.nanmax(mat.values)
    im = ax.imshow(mat.values, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    ax.set_xticks(range(mat.shape[1]))
    ax.set_yticks(range(mat.shape[0]))
    ax.set_yticklabels(mat.index, color=INK2)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    if fmt:
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat.values[i, j]
                ax.text(j, i, fmt(v), ha="center", va="center", fontsize=7,
                        color="white" if v > 0.55 * vmax else INK)
    return im


def fig_country_heatmap(df, n=20):
    c = df.dropna(subset=["giver_country"])
    top = c["giver_country"].value_counts().head(n).index
    mat = (c[c.giver_country.isin(top)].groupby(["giver_country", "year"]).size()
           .unstack(fill_value=0).reindex(top))
    mat = mat.reindex(columns=range(df.year.min(), df.year.max() + 1), fill_value=0)
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    im = heatmap(ax, mat, fmt=None, vmax=np.percentile(mat.values, 98))
    ax.set_xticklabels([str(y) if y % 2 == 1 else "" for y in mat.columns], color=MUTED, rotation=0)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=MUTED, length=0)
    cb.set_label("Gifts (capped at 98th pct.)", color=INK2)
    save(fig, "fig_country_heatmap")


def fig_role_branch(df):
    shown = [b for b in BRANCH_ORDER if b != "Judicial"]
    t = pd.crosstab(df.branch, df.giver_role, normalize="index").reindex(index=shown, columns=ROLE_ORDER).fillna(0) * 100
    fig, ax = plt.subplots(figsize=(6.5, 2.9))
    heatmap(ax, t, fmt=lambda v: f"{v:.0f}", vmax=60)
    ax.set_xticklabels([r.replace("/", "/\n").replace(" of ", "\nof ").replace("International ", "Intl.\n") for r in ROLE_ORDER],
                       color=INK2, fontsize=7.5)
    ax.xaxis.tick_top()
    save(fig, "fig_role_branch")
    return t


def runs(years, max_gap=2):
    """Split sorted years into runs, breaking where no gift is seen for > max_gap years."""
    out = [[years[0]]]
    for y in years[1:]:
        if y - out[-1][-1] > max_gap:
            out.append([])
        out[-1].append(y)
    return out


def fig_careers(df, multi, names):
    """Timeline of selected individuals across reporting branches."""
    keep = [q for q in names if q in multi.index]
    sub = df[df.recip_wiki.isin(keep)]
    years_by_branch = {q: {b: sorted(g.recd_year.unique()) for b, g in sub[sub.recip_wiki == q].groupby("branch")}
                       for q in keep}
    fig, ax = plt.subplots(figsize=(6.5, 0.32 * len(keep) + 0.9))
    used = []
    for i, qid in enumerate(keep):
        ax.axhline(i, color=GRID, linewidth=0.6, zorder=0)
        for branch, years in years_by_branch[qid].items():
            col = BRANCH_COLOR[branch]
            for run in runs(years):
                ax.plot([run[0], run[-1]], [i, i], color=col, linewidth=2.2, solid_capstyle="round", zorder=2)
                ax.scatter([run[0], run[-1]], [i, i], s=34, color=col, marker=BRANCH_MARKER[branch],
                           edgecolor="white", linewidth=1.2, zorder=3)
            used.append(branch)
    ax.set_yticks(range(len(keep)))
    ax.set_yticklabels([multi.loc[q, "Name"] for q in keep], color=INK2)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    handles = [plt.Line2D([], [], color=BRANCH_COLOR[b], marker=BRANCH_MARKER[b], linewidth=2.2,
                          markeredgecolor="white", label=b) for b in BRANCH_ORDER if b in used]
    ax.legend(handles=handles, ncol=len(handles), loc="lower center", bbox_to_anchor=(0.45, 1.0),
              frameon=False, fontsize=7.5, handlelength=1.6, columnspacing=1.0, labelcolor=INK2)
    ax.set_xlabel("Year gift received")
    save(fig, "fig_careers")


def map_html(df):
    """Interactive country-year map (prototype for the Streamlit view)."""
    import plotly.express as px
    panel = pd.read_csv(OUT_DIR / "country_year_panel.csv")
    fig = px.choropleth(panel, locations="giver_iso3", color="n_gifts", hover_name="giver_country",
                        hover_data={"giver_iso3": False, "n_gifts": True, "n_recipients": True},
                        animation_frame="year", color_continuous_scale=SEQ_BLUES,
                        range_color=(0, panel["n_gifts"].quantile(0.99)),
                        labels={"n_gifts": "Gifts", "n_recipients": "US recipients"},
                        title="Foreign gifts to US federal officials, by giving country")
    fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth")
    fig.write_html(OUT_DIR / "map_gifts_by_country.html", include_plotlyjs="cdn")


# ---------------------------------------------------------------------------
def main():
    df = pd.read_csv(DATA, low_memory=False)
    claims = pd.read_csv(CLAIMS, low_memory=False)
    numbers = json.loads((OUT_DIR / "summary.json").read_text())

    table_overview(df)
    table_top(df, "recip")
    table_top(df, "giver")
    table_countries(df)
    table_branch(df)
    multi, spells = careers(df)
    wikidata_coverage(df, claims)
    cld = cld_linkable(df, claims)

    fig_by_year(df)
    fig_branch_multiples(df)
    fig_country_heatmap(df)
    role_branch = fig_role_branch(df)
    fig_careers(df, multi, ["Q6294", "Q76", "Q6279", "Q22316", "Q7821917", "Q473239",
                                "Q28591", "Q244631", "Q381670", "Q1276563", "Q984191", "Q33190271"])
    map_html(df)

    panel = pd.read_csv(OUT_DIR / "country_year_panel.csv")
    numbers.update({
        "multi_branch_recipients": int(len(multi)),
        "gifts_per_year_max": [int(df.groupby("year").size().idxmax()), int(df.groupby("year").size().max())],
        "gifts_per_year_min": [int(df.groupby("year").size().idxmin()), int(df.groupby("year").size().min())],
        "gifts_2009_2016": int(df[df.year.between(2009, 2016)].shape[0]),
        "gifts_2017_2023": int(df[df.year.between(2017, 2023)].shape[0]),
        "panel_rows": int(len(panel)), "panel_countries": int(panel.giver_country.nunique()),
        "panel_share_any_gift": float(panel.any_gift.mean()),
        "confidential_giver_share": float(df.giver.fillna("").str.contains(r"7342|403-").mean()),
        "cld_recip_people": int(cld["Recipients"].sum()), "cld_giver_people": int(cld["Givers"].sum()),
        "value_total": float(df.estval_num.sum()), "value_median": float(df.estval_num.median()),
        "role_branch_head_state_whitehouse": float(role_branch.loc["White House", "Head of state/govt"]),
        "role_branch_military_defense": float(role_branch.loc["Defense", "Military"]),
        "role_branch_other_intel": float(role_branch.loc["Intelligence", "Other/unknown"]),
    })
    (OUT_DIR / "paper_numbers.json").write_text(json.dumps(numbers, indent=2))
    print(json.dumps(numbers, indent=2))


if __name__ == "__main__":
    main()
