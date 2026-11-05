"""Tables and models for the revised analysis.

Reads analysis_revised/data/ (built by 02_build_data.py) and writes LaTeX + CSV
tables to analysis_revised/output/tables/ and the numbers quoted in the memo to
analysis_revised/output/numbers.json.

Every table carries an 'evidence type' line saying what kind of comparison it
makes: between people, within a person over time, within an organization over
time, persistence of a network, or a cross-sectional association.

Run from the repo root:
  /home/arpie/envs/revised/bin/python analysis_revised/03_models.py
"""

import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA, OUTJ, SEED, PERIODS, SECTORS, ppml_fe, ols_fe, regtable, write_tex, stars, fix_mojibake,
                    FIRST_YEAR, LAST_YEAR)

N_PERM = 200            # permutations / rewirings / placebo draws
NUM = {}


def load():
    py = pd.read_csv(DATA / "person_year_recip.csv", low_memory=False)
    py["log_career"] = np.log1p(py["career_len"])
    py["log_tenure"] = np.log1p(py["tenure_org"])
    py["log_prior_gifts"] = np.log1p(py["prior_gifts"])
    py["log_prior_countries"] = np.log1p(py["prior_countries"])
    py["cur_sector"] = py["cur_sector"].fillna("None")
    return py


# ---------------------------------------------------------------------------
# A. Linkage audit tables
# ---------------------------------------------------------------------------
def tables_audit():
    b = json.loads((DATA / "build_numbers.json").read_text())["audit"]
    st = pd.read_csv(DATA / "audit_link_status.csv")
    st["share"] = (100 * st["share"]).round(1)
    t = st.pivot_table(index="status", columns="side", values=["records", "share"], aggfunc="first").fillna(0)
    t.columns = [f"{s} {v}" for v, s in t.columns]
    t = t[["recip records", "recip share", "giver records", "giver share"]].reset_index()
    t.columns = ["Link status", "Recipient records", "Recipient %", "Giver records", "Giver %"]
    for c in ["Recipient records", "Giver records"]:
        t[c] = t[c].astype(int)
    write_tex(t, "tab_audit_status", "Identifier status of gift records",
              note="QID (organization/state/suspect link): the linked Wikidata item is not a human (P31 != Q5); "
                   "these records are excluded from person-level panels. NIL: searched, no item found. "
                   "Evidence type: data quality.")
    cov = pd.DataFrame(b["career_coverage"])
    cov = cov.assign(people_share=(100 * cov.people_share).round(1),
                     records_share_of_all=(100 * cov.records_share_of_all).round(1))
    cov = cov[["side", "measure", "people", "people_share", "records_share_of_all"]]
    cov.columns = ["Side", "Career information", "Linked people", "% of linked people", "% of all records"]
    write_tex(cov, "tab_audit_career", "Linked people with usable career information",
              note="A dated spell is a P39 position or P108 employer with a start year. Classified: assigned to a sector. "
                   "Evidence type: data quality.")
    rows = [("Lookup keys (name strings) in masterwiki_new.csv", b["lookup_keys"]),
            ("  keys mapped to two different QIDs (first kept)", b["lookup_keys_conflicting"]),
            ("  exact duplicate key rows (dropped by parser)", b["lookup_exact_duplicate_rows"]),
            ("Recipient QIDs with more than one name form", b["qids_with_name_variants"]["recip"]),
            ("  ... with no name token in common (name change or mislink)", b["qids_variants_no_common_token"]["recip"]),
            ("Giver QIDs with more than one name form", b["qids_with_name_variants"]["giver"]),
            ("  ... with no name token in common", b["qids_variants_no_common_token"]["giver"]),
            ("Same normalized name linked to different QIDs: recipients", b["names_linked_to_multiple_qids"]["recip"]),
            ("Same normalized name linked to different QIDs: givers", b["names_linked_to_multiple_qids"]["giver"]),
            ("Distinct QIDs sharing one Wikidata label (possible duplicates): recipients", b["qid_pairs_same_label"]["recip"]),
            ("Distinct QIDs sharing one Wikidata label: givers", b["qid_pairs_same_label"]["giver"]),
            ("QIDs appearing as both recipient and giver", b["qids_on_both_sides"]),
            ("Recipient records resolved from a bare office (President, VP, First Lady)", b["bare_office_records"]),
            ("Implausible links (dates), recipients: people / records",
             f"{b['implausible_links'].get('recip', {}).get('qids', 0)} / {b['implausible_links'].get('recip', {}).get('records', 0)}"),
            ("Implausible links (dates), givers: people / records",
             f"{b['implausible_links'].get('giver', {}).get('qids', 0)} / {b['implausible_links'].get('giver', {}).get('records', 0)}")]
    for r in b["nonhuman_qids"]:
        rows.append((f"Non-person QIDs, {r['side']}s, {r['entity_type']}: QIDs / records", f"{r['qids']} / {r['records']}"))
    write_tex(pd.DataFrame(rows, columns=["Check", "Count"]), "tab_audit_checks", "Identifier linkage checks",
              note="Item-level lists are in analysis_revised/data/audit_*.csv. Evidence type: data quality.")
    g = pd.read_csv(DATA / "audit_link_by_group.csv")
    g["recip_linked"] = (100 * g.recip_linked).round(1)
    g["giver_linked"] = (100 * g.giver_linked).round(1)
    g.columns = ["Dimension", "Group", "Records", "% recipients linked", "% givers linked"]
    write_tex(g, "tab_audit_by_group", "Linkage rates by branch, administration, and giver type",
              note="Linkage is far from random: it is highest for the White House and Legislative branches and for "
                   "heads of state, and lowest for intelligence and for 'Other/unknown' givers. Evidence type: data quality.")
    NUM["audit"] = b


