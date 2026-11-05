"""Figures for the revised analysis (PDF + PNG in analysis_revised/output/figures/).

Each figure has a CSV twin with the plotted values (table view).

Run from the repo root, after 03_models.py:
  /home/arpie/envs/revised/bin/python analysis_revised/04_figures.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, FIG, SEED, EVENTS, PERIODS

# Same visual system as analysis/descriptives.py (validated categorical palette).
INK, INK2, MUTED, AXIS, GRID = "#0b0b0b", "#52514e", "#8a8984", "#c9c8c2", "#e6e5e0"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#a3a29c"
SEQ = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
BRANCH_ORDER = ["White House", "Diplomatic", "Defense", "Legislative", "Intelligence", "Other executive", "Judicial"]
BRANCH_COLOR = dict(zip(BRANCH_ORDER, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]))
SECTOR_SLOTS = ["National executive", "Legislature", "Diplomatic", "Military", "Subnational",
                "Academic/research", "Private", "Intl organization"]
SECTOR_COLOR = dict(zip(SECTOR_SLOTS, CAT))   # Judiciary, Party, Ceremonial -> "Other"
plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 8.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlecolor": INK, "axes.titlesize": 9, "axes.titleweight": "semibold",
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.bbox": "tight",
    "pdf.fonttype": 42, "svg.hashsalt": "gifts", "path.simplify": True})


def save(fig, name, table=None):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(FIG / f"{name}.png", dpi=200)
    plt.close(fig)
    if table is not None:
        table.to_csv(FIG / f"{name}.csv", index=False)


def events(ax, y=None, label=True):
    for yr, lab in EVENTS.items():
        ax.axvline(yr, color=AXIS, lw=0.8, ls=(0, (2, 2)), zorder=0)
        if label:
            ax.text(yr + 0.15, ax.get_ylim()[1] if y is None else y, lab, rotation=90, va="top", ha="left",
                    fontsize=6.5, color=MUTED)


def sector_color(s):
    return SECTOR_COLOR.get(s, OTHER)


# ---------------------------------------------------------------------------
def fig_linkage():
    g = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    g = g[g.in_panel_years]
    py = pd.read_csv(DATA / "person_year_recip.csv", usecols=["qid", "t", "n_gifts", "has_career_data"])
    by = g.groupby("t").agg(recip=("recip_qid", lambda s: s.notna().mean()), giver=("giver_qid", lambda s: s.notna().mean()))
    car = set(py.loc[py.has_career_data == 1, "qid"])
    by["career"] = g.groupby("t")["recip_qid"].apply(lambda s: s.isin(car).mean())
    by = by[by.index >= 1999]     # 1998 receipts appear only as backlog in the 1999 report
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    last = {c: 100 * by[c].iloc[-1] for c in ("recip", "giver", "career")}
    ypos = {"recip": last["recip"] + 2, "career": last["career"] + 1, "giver": last["giver"] - 3}
    for col, lab, c in [("recip", "Recipient is a linked person", CAT[0]), ("giver", "Giver is a linked person", CAT[1]),
                        ("career", "Recipient has a dated Wikidata career", CAT[2])]:
        ax.plot(by.index, 100 * by[col], color=c, lw=2, marker="o", ms=3)
        ax.text(by.index[-1] + 0.4, ypos[col], lab, color=INK2, fontsize=7, va="center")
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of gift records")
    ax.set_xlim(1998.5, 2023.5)
    ax.spines["right"].set_visible(False)
    ax.set_title("Share of gift records that can be followed through careers, by receipt year")
    save(fig, "fig_linkage", by.reset_index())


def fig_pathways():
    m = pd.read_csv(DATA / "transition_matrix_recip.csv", index_col=0)
    keep = [s for s in m.index if m.loc[s].sum() + m[s].sum() >= 5]
    m = m.loc[keep, keep]
    share = m.div(m.sum(axis=1).replace(0, np.nan), axis=0)
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    bounds = [0, .02, .05, .1, .2, .3, .5, .7, 1.01]
    from matplotlib.colors import BoundaryNorm, ListedColormap
    cmap, norm = ListedColormap(SEQ), BoundaryNorm(bounds, len(SEQ))
    ax.imshow(share.fillna(0).to_numpy(), cmap=cmap, norm=norm, aspect="auto")
    for i in range(len(keep)):
        for j in range(len(keep)):
            n = m.iloc[i, j]
            if n:
                ax.text(j, i, str(n), ha="center", va="center", fontsize=7,
                        color="white" if share.iloc[i, j] >= .3 else INK)
    ax.set_xticks(range(len(keep)), keep, rotation=40, ha="right")
    ax.set_yticks(range(len(keep)), keep)
    ax.set_xlabel("Sector of next organization")
    ax.set_ylabel("Sector of previous organization")
    ax.grid(False)
    ax.set_title("Career pathways of U.S. recipients: moves between organizations (counts; shading = row share)")
    sm_ = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm_, ax=ax, fraction=0.035, pad=0.02, ticks=bounds[:-1] + [1])
    cb.set_label("Share of moves out of the row sector", color=INK2)
    cb.outline.set_visible(False)
    save(fig, "fig_pathways", m.reset_index().rename(columns={"index": "from"}))


def fig_timelines(n=18):
    s = pd.read_csv(DATA / "spells.csv")
    p = pd.read_csv(DATA / "person_recip.csv")
    g = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    s = s[(s.side == "recip") & s.start_year.notna() & ~s.suspect_link & (s.sector != "Unclassified")]
    nsec = s.groupby("qid")["sector"].nunique()
    cand = p[(p.group == "Agency, military, diplomatic staff") & p.qid.isin(nsec[nsec >= 2].index)]
    cand = cand.sort_values(["total_agencies", "total_gifts"], ascending=False).head(n)
    order = cand.sort_values("first_year").qid.tolist()
    fig, ax = plt.subplots(figsize=(7, 0.3 * n + 1.2))
    rows = []
    for i, q in enumerate(order):
        h = s[s.qid == q]
        for r in h.itertuples():
            a, b = max(r.start_year, 1960), min(r.end_year_filled, 2025)
            if b < 1960:
                continue
            ax.barh(i, b - a + 0.9, left=a, height=0.62, color=sector_color(r.sector), edgecolor="white", lw=1)
            rows.append({"qid": q, "label": r.label, "sector": r.sector, "start": r.start_year, "end": r.end_year_filled})
        yrs = g.loc[g.recip_qid == q, "t"].value_counts()
        ax.scatter(yrs.index + 0.45, [i] * len(yrs), s=10 + 4 * np.sqrt(yrs.values), color=INK, zorder=3,
                   edgecolor="white", lw=0.6)
    ax.set_yticks(range(len(order)), cand.set_index("qid").loc[order, "name"])
    ax.invert_yaxis()
    ax.set_xlim(1960, 2026)
    ax.grid(axis="y", visible=False)
    present = [x for x in SECTOR_SLOTS if x in set(s[s.qid.isin(order)].sector)]
    handles = [plt.Rectangle((0, 0), 1, 1, color=SECTOR_COLOR[x]) for x in present] + \
              [plt.Rectangle((0, 0), 1, 1, color=OTHER), plt.Line2D([], [], marker="o", ls="", color=INK, ms=4)]
    ax.legend(handles, present + ["Other (judiciary, party, ceremonial)", "Gifts received (size = count)"],
              ncol=3, fontsize=6.8, frameon=False, loc="upper left", bbox_to_anchor=(0, -0.06))
    ax.set_title("Careers of agency, military, and diplomatic staff who worked in two or more sectors\n"
                 "(Wikidata spells; dots = years with gifts; most observed under several agencies first)")
    save(fig, "fig_career_timelines", pd.DataFrame(rows))


def fig_agency_network():
    g = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    g = g[g.in_panel_years & g.recip_qid.notna() & g.agency.notna()]
    pa = g.groupby("recip_qid")["agency"].apply(lambda s: sorted(set(s)))
    E = {}
    for ags in pa:
        for i in range(len(ags)):
            for j in range(i + 1, len(ags)):
                E[(ags[i], ags[j])] = E.get((ags[i], ags[j]), 0) + 1
    G = nx.Graph()
    for (a, b), w in E.items():
        G.add_edge(a, b, weight=w)
    size = g.groupby("agency").size()
    branch = g.groupby("agency")["branch"].agg(lambda s: s.mode().iloc[0])
    H = nx.Graph()
    H.add_weighted_edges_from((a, b, 1 / np.sqrt(d["weight"])) for a, b, d in G.edges(data=True))
    pos = nx.kamada_kawai_layout(H, weight="weight")
    pos = nx.spring_layout(G, pos=pos, weight="weight", seed=SEED, k=1.6, iterations=30)
    fig, ax = plt.subplots(figsize=(8, 6.2))
    for a, b, d in G.edges(data=True):
        ax.plot(*zip(pos[a], pos[b]), color=MUTED, lw=0.6 + 0.9 * np.sqrt(d["weight"]), alpha=0.55, zorder=1)
    for n in G.nodes:
        ax.scatter(*pos[n], s=25 + 1.5 * np.sqrt(size[n]) * 6, color=BRANCH_COLOR.get(branch[n], OTHER),
                   edgecolor="white", lw=1.5, zorder=2)
        ax.text(pos[n][0], pos[n][1] - 0.055, n.replace("Department of ", "Dept. of ").replace(
            "White House / Executive Office of the President", "White House/EOP"), ha="center", va="top", fontsize=6.3,
            color=INK2, zorder=3)
    hb = [b for b in BRANCH_ORDER if b in set(branch[list(G.nodes)])]
    ax.legend([plt.Line2D([], [], marker="o", ls="", color=BRANCH_COLOR[b], ms=6) for b in hb], hb, frameon=False,
              fontsize=7, loc="lower left", ncol=4, bbox_to_anchor=(0, -0.08))
    ax.axis("off")
    ax.set_title("Agencies connected by shared personnel: a line joins two agencies that reported gifts to the same person\n"
                 "(line width = number of people; dot size = gifts; isolated agencies omitted)")
    save(fig, "fig_agency_network", pd.DataFrame([{"agency_a": a, "agency_b": b, "people": w} for (a, b), w in E.items()]))


def fig_personnel():
    o = pd.read_csv(DATA / "org_year.csv")
    py = pd.read_csv(DATA / "person_year_recip.csv", usecols=["qid", "t", "risk_wd", "move_org", "exit_org", "has_career_data"])
    o2 = o[o.n_recip_linked >= 2]
    by = o2.groupby("t").agg(exit_rate=("exit_rate", "mean"), retention=("country_retention", "mean"),
                             agencies=("agency", "size"))
    inoff = py[(py.risk_wd == 1) & (py.has_career_data == 1)]
    mv = inoff.groupby("t").agg(move=("move_org", "mean"), exit=("exit_org", "mean"), people=("qid", "size"))
    tab = by.join(mv, how="outer").reset_index()
    fig, axes = plt.subplots(3, 1, figsize=(6.5, 6.2), sharex=True)
    for ax, (col, lab, c) in zip(axes, [
            ("exit_rate", "Agency turnover: share of last year's linked recipients not observed this year", CAT[0]),
            ("move", "Linked officials in office who start a job in a new organization (Wikidata)", CAT[1]),
            ("retention", "Agency continuity: share of last year's giving countries that give again", CAT[2])]):
        x = tab.dropna(subset=[col])
        x = x[x.t.between(1999, 2023)]
        ax.plot(x.t, 100 * x[col], color=c, lw=2, marker="o", ms=3)
        ax.set_ylim(0, 100)
        ax.set_ylabel("%")
        ax.set_title(lab, fontsize=8, loc="left")
        events(ax, label=False)
    fig.text(0.01, 0.0, "Dashed lines: " + "; ".join(f"{y} {l}" for y, l in EVENTS.items()), fontsize=7, color=INK2)
    fig.suptitle("Personnel movement and organizational continuity by year (agency-years with 2+ linked recipients)",
                 fontsize=9, color=INK, y=0.99)
    fig.tight_layout()
    save(fig, "fig_personnel_movement", tab)


def fig_network_change():
    n = pd.read_csv(DATA / "network_period.csv")
    y = n[n.window == "year"].sort_values("t")
    panels = [("edges", "Recipient-country ties", CAT[0], 1), ("ties_kept_from_prev", "Agency-country ties kept\nfrom previous year (%)", CAT[1], 100),
              ("modularity", "Modularity (recipient-country)", CAT[2], 1), ("giant_share", "Share of nodes in the\nlargest component (%)", CAT[6], 100)]
    y = y[y.t >= 1999]
    fig, axes = plt.subplots(2, 2, figsize=(7, 4.6), sharex=True)
    axes = axes.ravel()
    for ax, (col, lab, c, k) in zip(axes, panels):
        x = y.dropna(subset=[col])
        ax.plot(x.t, k * x[col], color=c, lw=2, marker="o", ms=3)
        ax.set_title(lab.replace("\n", " "), fontsize=8, loc="left")
        ax.set_ylim(0, None)
        events(ax, label=False)
    fig.suptitle("Change in the interaction network across years (linked recipients x giving countries)", fontsize=9,
                 color=INK, y=1.02)
    fig.tight_layout()
    fig.text(0.01, -0.03, "Dashed lines: " + "; ".join(f"{y} {l}" for y, l in EVENTS.items()), fontsize=7, color=INK2)
    save(fig, "fig_network_change", y[["t"] + [p[0] for p in panels]])


def fig_event_study():
    c = pd.read_csv(DATA / "event_study_coefs.csv")
    c = c[c.outcome == "n_gifts"]
    small = sorted(set(c.loc[c.n_events < 15, "event"]))
    c = c[c.n_events >= 15]          # fewer than 15 events: in the table only
    import textwrap
    evs = [e for e in c.event.unique()]
    ncol = 4
    nrow = int(np.ceil(len(evs) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(7.5, 2.4 * nrow), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, e, col in zip(axes, evs, CAT):
        x = c[(c.event == e) & ~c.not_identified.fillna(False).astype(bool)].sort_values("k")
        ax.axhline(0, color=AXIS, lw=1)
        ax.axvline(-0.5, color=AXIS, lw=0.8, ls=(0, (2, 2)))
        lo, hi = (x.coef - 1.96 * x.se).clip(-4, 6), (x.coef + 1.96 * x.se).clip(-4, 6)
        ax.fill_between(x.k, lo, hi, color=col, alpha=0.18, lw=0)
        ax.plot(x.k, x.coef, color=col, lw=2, marker="o", ms=4)
        miss = c[(c.event == e) & c.not_identified.fillna(False).astype(bool)].k.tolist()
        for k in miss:
            ax.text(k, -3.6, "n.i.", ha="center", fontsize=6.5, color=MUTED)
        ax.set_title("\n".join(textwrap.wrap(f"{e} ({int(x.n_events.iloc[0])} events)", 26)), fontsize=7.5)
        ax.set_xticks(range(-3, 4))
        ax.set_ylim(-4, 6)
    for ax in axes[len(evs):]:
        ax.axis("off")
    for ax in axes[-ncol:]:
        ax.set_xlabel("Years from move")
    for ax in axes[::ncol]:
        ax.set_ylabel("Log change in gifts\n(vs. t-1)")
    fig.suptitle("Gifts received before and after a change of organization (stacked event study, 95% CI)",
                 fontsize=9, color=INK, y=1.03)
    fig.text(0.01, -0.02, "n.i. = no gifts among movers in that year (not identified); CIs clipped at the axis. "
             + (f"Omitted (fewer than 15 events; see tab_event_study): {', '.join(small)}." if small else ""),
             fontsize=7, color=INK2)
    fig.tight_layout()
    save(fig, "fig_event_study", c)


def fig_permutation():
    null = pd.read_csv(DATA / "permutation_null.csv")
    obs = pd.read_csv(FIG.parent / "tables" / "tab_permutation.csv").set_index("Administration")
    cols = list(null.columns)
    fig, axes = plt.subplots(1, len(cols), figsize=(8, 1.9), sharey=True)
    for ax, ccol in zip(axes, cols):
        v = null[ccol].dropna()
        ax.hist(v, bins=20, color=CAT[0], alpha=0.75, edgecolor="white", lw=0.6)
        o = obs.loc[ccol, "Observed rho (betweenness, prior moves)"]
        ax.axvline(o, color=INK, lw=1.6)
        ax.set_title(ccol, fontsize=7.5)
        ax.tick_params(labelsize=6.5)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
    axes[0].set_ylabel("Rewired graphs")
    fig.suptitle("Correlation of betweenness with prior cross-sector moves: observed (black line) vs. 200 degree-preserving "
                 "rewirings", fontsize=8.5, color=INK, y=1.1)
    save(fig, "fig_permutation", null)


def main():
    fig_linkage()
    fig_pathways()
    fig_timelines()
    fig_agency_network()
    fig_personnel()
    fig_network_change()
    fig_event_study()
    fig_permutation()
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
