"""Paper-ready tables and figures for the revised empirical section of paper/gifts_living_data.tex.

Reads the revised-analysis data (02) and model outputs (03); re-estimates only the
compact specifications the paper reports (same estimators, samples, and seeds as 03).
Writes to analysis_revised/output/paper/ and copies the .tex tables and .pdf figures into
paper/tables/rev_*.tex and paper/figures/rev_*.pdf (new names: no existing paper file is
overwritten). Numbers quoted in the paper prose are written to output/paper/paper_numbers_revised.json.

Run from the repo root, after 03_models.py:
  /home/arpie/envs/revised/bin/python analysis_revised/06_paper_outputs.py
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BASE, DATA, REV, SEED, ppml_fe, ols_fe, stars, tex_escape, fix_mojibake


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "").lstrip("0123456789_"), HERE / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load("03_models.py")
B = _load("02_build_data.py")
F = _load("04_figures.py")

OUT = REV / "output" / "paper"
PAPER_TAB = BASE / "paper" / "tables"
PAPER_FIG = BASE / "paper" / "figures"
NUMS = json.loads((REV / "output" / "numbers.json").read_text())
P = {}          # numbers quoted in the paper


def tex_table(rows, header, name, align=None, panels=None):
    """booktabs tabular; `panels` maps a row index to a panel heading inserted before it."""
    align = align or "l" + "c" * (len(header) - 1)
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    for i, r in enumerate(rows):
        if panels and i in panels:
            if i:
                lines.append(r"\midrule")
            lines.append(rf"\multicolumn{{{len(header)}}}{{l}}{{\emph{{{panels[i]}}}}} \\")
        lines.append(" & ".join(str(c) for c in r) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.tex").write_text("\n".join(lines) + "\n")
    pd.DataFrame(rows, columns=header).to_csv(OUT / f"{name}.csv", index=False)


def cell(m, v):
    if v not in m.index:
        return "", ""
    return stars(m.loc[v, "coef"], m.loc[v, "se"]), f"({m.loc[v, 'se']:.3f})"


def coef_rows(models, rows):
    out = []
    for v, lab in rows:
        c = [lab] + [cell(m, v)[0] for m in models]
        s = [""] + [cell(m, v)[1] for m in models]
        out += [c, s]
    return out


def footer(models, evidence, fe):
    return [["Evidence type"] + evidence,
            ["Fixed effects"] + fe,
            ["People"] + [f"{m.attrs['clusters']:,}" for m in models],
            ["Person-years"] + [f"{m.attrs['n']:,}" for m in models]]


def d(m, v):
    return {"coef": float(m.loc[v, "coef"]), "se": float(m.loc[v, "se"])}


# ---------------------------------------------------------------------------
# 1. Position versus career
# ---------------------------------------------------------------------------
def position_table(py):
    s = py[(py.risk_main == 1) & (py.has_career_data == 1) & (py.cur_sector != "None")]
    nc = s[s.elite_person == 0]
    xb = ["log_career", "log_tenure", "n_prior_orgs", "trans_sector", "trans_domain", "log_prior_gifts", "elite_now"]
    xw = [x for x in xb if x != "log_career"]
    m = [ppml_fe(s, "n_gifts", xb, fe=["t", "cur_sector"], cluster="qid"),
         ppml_fe(s, "n_gifts", xw, fe=["qid", "t"], cluster="qid"),
         ppml_fe(nc, "n_gifts", xb[:-1], fe=["t", "cur_sector"], cluster="qid"),
         ppml_fe(nc, "n_gifts", xw[:-1], fe=["qid", "t"], cluster="qid")]
    rows = [("elite_now", "Holds cabinet-level office"), ("log_career", "log(1 + career length)"),
            ("log_tenure", "log(1 + tenure in organization)"), ("log_prior_gifts", "log(1 + prior appearances)"),
            ("n_prior_orgs", "Prior organizations"), ("trans_sector", "Prior cross-sector moves"),
            ("trans_domain", "Prior public/private/academic/IO moves")]
    body = coef_rows(m, rows) + footer(m, ["B", "W", "B", "W"],
                                       ["year, sector", "person, year", "year, sector", "person, year"])
    tex_table(body, ["", "(1) All", "(2) All", "(3) No cabinet", "(4) No cabinet"], "rev_tab_position")
    P["position"] = {k: {v: d(mm, v) for v in mm.index} for k, mm in zip(["B_all", "W_all", "B_nocab", "W_nocab"], m)}
    P["position"]["n"] = {k: {"people": mm.attrs["clusters"], "obs": mm.attrs["n"]} for k, mm in
                          zip(["B_all", "W_all", "B_nocab", "W_nocab"], m)}
    P["position"]["cabinet_multiplier_B"] = float(np.exp(m[0].loc["elite_now", "coef"]))
    P["position"]["cabinet_multiplier_W"] = float(np.exp(m[1].loc["elite_now", "coef"]))


def event_table():
    ev = {(r["Event"], r["Outcome"]): r for r in NUMS["event_study"]}
    keep = [("Move into cabinet-level office", "Into cabinet-level office"),
            ("Lateral/non-cabinet move", "Lateral or non-cabinet move"),
            ("Moves by agency/military/diplomatic staff", "Move by agency, military, or diplomatic staff"),
            ("Any change of organization", "Any change of organization")]
    rows = []
    for key, lab in keep:
        g, c = ev[(key, "Gifts")], ev[(key, "Countries")]
        rows.append([lab, g["Events"], g["Post (t>=0)"], g["Pre (t-3,t-2)"], c["Post (t>=0)"], c["Pre (t-3,t-2)"]])
        rows.append(["", "", g["SE post"], g["SE pre"], c["SE post"], c["SE pre"]])
    tex_table(rows, ["Move", "Events", "Gifts: after", "Gifts: before", "Countries: after", "Countries: before"],
              "rev_tab_events")
    P["events"] = {lab: {"gifts": ev[(k, "Gifts")], "countries": ev[(k, "Countries")]} for k, lab in keep}
    P["placebo_events"] = NUMS["placebo_events"]


def fig_position_events():
    c = pd.read_csv(DATA / "event_study_coefs.csv")
    c = c[c.outcome == "n_gifts"]
    evs = [("Move into cabinet-level office", "Into cabinet-level\noffice"),
           ("Lateral/non-cabinet move", "Lateral or\nnon-cabinet move"),
           ("Moves by agency/military/diplomatic staff", "Moves by agency, military,\nor diplomatic staff")]
    fig, axes = plt.subplots(1, 3, figsize=(6.8, 2.4), sharey=True)
    for ax, (e, lab), col in zip(axes, evs, F.CAT):
        x = c[(c.event == e) & ~c.not_identified.fillna(False).astype(bool)].sort_values("k")
        ax.axhline(0, color=F.AXIS, lw=1)
        ax.axvline(-0.5, color=F.AXIS, lw=0.8, ls=(0, (2, 2)))
        ax.fill_between(x.k, (x.coef - 1.96 * x.se).clip(-3, 5), (x.coef + 1.96 * x.se).clip(-3, 5), color=col,
                        alpha=0.18, lw=0)
        ax.plot(x.k, x.coef, color=col, lw=2, marker="o", ms=4)
        ax.set_title(f"{lab} ({int(x.n_events.iloc[0])} moves)", fontsize=7.5)
        ax.set_xticks(range(-3, 4))
        ax.set_ylim(-3, 5)
        ax.set_xlabel("Years from move")
    axes[0].set_ylabel("Log change in gifts (vs. t-1)")
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "rev_fig_position_events.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    fig.savefig(OUT / "rev_fig_position_events.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    c[c.event.isin([e for e, _ in evs])].to_csv(OUT / "rev_fig_position_events.csv", index=False)


# ---------------------------------------------------------------------------
# 2. Organizational continuity
# ---------------------------------------------------------------------------
def continuity_table():
    t = pd.read_csv(DATA / "tie_year.csv")
    t["ay"] = t.agency + "_" + t.t.astype(str)
    t["cy"] = t.country + "_" + t.t.astype(str)
    t["log_carriers"] = np.log(t.n_carriers)
    outs = [("retained_any", "Any personnel"), ("retained_by_others", "Other personnel"),
            ("retained_by_carrier", "Original carrier")]
    means = t.groupby("all_departed")[[o for o, _ in outs]].mean()
    n_by = t.groupby("all_departed").size()
    m = [ols_fe(t, o, ["all_departed", "log_carriers"], fe=["ay", "cy"], cluster="agency") for o, _ in outs]
    rows = [["Carriers: at least one stays"] + [f"{100 * means.loc[0, o]:.1f}" for o, _ in outs] + [f"{n_by[0]:,}"],
            ["Carriers: all leave"] + [f"{100 * means.loc[1, o]:.1f}" for o, _ in outs] + [f"{n_by[1]:,}"],
            ["All carriers leave (LPM)"] + [cell(mm, "all_departed")[0] for mm in m] + [""],
            [""] + [cell(mm, "all_departed")[1] for mm in m] + [""],
            ["Ties / agencies (clusters)"] + [f"{mm.attrs['n']:,} / {mm.attrs['clusters']}" for mm in m] + [""]]
    tex_table(rows, ["", "Any personnel", "Other personnel", "Original carrier", "Ties"], "rev_tab_continuity",
              panels={0: "A. Share of ties that recur within three years (\\%)",
                      2: "B. Difference when all carriers leave (agency-year and country-year FE)"})
    P["continuity"] = {"means": {o: {"stay": float(means.loc[0, o]), "leave": float(means.loc[1, o])} for o, _ in outs},
                       "n_ties": {"stay": int(n_by[0]), "leave": int(n_by[1])},
                       "lpm": {o: d(mm, "all_departed") for (o, _), mm in zip(outs, m)},
                       "n": m[0].attrs["n"], "agencies": m[0].attrs["clusters"]}

    mv = pd.read_csv(REV / "output" / "tables" / "tab_movers.csv")
    rows = [[r["Comparison"].replace(": ", ": ").replace("vs.", "vs."), r["Episodes"], f"{100 * r['Mean (first)']:.1f}",
             f"{100 * r['Mean (second)']:.1f}", f"{100 * r['Difference']:+.1f}", f"{r['Sign-flip p']:.3f}"]
            for _, r in mv.iterrows()]
    tex_table(rows, ["Comparison", "Episodes", "First (\\%)", "Second (\\%)", "Difference (pts)", "$p$"],
              "rev_tab_movers", align="lccccc")
    P["movers"] = mv.to_dict("records")
    o = NUMS["org"]["0"]
    P["agency_year"] = {"exit_rate": {"coef": o["coef"]["exit_rate"], "se": o["se"]["exit_rate"]},
                        "head_change": {"coef": NUMS["org"]["1"]["coef"]["head_change"],
                                        "se": NUMS["org"]["1"]["se"]["head_change"]}}
    org = pd.read_csv(DATA / "org_year.csv")
    s = org[(org.n_recip_linked >= 2) & org.country_retention.notna()]
    P["agency_year"]["agencies"] = int(s.agency.nunique())
    P["agency_year"]["agency_years"] = int(len(s))
    P["agencies_in_ties"] = int(t.agency.nunique())


# ---------------------------------------------------------------------------
# 3. Positional brokerage
# ---------------------------------------------------------------------------
def broker_table(py):
    inter = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    inter = inter[inter.in_panel_years & inter.recip_qid.notna()]
    edges = B.edge_counts(inter, "recip_qid", "country")
    net, summ = B.bipartite_measures(edges, "qid", "country", SEED)
    net = net.set_index("qid")
    br = pd.read_csv(DATA / "brokers_recip.csv").set_index("qid")
    br = br.join(net[["participation", "n_communities"]])
    # Position: the Wikidata spell held in the person's gift years (most recent start in each
    # year, weighted by gifts); for people without one, the reporting agency.
    sp = pd.read_csv(DATA / "spells.csv")
    sp = sp[sp.start_year.notna() & (sp.sector != "Unclassified") & ~sp.suspect_link]
    gy = inter.groupby(["recip_qid", "t"]).size()
    agency = inter.groupby("recip_qid")["agency"].agg(lambda s: s.value_counts().index[0])
    by_q = {q: h for q, h in sp.groupby("qid")}
    # Fallback: the most frequent gift-record title that names an office (parser fragments such as
    # "Jr." or a first name are skipped).
    raw = pd.read_csv(BASE / "analysis" / "output" / "gifts_analysis.csv", low_memory=False,
                      usecols=["recip_wiki", "recip_title"]).dropna()
    raw = raw[raw.recip_title.str.contains(r"Chief|Secretary|Director|Under|Assistant|Commander|Admiral|General|"
                                           r"Ambassador|Senator|Advis|Protocol|Deputy|Counselor|Administrator",
                                           regex=True)]
    gift_title = raw.groupby("recip_wiki")["recip_title"].agg(lambda s: s.value_counts().index[0]).to_dict()
    pos = {}
    for q in br.index:
        h, w = by_q.get(q), {}
        if h is not None and q in gy.index.get_level_values(0):
            for t, n in gy.loc[q].items():
                cur = h[(h.start_year <= t) & (h.end_year_filled >= t)]
                if len(cur):
                    lab = cur.sort_values(["start_year", "end_year_filled"]).iloc[-1]["label"]
                    w[lab] = w.get(lab, 0) + n
        pos[q] = max(w, key=w.get) if w else gift_title.get(q) or f"({agency.get(q, '')})"
    br["title"] = pd.Series(pos).map(fix_mojibake)
    elig = br[(br.total_gifts >= 3) & ~br.suspect_link].sort_values("betweenness", ascending=False)
    elig["rank"] = np.arange(1, len(elig) + 1)
    elig.to_csv(OUT / "rev_brokers_all.csv")
    rows, panels = [], {}
    for grp, lab, n in [("Cabinet level and above", "A. Cabinet level and above", 6),
                        ("Agency, military, diplomatic staff", "B. Agency, military, and diplomatic staff", 8),
                        ("Legislators", "C. Legislators", 6)]:
        panels[len(rows)] = lab
        for q, r in elig[elig.group == grp].head(n).iterrows():
            t = r["title"] if isinstance(r["title"], str) else ""
            t = t if len(t) <= 46 else t[:44] + "..."
            rows.append([tex_escape(fix_mojibake(r["name"])), tex_escape(t), int(r["rank"]), f"{1000 * r['betweenness']:.2f}",
                         int(r["countries"]), int(r["agencies"]),
                         f"{r['participation']:.2f}" if r["participation"] == r["participation"] else "",
                         int(r["n_communities"]) if r["n_communities"] == r["n_communities"] else ""])
    tex_table(rows, ["Recipient", "Position held in gift years", "Rank", "Betw.\\,$\\times$1000",
                     "Countries", "Agencies", "Particip.", "Comm."], "rev_tab_brokers",
              align="llcccccc", panels=panels)
    top = elig.head(len(elig) // 10)
    P["brokers"] = {"eligible": len(elig), "top_decile_n": len(top),
                    "top_decile_share": top.group.value_counts(normalize=True).to_dict(),
                    "eligible_share": elig.group.value_counts(normalize=True).to_dict(),
                    "top20_groups": elig.head(20).group.value_counts().to_dict(),
                    "network_modularity": summ.get("modularity"), "n_communities": summ.get("n_communities"),
                    "median_participation_by_group": elig.groupby("group")["participation"].median().to_dict()}


def brokerage_models(py):
    d_ = py[(py.n_countries > 0) & (py.has_career_data == 1) & py.net_c1_degree.notna()].copy()
    d_["log_c1_degree"] = np.log(d_["net_c1_degree"])
    d_["prior_multi_agency"] = (d_["prior_agencies"] > 1).astype(int)
    d_["betw_x100"] = 100 * d_["net_c1_betweenness"]
    xs = ["trans_sector", "n_prior_orgs", "prior_multi_agency"]
    m = [ols_fe(d_, "betw_x100", xs, fe=["t", "cur_sector"], cluster="qid"),
         ols_fe(d_, "betw_x100", xs + ["log_c1_degree"], fe=["t", "cur_sector"], cluster="qid"),
         ols_fe(d_, "net_c1_participation", xs, fe=["t", "cur_sector"], cluster="qid"),
         ols_fe(d_, "net_c1_participation", xs + ["log_c1_degree"], fe=["t", "cur_sector"], cluster="qid"),
         ols_fe(d_, "net_c1_participation", xs + ["log_c1_degree"], fe=["qid", "t"], cluster="qid")]
    rows = [("trans_sector", "Prior cross-sector moves"), ("n_prior_orgs", "Prior organizations"),
            ("prior_multi_agency", "Observed under $>$1 agency before $t$"), ("log_c1_degree", "log countries at $t$ (degree)")]
    body = coef_rows(m, rows) + footer(m, ["B", "B", "B", "B", "W"],
                                       ["year, sector"] * 4 + ["person, year"])
    tex_table(body, ["", "(1) Betw.", "(2) Betw.", "(3) Particip.", "(4) Particip.", "(5) Particip."],
              "rev_tab_brokerage")
    P["brokerage_models"] = {i: {v: d(mm, v) for v in mm.index} for i, mm in enumerate(m)}
    P["brokerage_models"]["n"] = {"obs": m[0].attrs["n"], "people": m[0].attrs["clusters"]}


def fig_null():
    tab = pd.read_csv(REV / "output" / "tables" / "tab_permutation.csv")
    null = pd.read_csv(DATA / "permutation_null.csv")
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    x = np.arange(len(tab))
    lo = [np.nanpercentile(null[a], 2.5) for a in tab.Administration]
    hi = [np.nanpercentile(null[a], 97.5) for a in tab.Administration]
    ax.vlines(x, lo, hi, color=F.CAT[0], lw=6, alpha=0.35, label="Null: middle 95% of 200 rewired graphs")
    ax.scatter(x, tab["Null mean"], color=F.CAT[0], marker="_", s=180, lw=2, label="Null mean", zorder=3)
    ax.scatter(x, tab["Observed rho (betweenness, prior moves)"], color=F.INK, s=28, zorder=4, label="Observed")
    top = max(max(hi), tab["Observed rho (betweenness, prior moves)"].max()) + 0.04
    for i, p in enumerate(tab["Permutation p"]):
        ax.text(i, top, "p<0.005" if p < 0.005 else f"p={p:.2f}", ha="center", fontsize=6.5, color=F.INK2)
    ax.set_ylim(None, top + 0.04)
    ax.axhline(0, color=F.AXIS, lw=1)
    ax.set_xticks(x, tab.Administration)
    ax.set_ylabel("Spearman correlation:\nbetweenness and prior moves")
    ax.legend(frameon=False, fontsize=7, loc="lower left", ncol=3, bbox_to_anchor=(0, -0.38))
    fig.savefig(OUT / "rev_fig_null.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    fig.savefig(OUT / "rev_fig_null.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    tab.assign(null_lo=lo, null_hi=hi).to_csv(OUT / "rev_fig_null.csv", index=False)
    P["permutation"] = tab.to_dict("records")
    P["label_permutation"] = NUMS["label_permutation"]


# ---------------------------------------------------------------------------
# 4. Network change
# ---------------------------------------------------------------------------
def network_table():
    n = pd.read_csv(DATA / "network_period.csv")
    p = n[n.window == "period"]
    y = n[n.window == "year"].set_index("t")
    rows = []
    for _, r in p.iterrows():
        rows.append([r["period"], r["years"], f"{r['gifts_per_year']:.0f}", f"{r['agency_country_ties']:.0f}",
                     "" if pd.isna(r["ties_kept_from_prev"]) else f"{100 * r['ties_kept_from_prev']:.0f}",
                     f"{r['agency_country_modularity']:.2f}", f"{100 * r['top10_recip_share']:.0f}"])
    tex_table(rows, ["Administration", "Years", "Gifts/yr", "Agency-country ties", "Kept from prev. (\\%)",
                     "Modularity", "Top-10 share (\\%)"], "rev_tab_network")
    P["network"] = {"periods": p.to_dict("records"),
                    "ties_kept_2020": float(y.loc[2020, "ties_kept_from_prev"]),
                    "ties_kept_2019": float(y.loc[2019, "ties_kept_from_prev"]),
                    "ties_kept_2021": float(y.loc[2021, "ties_kept_from_prev"]),
                    "edges_2019": float(y.loc[2019, "edges"]), "edges_2020": float(y.loc[2020, "edges"])}


# ---------------------------------------------------------------------------
# 5. Appendix: sample construction
# ---------------------------------------------------------------------------
def sample_table(py):
    b = json.loads((DATA / "build_numbers.json").read_text())
    inter = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    s = py[(py.risk_main == 1) & (py.has_career_data == 1) & (py.cur_sector != "None")]
    t = pd.read_csv(DATA / "tie_year.csv")
    rows = [
        ["Gift records (all report years)", f"{len(inter):,}", ""],
        ["  with receipt year 1998--2023", f"{int(inter.in_panel_years.sum()):,}", "47 backlogged earlier receipts dropped"],
        ["  recipient linked to a human Wikidata item", f"{int((inter.in_panel_years & inter.recip_qid.notna()).sum()):,}",
         "QIDs that are organizations or link errors excluded"],
        ["Linked U.S. recipients", f"{inter.loc[inter.in_panel_years, 'recip_qid'].nunique():,}", ""],
        ["  with a usable (dated, classified) Wikidata career", f"{py.loc[py.has_career_data == 1, 'qid'].nunique():,}",
         "23 implausible links excluded"],
        ["Recipient-year panel, all rows", f"{len(py):,}", "1,015 people $\\times$ 26 years"],
        ["  risk set (dated U.S. public office or a gift that year)", f"{int(py.risk_main.sum()):,}", ""],
        ["  in a dated position that year", f"{len(s):,}",
         f"{P['position']['n']['B_all']['obs']:,} in Table~\\ref{{tab:rev_position}} col.~1 after singletons"],
        ["Agency-country ties observed through linked carriers", f"{len(t):,}", "three later years observable"],
        ["  agencies", f"{t.agency.nunique()}", ""],
        ["Mover episodes (agency A, later agency B)", f"{b['sizes']['mover_episodes']}", ""],
        ["Career spells (P39/P108) of linked people", f"{b['sizes']['spells']:,}",
         f"{b['sizes']['spells_dated']:,} dated; {b['sizes']['spells_unclassified']:,} unclassified"],
    ]
    rows = [[("\\quad " + r[0].strip()) if r[0].startswith("  ") else r[0]] + r[1:] for r in rows]
    tex_table(rows, ["Step", "N", "Note"], "rev_tab_sample", align="lrl")
    P["sample"] = {r[0].replace("\\quad ", ""): r[1] for r in rows}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    py = M.load()
    position_table(py)
    event_table()
    fig_position_events()
    continuity_table()
    broker_table(py)
    brokerage_models(py)
    fig_null()
    network_table()
    sample_table(py)
    (OUT / "paper_numbers_revised.json").write_text(json.dumps(P, indent=2, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    # Copy into the paper (new file names only).
    for f in OUT.glob("rev_*.tex"):
        shutil.copy(f, PAPER_TAB / f.name)
    for f in OUT.glob("rev_*.pdf"):
        shutil.copy(f, PAPER_FIG / f.name)
    shutil.copy(REV / "output" / "figures" / "fig_network_change.pdf", PAPER_FIG / "rev_fig_network_change.pdf")
    print("paper outputs written to", OUT)


if __name__ == "__main__":
    main()