# ---------------------------------------------------------------------------
# B. Descriptive tables: careers, transitions, networks
# ---------------------------------------------------------------------------
def tables_careers(py):
    person = pd.read_csv(DATA / "person_recip.csv")
    gy = py[py.n_gifts > 0]
    rows = []
    groups = ["Cabinet level and above", "Family of officials", "Legislators", "Agency, military, diplomatic staff"]
    for grp, p in [("All linked recipients", person)] + [(k, person[person.group == k]) for k in groups]:
        q = set(p.qid)
        pc = p[p.has_career_data == 1]
        yy = gy[gy.qid.isin(q)]
        rows.append({"Group": grp, "People": len(p), "% with dated career": round(100 * p.has_career_data.mean(), 1),
                     "Median career yrs at first gift": pc.entry_career_len.median(),
                     "Median prior orgs at entry": pc.entry_prior_orgs.median(),
                     "Mean prior sector changes at entry": round(pc.entry_trans_sector.mean(), 2),
                     "% any public-private/academic/IO move before entry": round(100 * (pc.entry_trans_domain > 0).mean(), 1),
                     "% ever private before entry": round(100 * pc.entry_ever_private.mean(), 1),
                     "% ever legislature before entry": round(100 * pc.entry_ever_legis.mean(), 1),
                     "% ever military before entry": round(100 * pc.entry_ever_military.mean(), 1),
                     "Median active gift years": p.active_years.median(),
                     "% observed under >1 agency": round(100 * (p.total_agencies > 1).mean(), 1),
                     "Median tenure in org at gift": yy.tenure_org.median(),
                     "Gifts per active year": round(yy.n_gifts.mean(), 2)})
    t = pd.DataFrame(rows).set_index("Group").T.reset_index().rename(columns={"index": "Measure"})
    write_tex(t, "tab_career_desc", "Career duration and mobility of U.S. recipients, by prominence",
              note="Career measures use Wikidata spells that began before the first gift (career at entry). "
                   "Cabinet level and above: held a cabinet-level office or above (Wikidata P39 or the gift title) at any time. "
                   "Family: spouses and children of presidents and vice presidents without cabinet office, or listed as family in most "
                   "of their own records. Legislators: otherwise ever in a legislature or receiving gifts reported by Congress. "
                   "Staff: everyone else. "
                   "Evidence type: differences between people with different career histories (cross-sectional).")
    NUM["career_desc"] = t.to_dict("records")

    # Sector-to-sector transitions (consecutive dated, classified spells, recipients).
    s = pd.read_csv(DATA / "spells.csv")
    s = s[(s.side == "recip") & s.start_year.notna() & (s.sector != "Unclassified") & ~s.suspect_link]
    s = s.sort_values(["qid", "start_year", "end_year_filled"])
    pairs = []
    for q, h in s.groupby("qid"):
        secs = h["sector"].tolist()
        orgs = h["org_id"].tolist()
        for i in range(1, len(secs)):
            if orgs[i] != orgs[i - 1]:
                pairs.append((secs[i - 1], secs[i]))
    m = pd.crosstab(pd.Series([a for a, _ in pairs], name="From"), pd.Series([b for _, b in pairs], name="To"))
    order = [x for x in SECTORS if x in m.index or x in m.columns]
    m = m.reindex(index=order, columns=order, fill_value=0)
    m.to_csv(DATA / "transition_matrix_recip.csv")
    short = {"Monarchy/ceremonial": "Ceremonial", "Intl organization": "IO", "National executive": "Nat. exec.",
             "Academic/research": "Academic", "Legislature": "Legis.", "Subnational": "Subnat.",
             "Diplomatic": "Diplom.", "Judiciary": "Judic.", "Military": "Military", "Private": "Private", "Party": "Party"}
    mt = m.rename(index=short, columns=short).reset_index().rename(columns={"From": "From \\ To"})
    write_tex(mt, "tab_transitions", "Moves between organizations by sector of origin and destination (U.S. recipients)",
              note="Each cell counts consecutive dated spells in different organizations (all years in Wikidata, "
                   "not only 1999-2023). Diagonal: moves between organizations in the same sector. "
                   "Evidence type: description of career pathways.")
    tot = m.values.sum()
    dom = {"Private", "Academic/research", "Intl organization"}
    rev = sum(m.loc[a, b] for a in m.index for b in m.columns if (a in dom) != (b in dom))
    NUM["transitions"] = {"moves": int(tot), "same_sector_share": float(np.trace(m.values) / tot),
                          "public_nonpublic_moves": int(rev), "public_nonpublic_share": float(rev / tot),
                          "into_private": int(m["Private"].sum() - m.loc["Private", "Private"]) if "Private" in m else 0}

    # Network structure by administration.
    n = pd.read_csv(DATA / "network_period.csv")
    p = n[n.window == "period"].copy()
    cols = {"period": "Administration", "years": "Years", "gifts_per_year": "Gifts/yr", "agencies": "Agencies",
            "countries": "Countries", "recipients_linked": "Linked recipients", "agency_country_ties": "Agency-country ties",
            "ties_kept_from_prev": "Ties kept from prev. (%)", "recips_from_prev": "Recipients seen in prev. (%)",
            "agency_country_modularity": "Modularity (agency-country)", "recip_country_giant_share": "Giant comp. share",
            "gini_recip_gifts": "Gini, gifts per recipient", "top10_recip_share": "Top-10 recipients' share"}
    p = p[list(cols)].rename(columns=cols)
    for c in ["Ties kept from prev. (%)", "Recipients seen in prev. (%)", "Top-10 recipients' share"]:
        p[c] = (100 * p[c]).round(1)
    for c in ["Gifts/yr"]:
        p[c] = p[c].round(0).astype(int)
    for c in ["Modularity (agency-country)", "Giant comp. share", "Gini, gifts per recipient"]:
        p[c] = p[c].round(2)
    pt = p.set_index("Administration").T.reset_index().rename(columns={"index": "Measure"})
    write_tex(pt, "tab_network_periods", "Interaction network by administration",
              note="Ties kept: share of the previous administration's agency-country ties observed again. "
                   "Recipients seen in prev.: share of linked recipients also observed in the previous administration. "
                   "Modularity from Louvain communities (seeded). Evidence type: persistence or transformation of a network over time.")
    NUM["network_periods"] = p.to_dict("records")


# ---------------------------------------------------------------------------
# C. Main person-year models
# ---------------------------------------------------------------------------
CAREER_ROWS = [("log_career", "log(1 + career length)"), ("log_tenure", "log(1 + tenure in current org.)"),
               ("n_prior_orgs", "Prior organizations"), ("trans_sector", "Prior cross-sector moves"),
               ("trans_domain", "Prior public/private/academic/IO moves"),
               ("log_prior_gifts", "log(1 + prior gifts)"), ("log_prior_countries", "log(1 + prior countries)"),
               ("elite_now", "Holds cabinet-level office now")]


def main_models(py):
    d = py[(py.risk_main == 1) & (py.has_career_data == 1)].copy()
    d = d[d.cur_sector != "None"]   # in a dated position this year (career measures defined)
    xs_between = ["log_career", "log_tenure", "n_prior_orgs", "trans_sector", "trans_domain", "log_prior_gifts", "elite_now"]
    xs_within = ["log_tenure", "n_prior_orgs", "trans_sector", "trans_domain", "log_prior_gifts", "elite_now"]
    m = [ppml_fe(d, "n_gifts", xs_between, fe=["t", "cur_sector"], cluster="qid"),
         ppml_fe(d, "n_gifts", xs_within, fe=["qid", "t"], cluster="qid"),
         ppml_fe(d, "n_countries", xs_between, fe=["t", "cur_sector"], cluster="qid"),
         ppml_fe(d, "n_countries", xs_within, fe=["qid", "t"], cluster="qid"),
         ppml_fe(d, "n_new_countries", xs_within, fe=["qid", "t"], cluster="qid")]
    regtable(m, ["Gifts", "Gifts", "Countries", "Countries", "New countries"], CAREER_ROWS[:6] + [CAREER_ROWS[7]],
             "tab_main_career", "Career duration, mobility, and the extent of interaction (person-year)",
             note="Poisson PML; SEs clustered by person. Sample: linked recipients with a dated Wikidata career, in years "
                  "they hold a dated U.S. public position or receive a gift. All career and history measures use spells and "
                  "gifts before year t. Columns 1 and 3 compare people (year and current-sector FE); columns 2, 4, 5 compare "
                  "the same person over time (person and year FE); career length is omitted there because it is collinear "
                  "with person and year FE. Evidence type: (1),(3) between people; (2),(4),(5) within person.",
             extra=[("Evidence type", ["between", "within", "between", "within", "within"])])
    NUM["main_career"] = {lab: m_.to_dict() for lab, m_ in zip(["g_between", "g_within", "c_between", "c_within", "new_within"], m)}
    return d, m


def brokerage_models(py):
    """Mobility and bridging position, with degree held fixed (brokerage is not just volume)."""
    d = py[(py.n_countries > 0) & (py.has_career_data == 1) & py.net_c1_degree.notna()].copy()
    d["log_c1_degree"] = np.log(d["net_c1_degree"])
    d["prior_multi_agency"] = (d["prior_agencies"] > 1).astype(int)
    xs = ["trans_sector", "n_prior_orgs", "prior_multi_agency", "log_career", "net_l3_participation", "log_c1_degree"]
    rows = [("trans_sector", "Prior cross-sector moves"), ("n_prior_orgs", "Prior organizations"),
            ("prior_multi_agency", "Observed under >1 U.S. agency before t"), ("log_career", "log(1 + career length)"),
            ("net_l3_participation", "Participation coef., t-3..t-1"), ("log_c1_degree", "log countries at t")]
    d["betw_x100"] = 100 * d["net_c1_betweenness"]
    m = [ols_fe(d, "net_c1_participation", xs, fe=["t", "cur_sector"], cluster="qid"),
         ols_fe(d, "net_c1_participation", [x for x in xs if x != "log_career"], fe=["qid", "t"], cluster="qid"),
         ols_fe(d, "betw_x100", xs, fe=["t", "cur_sector"], cluster="qid"),
         ols_fe(d, "betw_x100", [x for x in xs if x != "log_career"], fe=["qid", "t"], cluster="qid"),
         ols_fe(d, "net_c1_bridging", xs, fe=["t", "cur_sector"], cluster="qid")]
    regtable(m, ["Particip.", "Particip.", "Betweenness x100", "Betweenness x100", "Bridges >1 comm."], rows,
             "tab_brokerage", "Career mobility and brokerage in the recipient-country network (person-year)",
             note="OLS; SEs clustered by person. Network: bipartite U.S. recipient x giving-country graph for year t; "
                  "participation coefficient across Louvain communities; normalized betweenness. Degree (log countries) is "
                  "controlled so that brokerage is not simply volume. Sample: person-years with at least one gift with a "
                  "known country and a dated career. Evidence type: (1),(3),(5) between people; (2),(4) within person.",
             extra=[("Evidence type", ["between", "within", "between", "within", "between"])])
    NUM["brokerage"] = {i: x.to_dict() for i, x in enumerate(m)}

    # Selection: brokerage at entry by pre-entry career.
    p = pd.read_csv(DATA / "person_recip.csv")
    p = p[(p.has_career_data == 1) & p.entry_c1_participation.notna() & (p.entry_countries > 0)].copy()
    p["log_entry_countries"] = np.log(p["entry_countries"])
    p["log_entry_career"] = np.log1p(p["entry_career_len"])
    xs = ["entry_trans_sector", "entry_prior_orgs", "log_entry_career", "entry_ever_private", "entry_ever_military",
          "entry_ever_legis", "log_entry_countries"]
    sel = [ols_fe(p, "entry_c1_participation", xs, fe=["first_year", "entry_branch"]),
           ols_fe(p.assign(b=100 * p.entry_c1_betweenness), "b", xs, fe=["first_year", "entry_branch"]),
           ppml_fe(p, "entry_gifts", xs[:-1], fe=["first_year", "entry_branch"])]
    regtable(sel, ["Participation at entry", "Betweenness x100 at entry", "Gifts at entry"],
             [("entry_trans_sector", "Prior cross-sector moves"), ("entry_prior_orgs", "Prior organizations"),
              ("log_entry_career", "log(1 + career length)"), ("entry_ever_private", "Ever private sector"),
              ("entry_ever_military", "Ever military"), ("entry_ever_legis", "Ever legislature"),
              ("log_entry_countries", "log countries at entry")],
             "tab_selection", "Selection: pre-entry careers and network position in the first year observed",
             note="One row per linked recipient with a dated career, in the first year they receive a gift. Robust SEs. "
                  "Entry-year and entry-branch FE. These coefficients describe who enters central positions (selection), "
                  "not what the position does to the person. Evidence type: differences between people at entry.")
    NUM["selection"] = {i: x.to_dict() for i, x in enumerate(sel)}
    return d


# ---------------------------------------------------------------------------
# D. Event studies around career transitions (stacked design)
# ---------------------------------------------------------------------------
K = 3


def stack(py, event_col, keep_treated=None, rng=None, placebo=False):
    """Stacked event-time panel: clean events (no other move within +/-K) and clean controls.

    Treated: people in U.S. public office the year before a move (so pre-period outcomes
    are not zero by construction). Controls: people in office at g-1 with no move in [g-K, g+K].
    """
    d = py[py.has_career_data == 1]
    moves = d[d[event_col] == 1][["qid", "t"]]
    any_move = d[d["move_org"] == 1].groupby("qid")["t"].apply(list).to_dict()
    in_office = d[d.risk_wd == 1].groupby("qid")["t"].apply(set).to_dict()
    ev = []
    for q, g in moves.itertuples(index=False):
        others = [x for x in any_move.get(q, []) if x != g]
        if any(abs(x - g) <= K for x in others):
            continue
        if (g - 1) not in in_office.get(q, set()) or not (FIRST_YEAR + K <= g <= LAST_YEAR - K):
            continue
        if keep_treated is not None and not keep_treated(q, g):
            continue
        ev.append((q, g))
    if placebo:   # assign the same event years to random non-movers who were in office at g-1
        nonmovers = [q for q in in_office if q not in any_move]
        ev = [(rng.choice([q for q in nonmovers if (g - 1) in in_office[q]] or nonmovers), g) for _, g in ev]
    rows = []
    for g in sorted({g for _, g in ev}):
        tr = {q for q, gg in ev if gg == g}
        ctrl = [q for q, yrs in in_office.items() if (g - 1) in yrs and q not in tr
                and not any(abs(x - g) <= K for x in any_move.get(q, []))]
        w = d[d.qid.isin(tr | set(ctrl)) & d.t.between(g - K, g + K) & (d.risk_main == 1)].copy()
        w["stack"] = g
        w["treated"] = w.qid.isin(tr).astype(int)
        w["rel"] = np.where(w.treated == 1, w.t - g, -99)
        rows.append(w)
    s = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if len(s):
        s["sp"] = s["stack"].astype(str) + "_" + s["qid"]
        s["sy"] = s["stack"].astype(str) + "_" + s["t"].astype(str)
        for k in range(-K, K + 1):
            if k != -1:
                s[f"ev_{k}"] = (s.rel == k).astype(int)
    return s, ev


def event_study(py, event_col, outcome, label, keep_treated=None):
    s, ev = stack(py, event_col, keep_treated)
    # An event-time cell in which no treated person has any interaction is not identified in a
    # Poisson model (the coefficient diverges to -infinity); it is dropped and reported as such.
    zero = [k for k in range(-K, K + 1) if k != -1 and s.loc[s.rel == k, outcome].sum() == 0]
    xs = [f"ev_{k}" for k in range(-K, K + 1) if k != -1 and k not in zero]
    r = ppml_fe(s, outcome, xs, fe=["sp", "sy"], cluster="qid")
    out = r.reset_index().rename(columns={"index": "term"})
    out["k"] = out.term.str.replace("ev_", "").astype(int)
    out = pd.concat([out, pd.DataFrame([{"term": "ev_-1", "coef": 0.0, "se": 0.0, "k": -1}] +
                                       [{"term": f"ev_{k}", "coef": np.nan, "se": np.nan, "k": k} for k in zero])])
    out = out.sort_values("k")
    out["not_identified"] = out.k.isin(zero)
    out["outcome"], out["event"], out["n_events"], out["n"] = outcome, label, len(ev), r.attrs["n"]
    # Pooled post - pre contrast.
    s["post"] = ((s.rel >= 0) & (s.treated == 1)).astype(int)
    s["pre_far"] = (s.rel.isin([-3, -2]) & (s.treated == 1)).astype(int)
    pooled = ppml_fe(s, outcome, ["post", "pre_far"], fe=["sp", "sy"], cluster="qid")
    pooled.attrs["zero_cells"] = zero
    return out, pooled, len(ev), s


def event_studies(py):
    elite_moves = set(map(tuple, py.loc[py.move_into_elite == 1, ["qid", "t"]].to_numpy()))
    staff = set(py.loc[py.staff == 1, "qid"])
    specs = [("move_org", "Any change of organization", None),
             ("move_org", "Lateral/non-cabinet move", lambda q, g: (q, g) not in elite_moves),
             ("move_org", "Move into cabinet-level office", lambda q, g: (q, g) in elite_moves),
             ("move_sector", "Cross-sector move", None),
             ("move_sector", "Cross-sector, non-cabinet", lambda q, g: (q, g) not in elite_moves),
             ("move_org", "Moves by agency/military/diplomatic staff", lambda q, g: q in staff),
             ("move_domain", "Public / non-public move", None)]
    coefs, pooled_rows = [], []
    for col, lab, keep in specs:
        for y in ("n_gifts", "n_countries"):
            try:
                out, pooled, nev, _ = event_study(py, col, y, lab, keep)
            except Exception as e:     # too few events
                print("event study failed", lab, y, e)
                continue
            coefs.append(out)
            pooled_rows.append({"Event": lab, "Outcome": "Gifts" if y == "n_gifts" else "Countries",
                                "Events": nev, "Post (t>=0)": stars(pooled.loc["post", "coef"], pooled.loc["post", "se"]),
                                "SE post": f"({pooled.loc['post', 'se']:.3f})",
                                "Pre (t-3,t-2)": stars(pooled.loc["pre_far", "coef"], pooled.loc["pre_far", "se"]),
                                "SE pre": f"({pooled.loc['pre_far', 'se']:.3f})", "N": pooled.attrs["n"],
                                "Event-time cells with no interactions": ", ".join(map(str, pooled.attrs["zero_cells"])) or "none"})
    c = pd.concat(coefs, ignore_index=True)
    c.to_csv(DATA / "event_study_coefs.csv", index=False)
    pr = pd.DataFrame(pooled_rows)
    write_tex(pr, "tab_event_study", "Interactions before and after career transitions (stacked event study)",
              note="Poisson PML with stack x person and stack x year FE; SEs clustered by person. Treated: linked recipients "
                   "in a dated U.S. public position in g-1 who start a spell in a new organization in g (Wikidata), with no "
                   "other move within 3 years. Controls: people in office in g-1 with no move within 3 years. "
                   "Reference: t-1. 'Pre' tests for anticipation or differential pre-trends. Moves into cabinet-level office "
                   "change the formal position, so their post coefficients are positional, not career effects. Event-time cells "
                   "in which no treated person received anything are not identified and are listed; event types with fewer "
                   "than 30 events are imprecise. "
                   "Evidence type: change within the same person after a career transition.")
    NUM["event_study"] = pooled_rows
    return c


def placebo_events(py, reps=N_PERM):
    rng = np.random.default_rng(SEED)
    draws = []
    for r in range(reps):
        s, ev = stack(py, "move_org", None, rng=rng, placebo=True)
        s["post"] = ((s.rel >= 0) & (s.treated == 1)).astype(int)
        try:
            draws.append(ppml_fe(s, "n_gifts", ["post"], fe=["sp", "sy"], cluster="qid").loc["post", "coef"])
        except Exception:
            continue
    draws = np.array(draws)
    pd.DataFrame({"placebo_post": draws}).to_csv(DATA / "placebo_event_draws.csv", index=False)
    return draws


# ---------------------------------------------------------------------------
# E. Event-history (discrete-time hazard) models
# ---------------------------------------------------------------------------
def logit_cluster(d, y, xs, fe_col, cluster):
    X = pd.get_dummies(d[fe_col].astype(str), prefix="fe", drop_first=True).astype(float)
    X = pd.concat([d[xs].astype(float), X], axis=1)
    X = sm.add_constant(X)
    m = sm.Logit(d[y].astype(float), X).fit(disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cluster])[0]},
                                            maxiter=200)
    res = pd.DataFrame({"coef": m.params[xs], "se": m.bse[xs]})
    res.attrs.update(n=int(m.nobs), clusters=d[cluster].nunique(), ymean=float(d[y].mean()), model="Logit",
                     fe=[f"{fe_col} dummies"])
    return res


def hazards(py):
    d = py[(py.risk_wd == 1) & (py.has_career_data == 1)].copy()
    d = d.sort_values(["qid", "t"])
    d["next_move"] = d.groupby("qid")["move_org"].shift(-1)
    d["l_degree"] = np.log1p(d["net_l3_degree"])
    d["l_betw"] = 100 * d["net_l3_betweenness"]
    xs = ["l_degree", "l_betw", "net_l3_participation", "log_tenure", "log_career", "n_prior_orgs", "trans_sector", "elite_now"]
    rows = [("l_degree", "log(1 + countries), t-3..t-1"), ("l_betw", "Betweenness x100, t-3..t-1"),
            ("net_l3_participation", "Participation coef., t-3..t-1"), ("log_tenure", "log(1 + tenure in org.)"),
            ("log_career", "log(1 + career length)"), ("n_prior_orgs", "Prior organizations"),
            ("trans_sector", "Prior cross-sector moves"), ("elite_now", "Holds cabinet-level office now")]
    d = d.dropna(subset=xs + ["exit_org"])
    m1 = logit_cluster(d, "exit_org", xs, "t", "qid")
    d2 = d.dropna(subset=["next_move"])
    m2 = logit_cluster(d2, "next_move", xs, "t", "qid")
    m3 = logit_cluster(d2[d2.elite_now == 0], "next_move", [x for x in xs if x != "elite_now"], "t", "qid")
    regtable([m1, m2, m3], ["Leaves organization at t", "Moves to new org. at t+1", "Moves (non-cabinet)"], rows,
             "tab_hazard", "Event-history models: organizational exit and career transitions",
             note="Discrete-time logit hazards with year dummies; SEs clustered by person. Sample: person-years in a dated "
                  "U.S. public position (Wikidata). Network measures are lagged (t-3..t-1) so they precede the event. "
                  "Evidence type: does prior network position predict later career events (selection into mobility)?")
    NUM["hazard"] = {"exit": m1.to_dict(), "move": m2.to_dict(), "move_nonelite": m3.to_dict()}
    return [m1, m2, m3]


# ---------------------------------------------------------------------------
# F. Organizations: turnover, continuity, institutional memory
# ---------------------------------------------------------------------------
def org_models():
    o = pd.read_csv(DATA / "org_year.csv")
    o = o.sort_values(["agency", "t"])
    o["log_gifts_prev"] = o.groupby("agency")["log_gifts"].shift(1)
    d = o[(o.n_recip_linked >= 2) & o.country_retention.notna()].copy()
    rows = [("exit_rate", "Share of last year's recipients gone"), ("head_change", "Top recipient changed"),
            ("exit_rate_ident", "Exit share (all identifiable names)"),
            ("log_gifts", "log(1 + gifts) at t"), ("log_gifts_prev", "log(1 + gifts) at t-1")]
    m = [ols_fe(d, "country_retention", ["exit_rate", "log_gifts", "log_gifts_prev"], fe=["agency", "t"], cluster="agency"),
         ols_fe(d, "country_retention", ["head_change", "log_gifts", "log_gifts_prev"], fe=["agency", "t"], cluster="agency"),
         ols_fe(d, "country_jaccard", ["exit_rate", "log_gifts", "log_gifts_prev"], fe=["agency", "t"], cluster="agency"),
         ols_fe(d.dropna(subset=["giver_retention"]), "giver_retention", ["exit_rate", "log_gifts", "log_gifts_prev"],
                fe=["agency", "t"], cluster="agency"),
         ols_fe(d, "country_retention", ["exit_rate_ident", "log_gifts", "log_gifts_prev"], fe=["agency", "t"], cluster="agency")]
    regtable(m, ["Country retention", "Country retention", "Country Jaccard", "Giver retention", "Country retention"], rows,
             "tab_org_continuity", "Personnel turnover and the continuity of agencies' foreign ties (agency-year)",
             note="OLS with agency and year FE; SEs clustered by agency. Country retention: share of the agency's giving "
                  "countries at t-1 that give again at t. Exit share: share of the agency's linked recipients at t-1 who "
                  "receive nothing from it at t. Gift volume at t and t-1 is controlled because retention mechanically rises "
                  "with volume. Column 5 counts unlinked recipients by normalized name. Agency-years with at least two linked "
                  "recipients. Evidence type: change within an organization after personnel turnover.")
    NUM["org"] = {i: x.to_dict() for i, x in enumerate(m)}

    t = pd.read_csv(DATA / "tie_year.csv")
    t["ay"] = t.agency + "_" + t.t.astype(str)
    t["cy"] = t.country + "_" + t.t.astype(str)
    t["log_carriers"] = np.log(t.n_carriers)
    mt = [ols_fe(t, "retained_any", ["all_departed", "log_carriers"], fe=["ay", "cy"], cluster="agency"),
          ols_fe(t, "retained_by_others", ["all_departed", "log_carriers"], fe=["ay", "cy"], cluster="agency"),
          ols_fe(t, "retained_by_others", ["share_departed", "log_carriers"], fe=["ay", "cy"], cluster="agency")]
    regtable(mt, ["Tie kept (anyone)", "Tie kept by others", "Tie kept by others"],
             [("all_departed", "All carriers left the agency"), ("share_departed", "Share of carriers who left"),
              ("log_carriers", "log carriers")],
             "tab_tie_memory", "Do agencies keep a foreign tie when the people who carried it leave? (agency x country x year)",
             note="Linear probability models with agency x year and country x year FE; SEs clustered by agency. Unit: an "
                  "agency-country tie observed at t-1 through linked recipients (carriers). Kept: the country gives to the "
                  "agency again in t..t+2. 'By others': through someone other than the t-1 carriers. A carrier has left if "
                  "never observed under that agency after t-1. Evidence type: change within an organization after personnel "
                  "turnover (institutional memory).")
    NUM["tie"] = {i: x.to_dict() for i, x in enumerate(mt)}
    NUM["tie_means"] = t.groupby("all_departed")[["retained_any", "retained_by_others"]].mean().to_dict()

    mv = pd.read_csv(DATA / "movers.csv")
    rng = np.random.default_rng(SEED)
    res = []
    for lab, a, b in [("Countries: mover vs. others at new agency", "share_B_from_CA", "others_B_share_from_CA"),
                      ("Foreign individuals: mover vs. others at new agency", "share_B_from_GA", "others_B_share_from_GA"),
                      ("Countries: old agency after vs. before the move", "A_after_share_from_CA", "A_before_others_share_from_CA")]:
        x = mv.dropna(subset=[a, b])
        diff = (x[a] - x[b]).to_numpy()
        flips = np.array([np.mean(diff * rng.choice([-1, 1], len(diff))) for _ in range(5000)])
        res.append({"Comparison": lab, "Episodes": len(x), "Mean (first)": round(x[a].mean(), 3),
                    "Mean (second)": round(x[b].mean(), 3), "Difference": round(diff.mean(), 3),
                    "Sign-flip p": round(float(np.mean(np.abs(flips) >= abs(diff.mean()))), 4)})
    r = pd.DataFrame(res)
    write_tex(r, "tab_movers", "Do foreign contacts follow the person or stay with the office?",
              note="Episodes: a linked recipient observed under agency A and later under agency B. Row 1: share of the "
                   "mover's gifts at B from countries that gave to them at A, against the same share among B's other "
                   "recipients in the same years. Row 2: the same for foreign individuals (QIDs). Row 3: at A, the share of "
                   "other recipients' gifts from the mover's countries in the 3 years after vs. before the move. "
                   "p-values from 5,000 sign-flip permutations (seeded). Evidence type: person-level persistence of ties "
                   "across organizations vs. organizational persistence.")
    NUM["movers"] = res


# ---------------------------------------------------------------------------
# G. Permutation tests for brokerage
# ---------------------------------------------------------------------------
def rewire_bipartite(edges, rng, nswap_mult=10):
    """Degree-preserving rewiring of a bipartite edge list (swap right endpoints)."""
    e = [list(x) for x in edges]
    es = set(map(tuple, e))
    m = len(e)
    for _ in range(nswap_mult * m):
        i, j = rng.integers(0, m, 2)
        (a, b), (c, d) = e[i], e[j]
        if a == c or b == d or (a, d) in es or (c, b) in es:
            continue
        es -= {(a, b), (c, d)}
        es |= {(a, d), (c, b)}
        e[i], e[j] = [a, d], [c, b]
    return e


def permutation_tests(py):
    """Is the association between career mobility and brokerage more than degree?

    For each administration, the unweighted recipient-country graph is rewired 200 times
    holding every recipient's and every country's degree fixed. The test statistic is the
    Spearman correlation between a recipient's betweenness and their prior cross-sector
    moves (measured at the start of the period). Under the null the correlation reflects
    only degrees; the observed value is compared with the null distribution.
    """
    inter = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    inter = inter[inter.recip_qid.notna() & inter.country.notna() & inter.in_panel_years]
    rng = np.random.default_rng(SEED)
    out = []
    null_store = {}
    for name, a, b in PERIODS:
        w = inter[inter.t.between(a, b)]
        edges = sorted(set(zip(w.recip_qid, w.country)))
        mob = py[(py.t == a)].set_index("qid")["trans_sector"]
        car = py[(py.t == a)].set_index("qid")["has_career_data"]

        def stat(edge_list):
            G = nx.Graph()
            G.add_edges_from((("L", x), ("R", y)) for x, y in edge_list)
            btw = nx.betweenness_centrality(G, normalized=True)
            s = pd.Series({n[1]: v for n, v in btw.items() if n[0] == "L"})
            keep = [q for q in s.index if car.get(q, 0) == 1]
            if len(keep) < 10:
                return np.nan, s
            return pd.Series(s[keep]).rank().corr(mob.reindex(keep).rank()), s

        obs, s_obs = stat(edges)
        null = []
        for _ in range(N_PERM):
            v, _ = stat(rewire_bipartite(edges, rng))
            null.append(v)
        null = np.array(null)
        null_store[name] = null
        # Concentration of brokerage: share of total betweenness held by the top 5% of recipients.
        top = s_obs.sort_values(ascending=False)
        out.append({"Administration": name, "Recipients": len(s_obs),
                    "Observed rho (betweenness, prior moves)": round(obs, 3),
                    "Null mean": round(np.nanmean(null), 3), "Null 95% range": f"[{np.nanpercentile(null, 2.5):.3f}, {np.nanpercentile(null, 97.5):.3f}]",
                    "Permutation p": round(float(np.mean(np.abs(null - np.nanmean(null)) >= abs(obs - np.nanmean(null)))), 3),
                    "Top-5% share of betweenness": round(top.head(max(1, len(top) // 20)).sum() / top.sum(), 3)})
    r = pd.DataFrame(out)
    write_tex(r, "tab_permutation", "Permutation test: career mobility and brokerage beyond degree",
              note=f"For each administration, {N_PERM} degree-preserving rewirings of the recipient-country graph (seed "
                   f"{SEED}). rho: Spearman correlation between a recipient's betweenness and prior cross-sector moves "
                   "(Wikidata, at the start of the administration), among recipients with a dated career. Two-sided p from "
                   "the null distribution. Evidence type: cross-sectional association, tested against a structural null.")
    pd.DataFrame(null_store).to_csv(DATA / "permutation_null.csv", index=False)
    NUM["permutation"] = out

    # Label permutation for the within-sector regression coefficient (placebo for the career measure).
    d = py[(py.n_countries > 0) & (py.has_career_data == 1) & py.net_c1_degree.notna()].copy()
    d["log_c1_degree"] = np.log(d["net_c1_degree"])
    base = ols_fe(d, "net_c1_participation", ["trans_sector", "log_c1_degree"], fe=["t", "cur_sector"], cluster="qid")
    obs = base.loc["trans_sector", "coef"]
    per = d.groupby("qid")["trans_sector"].mean()
    null = []
    for _ in range(N_PERM):
        sh = pd.Series(rng.permutation(per.to_numpy()), index=per.index)
        dd = d.assign(trans_perm=d["qid"].map(sh))
        null.append(ols_fe(dd, "net_c1_participation", ["trans_perm", "log_c1_degree"], fe=["t", "cur_sector"]).loc["trans_perm", "coef"])
    null = np.array(null)
    NUM["label_permutation"] = {"observed": obs, "null_mean": float(null.mean()), "null_sd": float(null.std()),
                                "p": float(np.mean(np.abs(null) >= abs(obs)))}
    return r


# ---------------------------------------------------------------------------
# H. Robustness
# ---------------------------------------------------------------------------
def robustness(py):
    d0 = py[(py.risk_main == 1) & (py.has_career_data == 1) & (py.cur_sector != "None")].copy()
    xs = ["log_tenure", "n_prior_orgs", "trans_sector", "log_prior_gifts", "elite_now"]
    top_staff = set(py[py.staff == 1].groupby("qid")["n_gifts"].sum().nlargest(10).index)
    samples = [("Main sample", d0),
               ("Excl. cabinet level and above", d0[d0.elite_person == 0]),
               ("Excl. top-25 recipients", d0[d0.top25 == 0]),
               ("Excl. top 1%", d0[d0.top1pct == 0]),
               ("Excl. White House branch", d0[d0.branch_filled.fillna("") != "White House"]),
               ("Agency, military, diplomatic staff only", d0[d0.staff == 1]),
               ("Staff, excl. the 10 most-observed staff", d0[(d0.staff == 1) & ~d0.qid.isin(top_staff)]),
               ("Wikidata tenure years only", d0[d0.risk_wd == 1])]
    rows = []
    for lab, d in samples:
        x = [v for v in xs if not (v == "elite_now" and d.elite_now.sum() == 0)]
        for y in ("n_gifts", "n_countries"):
            try:
                r = ppml_fe(d, y, x, fe=["qid", "t"], cluster="qid")
            except Exception as e:
                print("robustness failed", lab, y, e)
                continue
            rows.append({"Sample": lab, "Outcome": "Gifts" if y == "n_gifts" else "Countries",
                         "Tenure": stars(r.loc["log_tenure", "coef"], r.loc["log_tenure", "se"]),
                         "Prior orgs": stars(r.loc["n_prior_orgs", "coef"], r.loc["n_prior_orgs", "se"]),
                         "Cross-sector moves": stars(r.loc["trans_sector", "coef"], r.loc["trans_sector", "se"]),
                         "Prior gifts": stars(r.loc["log_prior_gifts", "coef"], r.loc["log_prior_gifts", "se"]),
                         "People": d.qid.nunique(), "N": r.attrs["n"]})
    write_tex(pd.DataFrame(rows), "tab_robust_samples", "Robustness: excluding prominent people and branches (within-person models)",
              note="Poisson PML with person and year FE, as in Table tab_main_career columns 2 and 4; SEs clustered by person "
                   "(not shown; stars at 5/1/0.1%). Evidence type: within person.")
    NUM["robust_samples"] = rows

    # Alternative definitions of a career transition.
    rows = []
    for col, lab in [("trans_sector", "Any sector change (main)"), ("trans_strict", "Sector change, sequential spells only"),
                     ("trans_domain", "Public / private / academic / IO change"), ("trans_org", "Any change of organization")]:
        for y in ("n_gifts", "n_countries"):
            r = ppml_fe(d0, y, ["log_tenure", col, "log_prior_gifts", "elite_now"], fe=["qid", "t"], cluster="qid")
            rb = ppml_fe(d0, y, ["log_career", "log_tenure", col, "log_prior_gifts", "elite_now"], fe=["t", "cur_sector"], cluster="qid")
            rows.append({"Definition": lab, "Outcome": "Gifts" if y == "n_gifts" else "Countries",
                         "Within person": stars(r.loc[col, "coef"], r.loc[col, "se"]), "SE (within)": f"({r.loc[col, 'se']:.3f})",
                         "Between people": stars(rb.loc[col, "coef"], rb.loc[col, "se"]), "SE (between)": f"({rb.loc[col, 'se']:.3f})"})
    write_tex(pd.DataFrame(rows), "tab_robust_transitions", "Robustness: alternative definitions of a career transition",
              note="Coefficient on the cumulative count of prior transitions under each definition. Within: person and year "
                   "FE. Between: year and current-sector FE, with career length. Poisson PML; SEs clustered by person.")
    NUM["robust_transitions"] = rows

    # Alternative network windows for the brokerage persistence and hazard models.
    rows = []
    d = py[(py.n_countries > 0) & (py.has_career_data == 1) & py.net_c1_degree.notna()].copy()
    d["log_c1_degree"] = np.log(d["net_c1_degree"])
    h = py[(py.risk_wd == 1) & (py.has_career_data == 1)].sort_values(["qid", "t"]).copy()
    h["next_move"] = h.groupby("qid")["move_org"].shift(-1)
    for w, lab in [("l3", "t-3..t-1 (main)"), ("l5", "t-5..t-1"), ("cum", "All prior years")]:
        r1 = ols_fe(d, "net_c1_participation", ["trans_sector", f"net_{w}_participation", "log_c1_degree"],
                    fe=["t", "cur_sector"], cluster="qid")
        hh = h.assign(ld=np.log1p(h[f"net_{w}_degree"]), lb=100 * h[f"net_{w}_betweenness"]).dropna(subset=["next_move", "log_tenure"])
        r2 = logit_cluster(hh, "next_move", ["ld", "lb", "log_tenure", "elite_now"], "t", "qid")
        rows.append({"Window": lab,
                     "Particip. at t on lagged particip.": stars(r1.loc[f"net_{w}_participation", "coef"], r1.loc[f"net_{w}_participation", "se"]),
                     "... on prior moves": stars(r1.loc["trans_sector", "coef"], r1.loc["trans_sector", "se"]),
                     "Move at t+1 on lagged degree": stars(r2.loc["ld", "coef"], r2.loc["ld", "se"]),
                     "Move at t+1 on lagged betweenness": stars(r2.loc["lb", "coef"], r2.loc["lb", "se"])})
    write_tex(pd.DataFrame(rows), "tab_robust_windows", "Robustness: alternative network windows",
              note="Columns 1-2: OLS with year and current-sector FE, controlling log countries at t. Columns 3-4: logit "
                   "hazard of moving to a new organization at t+1 with year dummies, controlling tenure and cabinet office. "
                   "SEs clustered by person.")
    NUM["robust_windows"] = rows

    # Organization models restricted to linked vs all identifiable recipients is in tab_org_continuity col. 5.


# ---------------------------------------------------------------------------
# I. Who brokers? Ordinary staff and foreign intermediaries
# ---------------------------------------------------------------------------
def broker_tables(py):
    inter = pd.read_csv(DATA / "interactions.csv", low_memory=False)
    inter = inter[inter.in_panel_years]
    # U.S. side: full-period agency-person-country graph (people connect agencies and countries).
    w = inter[inter.recip_qid.notna()]
    G = nx.Graph()
    for (q, a), n in w.groupby(["recip_qid", "agency"]).size().items():
        G.add_edge(("P", q), ("A", a), weight=n)
    for (q, c), n in w.dropna(subset=["country"]).groupby(["recip_qid", "country"]).size().items():
        G.add_edge(("P", q), ("C", c), weight=n)
    btw = nx.betweenness_centrality(G, normalized=True)
    person = pd.read_csv(DATA / "person_recip.csv").set_index("qid")
    rows = []
    for (typ, q), v in btw.items():
        if typ != "P":
            continue
        rows.append({"qid": q, "betweenness": v, "agencies": sum(1 for n in G[("P", q)] if n[0] == "A"),
                     "countries": sum(1 for n in G[("P", q)] if n[0] == "C")})
    b = pd.DataFrame(rows).set_index("qid").join(person[["name", "total_gifts", "elite_person", "top25", "entry_branch",
                                                         "group", "has_career_data"]])
    suspect = set(pd.read_csv(DATA / "audit_implausible_links.csv")["qid"])
    b["suspect_link"] = b.index.isin(suspect)
    b = b.sort_values("betweenness", ascending=False)
    b.to_csv(DATA / "brokers_recip.csv")
    # A person with one gift who is the only tie of a small agency scores high betweenness
    # by construction, so the ranking requires at least three gifts and a plausible link.
    elig = b[(b.total_gifts >= 3) & ~b.suspect_link]
    tabs = []
    for grp in ["Agency, military, diplomatic staff", "Legislators"]:
        x = elig[elig.group == grp].head(10).reset_index()
        x["Group"] = "Staff" if grp.startswith("Agency") else "Legislators"
        tabs.append(x)
    t = pd.concat(tabs)[["Group", "name", "entry_branch", "agencies", "countries", "total_gifts", "betweenness"]]
    t["betweenness"] = (1000 * t["betweenness"]).round(2)
    t.columns = ["Group", "Recipient", "First branch", "Agencies", "Countries", "Gifts", "Betweenness x1000"]
    write_tex(t, "tab_brokers_ordinary", "Brokers below cabinet level: agency staff and legislators",
              note="Betweenness in the 1998-2023 tripartite graph of linked U.S. recipients, reporting agencies, and giving "
                   "countries: a person scores high by connecting agencies and governments that are otherwise far apart. "
                   "People with at least 3 gifts and a plausible identifier link. Evidence type: cross-sectional (whole period).")
    top = elig.head(len(elig) // 10)
    NUM["brokers"] = {"eligible": len(elig), "top_decile_share_by_group": top.group.value_counts(normalize=True).to_dict(),
                      "eligible_share_by_group": elig.group.value_counts(normalize=True).to_dict(),
                      "share_people_multi_agency": float((b.agencies > 1).mean())}

    gn = pd.read_csv(DATA / "network_giver_period.csv")
    allp = gn[gn.period == "All years"].copy()
    names = inter.dropna(subset=["giver_qid"]).drop_duplicates("giver_qid").set_index("giver_qid")
    allp["name"] = allp.qid.map(names["giver_wikiname"]).map(fix_mojibake)
    allp["role"] = allp.qid.map(names["giver_role"])
    allp["country"] = allp.qid.map(names["country"])
    allp = allp.sort_values("betweenness", ascending=False)
    allp.to_csv(DATA / "brokers_giver.csv", index=False)
    non_head = allp[~allp.role.isin(["Head of state/govt", "Royalty"])].head(15)
    t = non_head[["name", "country", "role", "degree", "n_branches", "betweenness"]].copy()
    t["betweenness"] = (1000 * t["betweenness"]).round(2)
    t.columns = ["Foreign official", "Country", "Giver type", "U.S. agencies", "U.S. branches", "Betweenness x1000"]
    write_tex(t, "tab_brokers_foreign", "Foreign intermediaries who connect U.S. agencies (excluding heads of state and royalty)",
              note="Betweenness in the 1998-2023 bipartite graph of linked foreign givers and U.S. reporting agencies. "
                   "Evidence type: cross-sectional (whole period).")
    g = allp.assign(head=allp.role.isin(["Head of state/govt", "Royalty"]))
    NUM["foreign_brokers"] = {"share_multi_agency": float((allp.degree > 1).mean()),
                              "share_multi_agency_heads": float((g[g["head"]].degree > 1).mean()),
                              "share_multi_agency_others": float((g[~g["head"]].degree > 1).mean()),
                              "top_decile_share_heads": float(g.head(len(g) // 10)["head"].mean())}


def main():
    py = load()
    tables_audit()
    tables_careers(py)
    print("main models", flush=True)
    main_models(py)
    brokerage_models(py)
    print("event studies", flush=True)
    event_studies(py)
    draws = placebo_events(py)
    s, _ = stack(py, "move_org")
    s["post"] = ((s.rel >= 0) & (s.treated == 1)).astype(int)
    obs = ppml_fe(s, "n_gifts", ["post"], fe=["sp", "sy"], cluster="qid").loc["post", "coef"]
    NUM["placebo_events"] = {"observed_post": obs, "placebo_mean": float(draws.mean()), "placebo_sd": float(draws.std()),
                             "p": float(np.mean(np.abs(draws) >= abs(obs))), "draws": len(draws)}
    print("hazards / org", flush=True)
    hazards(py)
    org_models()
    print("permutations", flush=True)
    permutation_tests(py)
    print("robustness", flush=True)
    robustness(py)
    broker_tables(py)
    OUTJ.write_text(json.dumps(NUM, indent=2, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    print("done")


if __name__ == "__main__":
    main()
