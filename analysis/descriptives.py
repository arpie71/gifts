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
import time
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests


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
# Who receives, and what recipients share with givers (Wikidata claims)
# ---------------------------------------------------------------------------
INST_CACHE = BASE_DIR / "files" / "institution_country.csv"
HEADERS = {"User-Agent": "Raymond Hicks research script (arpie71@gmail.com)"}
US = "Q30"

# Occupation (P106) labels grouped into broad career types.
OCC_RULES = [
    ("Military", r"military|soldier|army officer|naval officer|air force officer|aviator|general|admiral"),
    ("Diplomat", r"diplomat|ambassador|consul"),
    ("Politician", r"politician|statesperson|head of (?:state|government)|minister|monarch|sovereign"),
    ("Law", r"lawyer|jurist|judge|attorney|prosecutor"),
    ("Economics/business", r"economist|business|entrepreneur|banker|financier|executive"),
    ("Academic", r"university teacher|professor|political scientist|researcher|scientist|historian|academic"),
    ("Civil servant", r"civil servant|official|bureaucrat|intelligence|spy"),
]
# U.S. professional military education: service academies, staff and war colleges.
PME = (r"Military Academy|Naval Academy|Air Force Academy|War College|Command and General Staff|"
       r"National Defense University|Industrial College of the Armed Forces|Eisenhower School|"
       r"Naval Postgraduate School|Air University|Marine Corps University|Air Command and Staff")


def fetch_institution_country(qids):
    """Country (P17) of each educational institution, cached in files/."""
    cache = (pd.read_csv(INST_CACHE) if INST_CACHE.exists()
             else pd.DataFrame(columns=["qid", "country"]))
    todo = sorted(set(qids) - set(cache["qid"]))
    rows = []
    for i in range(0, len(todo), 50):
        r = requests.get("https://www.wikidata.org/w/api.php", headers=HEADERS, timeout=60, params={
            "action": "wbgetentities", "ids": "|".join(todo[i:i + 50]),
            "props": "claims", "format": "json"})
        for qid, ent in r.json().get("entities", {}).items():
            country = ""
            for st in ent.get("claims", {}).get("P17", []):
                if st.get("rank") != "deprecated" and st["mainsnak"].get("datavalue"):
                    country = st["mainsnak"]["datavalue"]["value"]["id"]
                    break
            rows.append({"qid": qid, "country": country})
        time.sleep(1)
    if rows:
        cache = pd.concat([cache, pd.DataFrame(rows)]).drop_duplicates("qid")
        cache.to_csv(INST_CACHE, index=False)
    return dict(zip(cache["qid"], cache["country"].fillna("")))


def person_attributes(claims):
    """One row per QID with set-valued attributes used for matching."""
    c = claims[claims["rank"] != "deprecated"]
    by_prop = lambda p, col="value": c[c["property"] == p].groupby("item")[col].apply(set)
    occ = c[c["property"] == "P106"][["item", "valueLabel"]].dropna()
    occ["type"] = None
    for label, pattern in reversed(OCC_RULES):   # first matching rule wins
        occ.loc[occ["valueLabel"].str.contains(pattern, case=False, regex=True), "type"] = label
    schools = c[c["property"] == "P69"][["item", "value", "valueLabel"]]
    inst = fetch_institution_country(schools["value"].unique())
    schools = schools.assign(country=schools["value"].map(inst).fillna(""))
    born = c[c["property"] == "P569"].groupby("item")["value"].first().str[:4]
    att = pd.DataFrame({
        "gender": by_prop("P21"),
        "occ": occ.dropna(subset=["type"]).groupby("item")["type"].apply(set),
        "school": by_prop("P69"),
        "school_country": schools[schools["country"] != ""].groupby("item")["country"].apply(set),
        "employer": by_prop("P108"),
        "rank": by_prop("P410"),
        "party": by_prop("P102"),
        "born": pd.to_numeric(born, errors="coerce"),
    })
    att["us_pme"] = schools[(schools["country"] == US) & schools["valueLabel"].str.contains(PME, regex=True, na=False)
                            ].groupby("item").size().reindex(att.index).notna()
    # Military career: rank held, or a military occupation.
    att["military"] = att["rank"].notna() | att["occ"].apply(lambda s: isinstance(s, set) and "Military" in s)
    return att


def table_recip_profile(df, att):
    """Who the recipients are, by branch of the reporting agency."""
    q = df[df.recip_has_qid == 1]
    rows = []
    for b in BRANCH_ORDER + ["All"]:
        ids = sorted(set(q.loc[q.branch == b, "recip_wiki"] if b != "All" else q["recip_wiki"]))
        a = att.reindex(ids)
        known = lambda col: a[col].notna()
        has = lambda col, v: a[col].apply(lambda s: isinstance(s, set) and v in s)
        abroad = a["school_country"].apply(lambda s: isinstance(s, set) and bool(s - {US}))
        rows.append({
            "Branch": b, "People": len(ids),
            "Female": pct(has("gender", "Q6581072").sum() / max(known("gender").sum(), 1)),
            "Born (median)": a["born"].median(),
            "Military": pct(a["military"].mean()),
            "Diplomat": pct(has("occ", "Diplomat").mean()),
            "Law": pct(has("occ", "Law").mean()),
            "Party member": pct(known("party").mean()),
            "Studied abroad": pct(abroad.sum() / max(known("school_country").sum(), 1)),
        })
    out = pd.DataFrame(rows)
    out["Born (median)"] = out["Born (median)"].map(lambda x: Raw(f"{x:.0f}") if pd.notna(x) else "")
    write_table(out, "tab_recip_profile")
    return out


def _overlap(a, b):
    """Shared-element indicator and 'both known' mask for two Series of sets."""
    known = np.array([isinstance(x, set) and isinstance(y, set) for x, y in zip(a, b)])
    share = np.array([k and bool(x & y) for x, y, k in zip(a, b, known)])
    return known, share


MATCHES = [
    ("Same gender", "gender"),
    ("Same professional career", "occ"),
    ("Both have military careers", "military"),
    ("Same birth cohort ($\\pm$5 years)", "born"),
    ("Educated in the same country", "school_country"),
    ("Same educational institution", "school"),
    ("Same employer", "employer"),
]
AGENCY_BRANCHES = ["Diplomatic", "Defense", "Intelligence", "Other executive", "Judicial"]


def dyad_matches(rq, gq, att):
    """For each matching rule: (both-known mask, match indicator) for recipient/giver QID arrays."""
    A, B = att.reindex(rq), att.reindex(gq)
    out = {}
    for label, col in MATCHES:
        if col == "born":
            x, y = A["born"].to_numpy(), B["born"].to_numpy()
            known = ~np.isnan(x) & ~np.isnan(y)
            out[label] = (known, known & (np.abs(x - y) <= 5))
        elif col == "military":   # flag known for everyone with claims
            x, y = A["military"].to_numpy(), B["military"].to_numpy()
            known = A["military"].notna().to_numpy() & B["military"].notna().to_numpy()
            out[label] = (known, known & (x == True) & (y == True))
        elif col == "occ":        # professional careers only; "politician" says little
            prof = lambda s: s - {"Politician"} if isinstance(s, set) and s - {"Politician"} else np.nan
            out[label] = _overlap(A["occ"].map(prof).to_numpy(), B["occ"].map(prof).to_numpy())
        else:
            out[label] = _overlap(A[col].to_numpy(), B[col].to_numpy())
    return out


def shared_rates(d, att, reps, rng):
    """Observed match rates, two random-pairing baselines, and a permutation p-value."""
    rq, gq = d["recip_wiki"].to_numpy(), d["giver_wiki"].to_numpy()
    obs = dyad_matches(rq, gq, att)
    groups = {"year": d.groupby("year").indices, "branch_year": d.groupby(["branch", "year"]).indices}
    exp = {k: {label: [] for label, _ in MATCHES} for k in groups}
    for k, idx in groups.items():
        for _ in range(reps):
            perm = np.empty(len(d), dtype=object)
            for rows in idx.values():
                perm[rows] = gq[rng.permutation(rows)]
            for label, (known, share) in dyad_matches(rq, perm, att).items():
                exp[k][label].append(share[known].mean())
    rows = []
    for label, _ in MATCHES:
        known, share = obs[label]
        o = share[known].mean()
        e1, e2 = np.mean(exp["year"][label]), np.array(exp["branch_year"][label])
        rows.append({"label": label, "gifts": int(known.sum()), "obs": o, "exp_year": e1,
                     "exp_branch_year": e2.mean(), "ratio": o / e2.mean(), "ratio_year": o / e1,
                     # 95% range of the branch-year null, as a ratio to its mean
                     "null_lo": np.quantile(e2, 0.025) / e2.mean(), "null_hi": np.quantile(e2, 0.975) / e2.mean(),
                     "p": (1 + (e2 >= o).sum()) / (1 + reps)})
    return pd.DataFrame(rows), obs


def table_shared(df, att, reps=500, seed=20261103):
    """Observed giver-recipient similarity against two random-pairing baselines.

    Baseline 1 shuffles givers among gifts in the same report year; baseline 2
    shuffles them within the same branch and year, so it holds fixed which kinds of
    givers each branch receives (protocol matching) and leaves person-level sorting.
    Panel B repeats this for gifts reported by executive agencies (no White House or Congress).
    """
    rng = np.random.default_rng(seed)
    d = df[(df.recip_has_qid == 1) & (df.giver_has_qid == 1)].reset_index(drop=True)
    panels = [("A. All branches", d),
              ("B. Executive agencies only", d[d.branch.isin(AGENCY_BRANCHES)].reset_index(drop=True))]
    lines = [r"\begin{tabular}{lrrrrrr}", r"\toprule",
             r" & & & \multicolumn{2}{c}{Random pairing (\%)} & & \\ \cmidrule(lr){4-5}",
             r"Shared characteristic & Gifts & Observed (\%) & Same year & Same branch-year & Ratio & $p$ \\",
             r"\midrule"]
    results = {}
    for i, (title, sample) in enumerate(panels):
        res, obs = shared_rates(sample, att, reps, rng)
        results[title] = res
        if i:
            lines.append(r"\addlinespace")
        lines.append(rf"\multicolumn{{7}}{{l}}{{\emph{{{title} ({len(sample):,} gifts with both parties linked)}}}} \\")
        for r in res.itertuples():
            p = "$<$0.01" if r.p < 0.01 else f"{r.p:.2f}"
            lines.append(f"\\quad {r.label} & {r.gifts:,} & {100 * r.obs:.1f} & {100 * r.exp_year:.1f} & "
                         f"{100 * r.exp_branch_year:.1f} & {r.ratio:.2f} & {p} \\\\")
        if i == 0:
            _, school_share = obs["Same educational institution"]
            pairs = (sample[school_share].assign(n=1)
                     .groupby(["recip_wikiname", "giver_wikiname", "branch"])["n"].sum()
                     .sort_values(ascending=False))
    lines += [r"\bottomrule", r"\end{tabular}"]
    (TAB_DIR / "tab_shared.tex").write_text("\n".join(lines) + "\n")
    return results, pairs


def giver_us_education(df, att):
    """Gifts from foreign givers educated in the United States, by branch."""
    q = df[(df.giver_has_qid == 1)]
    a = att.reindex(q["giver_wiki"])
    known = a["school_country"].notna().to_numpy()
    us = a["school_country"].apply(lambda s: isinstance(s, set) and US in s).to_numpy()
    pme = a["us_pme"].fillna(False).to_numpy().astype(bool)
    q = q.assign(known=known, us=us, pme=pme)[known]
    by_branch = q.groupby("branch")[["us", "pme"]].mean()
    people = q.drop_duplicates("giver_wiki")
    return {"giver_edu_known_people": int(len(people)),
            "giver_us_educated_people": int(people["us"].sum()),
            "giver_us_pme_people": int(people["pme"].sum()),
            "giver_us_educated_gift_share": float(q["us"].mean()),
            "giver_us_educated_by_branch": by_branch["us"].round(3).to_dict(),
            "giver_us_pme_by_branch": by_branch["pme"].round(3).to_dict()}


# ---------------------------------------------------------------------------
# Technical, business, and political backgrounds
# ---------------------------------------------------------------------------
EMP_CACHE = BASE_DIR / "files" / "employer_types.csv"

# Scores carried over from the earlier Stata coding (first matching level wins, highest first).
TECH_JOB = [(1.0, r"economist|physician|lawyer|jurist|university teacher|civil servant|judge|barrister|"
                  r"mathematician|scientist|Professor|Technical Adviser|Technical Director|Expert|geneticist"),
            (0.5, r"researcher|teacher|veterinarian|writer")]
TECH_EDU = [(1.0, r"polytechnique|Polytechnic|Institute of Technology|Desarrollo|Ecole Superieure D'Administration|"
                  r"Higher Institute of Social Sciences|Faculty of Medicine|Center for Management Studies|"
                  r"Faculty of Mechanics and Math|Medical School of Paris|Moscow Power Engineering Institute|"
                  r"Paris Demography Institute|Sciences Economiques|Agricultural and Mechanical|"
                  r"National Administrative Institute|ETH Zurich"),
            (0.5, r"Academy of Management of the Ministry|State Transport Univer|Centro de Estudios para el Desarrollo|"
                  r"Centro de Investigación y Docencia|Fiji School of Medicine|Kiev Higher Tank Engineering School|"
                  r"IIT Bombay|nationale d'administration|National Veterinary School|vétérinaire")]
TECH_POS = [(1.0, r"[fF]inance [mM]inister|Minister of Finance|Governor of the State Bank|Governor of the Reserve Bank|"
                  r"[Gg]overnor of the (?:Central )?Bank|Central Bank"),
            (0.75, r"Financial and Administrative Officer|Federal Secretary|Special Representative"),
            (0.5, r"Deputy Director of Border Service|Transportation Expert|[Aa]dvis[eo]r|Board Member|Research Director|"
                  r"Senior Consultant|Specialist Consultant|Special Rapporteur|Political Secretary|Ministro Consejero|"
                  r"economic and financial Division|Administrative Secretary"),
            (0.25, r"Construction organizer|Asesor General|Research assistant|civil servant|research officer")]
# Work in international organizations counts as technical.
IO_PATTERN = (r"United Nations|\bUN\b|UNESCO|UNICEF|UNHCR|World Bank|International Monetary Fund|\bIMF\b|OECD|"
              r"World Health Organization|World Trade Organization|International Atomic Energy|European Commission|"
              r"Secretary[- ]General|Director[- ]General|African Development Bank|Asian Development Bank|"
              r"Inter-American Development Bank|International Labour|Food and Agriculture Organization")
BUSINESS_JOB = (r"businessperson|entrepreneur|banker|financier|business executive|industrialist|investor|"
                r"chief executive|manager|merchant|business magnate|corporate")

# Employer types (P31 label of the employer item).
EMP_RULES = [
    ("IO", r"intergovernmental|international organi[sz]ation|United Nations|specialized agency|"
           r"international financial institution|development bank|multilateral"),
    ("Government", r"government agency|ministry|executive department|federal agency|central bank|"
                   r"independent agency|intelligence agency|national laboratory|regulatory|public body|"
                   r"^government$|civil service|statutory corporation|armed forces|police"),
    ("Academic", r"universit|college|research institute|think tank|school|faculty|academy of sciences|"
                 r"higher education|educational institution|hospital"),
    ("Culture", r"theatre|theater|orchestra|museum|opera|ballet|band\b"),
    ("Business", r"business|enterprise|company|corporation|^bank$|credit institution|law firm|firm|conglomerate|"
                 r"investment|holding|manufacturer|consult|airline|brand|publishing house|newspaper|"
                 r"television|production company|stock exchange|fund|football club|sports club|"
                 r"sports team|media|broadcast|mass media|record label|retail|hotel"),
]

# Recipient office, from the reporting agency.
SECURITY_AGENCIES = r"Homeland Security|Federal Bureau of Investigation|Secret Service|Coast Guard"
# Giver office, from the giver's title in the gift report (checked in order).
GIVER_OFFICE_RULES = [
    ("Technical", r"[Ff]inance|Treasury|Central Bank|Reserve Bank|State Bank|Monetary|Governor of the .*Bank|"
                  r"Director[- ]General|Secretary[- ]General|Commissioner|Ombudsman|Auditor|Statistic|"
                  r"Ministry of|Deputy Minister|Undersecretary|Under Secretary|Permanent Secretary|"
                  r"Advis[eo]r|Expert|Rapporteur|Special Representative|Board Member|Research|Professor|"
                  r"Judge|Court|Attorney General|Prosecutor|Mayor|Head of Department|Chief of Protocol|Director"),
    ("Business", r"Chief Executive|\bCEO\b|Company|Corporation|Airlines|Aramco|Petroleum|Industries|"
                 r"Chamber of Commerce|Group\b|Holding|Enterprise|Chairman of the Board"),
]
ROLE_OFFICE = {"Head of state/govt": "Political", "Royalty": "Political", "Minister": "Political",
               "Legislator": "Political", "Military": "Security", "Intelligence/security": "Security",
               "Diplomat": "Diplomatic", "International org.": "Technical"}
BACKGROUND_ORDER = ["Political", "Technical", "Business", "Military", "Spouse/family", "Unknown"]
OFFICE_ORDER = ["Political", "Technical", "Business", "Diplomatic", "Security", "Unknown"]

# Nature of the gift, from the item description (first matching rule wins).
ITEM_RULES = [
    ("Jewelry", r"necklace|bracelet|earring|brooch|\bring\b|rings\b|jewel|pendant|cufflink|cuff link|diamond|"
                r"emerald|sapphire|ruby|pearl"),
    ("Watch", r"\bwatch|wristwatch|timepiece|Rolex|Cartier|Omega|Seiko|Patek|Breitling|Tag Heuer"),
    ("Weapon/ceremonial", r"sword|dagger|khanjar|knife|rifle|pistol|gun\b|shotgun|saber|sabre|jambiya|scabbard|fire ?arm|"
                          r"AK.?47|bayonet|blade|"
                          r"medal|plaque|coin"),
    ("Art/decorative", r"painting|portrait|sculpture|statue|figurine|vase|bowl|tray|carpet|\brug|tapestry|"
                       r"crystal|porcelain|ceramic|silver|gold|bronze|lithograph|print\b|photograph|frame|"
                       r"model|clock|box|dish|plate|lamp|mosaic|artwork|calligraphy|incense|candle"),
    ("Clothing/textile", r"robe|dress|shirt|scarf|shawl|suit|jacket|coat|cloth|fabric|textile|garment|bisht|"
                         r"kimono|silk|cashmere|pashmina|handbag|purse|bag\b|shoes|boots|hat\b|tie\b|belt"),
    ("Book/media", r"\bbook|album|DVD|\bCD\b|map\b|manuscript|Koran|Quran|atlas|stamp"),
    ("Food/drink", r"wine|whisk|liquor|cognac|vodka|champagne|tea\b|coffee|dates\b|chocolate|caviar|food|"
                   r"honey|saffron|beverage|sake"),
]


def _score(labels, rules):
    """Highest score among the regex levels that match any label."""
    for value, pattern in rules:
        if labels.str.contains(pattern, regex=True, na=False).any():
            return value
    return 0.0


def employer_kind():
    """IO / Government / Academic / Business for each employer QID, from its P31 types (cached)."""
    t = pd.read_csv(EMP_CACHE).fillna("")
    kinds = {}
    for qid, g in t.groupby("qid"):
        labels = " | ".join(g["p31_label"])
        kinds[qid] = next((k for k, pat in EMP_RULES if re.search(pat, labels, re.I)), "Other")
    return kinds


# Positions held (P39) by kind of career, checked in order.
POSITION_RULES = [
    ("Technical", TECH_POS[0][1] + "|" + TECH_POS[1][1] + "|" + IO_PATTERN +
                  r"|President of .*(?:Universit|College|Institut)|[Uu]niversity president|[Pp]rovost|"
                  r"Chancellor of .*(?:Universit|College)|[Dd]ean of|[Pp]rofessor"
                  r"|[Cc]entral [Bb]ank|[Gg]overnor of the .*[Bb]ank|Federal Reserve|[Aa]mbassador|"
                  r"Permanent Representative|Under ?[Ss]ecretary|Assistant Secretary|Deputy Secretary|"
                  r"Administrator|Commissioner|Inspector General|Solicitor General|[Jj]udge|[Jj]ustice of|"
                  r"Director of|[Dd]irector-general|[Cc]hief [Ee]conomist|[Ee]nvoy|civil servant|"
                  r"National Security Advis[eo]r|Comptroller|Surgeon General|Librarian|Archivist"),
    ("Military", r"Chief of (?:the )?(?:General |Naval |Defence |Defense |Air |Army )?Staff|Joint Chiefs|"
                 r"Chief of Naval Operations|Commandant|[Cc]ommander|Supreme Allied|Chief of the Air|"
                 r"Chief of the Army|Chief of Defence|Chief of Defense"),
    ("Business", r"chief executive officer|\bCEO\b|chairman of the board|managing director|chief operating|"
                 r"chief financial|business"),
    ("Political", r"[Mm]ember of|[Ss]enator|[Rr]epresentative|President of|[Pp]rime [Mm]inister|"
                  r"Vice President|[Mm]inister|Secretary of|[Kk]ing|[Qq]ueen|[Ee]mir|[Ss]ultan|monarch|"
                  r"[Cc]rown [Pp]rince|[Gg]overnor of|[Mm]ayor|party leader|[Ll]eader of|[Dd]eputy|"
                  r"Knesset|Teachta|[Pp]arliament|[Cc]ongress|[Cc]hancellor|"
                  r"head of (?:state|government)|council member|[Ss]peaker"),
]
EMP_TO_CAREER = {"IO": "Technical", "Government": "Technical", "Academic": "Technical", "Business": "Business"}
UNDATED_YEARS = 4          # assumed length of an undated job
BUSINESS_FLOOR = 8         # a business occupation implies at least this many business years
MILITARY_FLOOR = 20        # a general/flag rank implies a full military career
SENIOR_RANK = r"general|admiral|marshal|colonel|brigadier|jiang|aluf|commander-in-chief|supreme|four-star"
SPOUSE_POS = r"First Lady|First Gentleman|[Cc]onsort|[Ss]pouse of"
SPOUSE_TITLE = r"First Lady|[Ss]pouse|[Ww]ife|Consort|Mrs\.|First Gentleman|[Dd]aughter|\b[Ss]on of|[Hh]usband"
CAREERS = ["Technical", "Business", "Political", "Military"]


def _years(start, end):
    """Calendar years covered by a dated spell (open spells run to 2025)."""
    s = pd.to_numeric(str(start)[:4], errors="coerce")
    e = pd.to_numeric(str(end)[:4], errors="coerce")
    if np.isnan(s):
        return None
    e = 2025 if np.isnan(e) else e
    return set(range(int(s), int(max(e, s)) + 1))


def spouse_by_title(df):
    """QIDs listed as a spouse or family member in most of their own gift entries."""
    out = set()
    for side, text in [("recip", df.recip_title.fillna("") + " " + df.recip.fillna("")),
                       ("giver", df.giver_title.fillna(""))]:
        flag = text.str.contains(SPOUSE_TITLE, regex=True)
        if side == "recip":   # "President and First Lady": the QID is the principal
            flag &= ~df.recip.fillna("").str.contains(r"President and|Vice President and|Secretary and", regex=True)
        share = flag.groupby(df[f"{side}_wiki"].where(df[f"{side}_has_qid"] == 1)).mean()
        out |= set(share[share >= 0.5].index)
    return out


def backgrounds(claims):
    """Primary background = the kind of work that fills most of a person's recorded career.

    Career years come from dated positions held (P39) and employers (P108), counted as
    sets of calendar years so overlapping jobs are not double counted; an undated job adds
    UNDATED_YEARS. People with no classifiable job fall back to the earlier occupation and
    education codes. The three overlapping indicators use the earlier Stata scores as is.
    """
    c = claims[claims["rank"] != "deprecated"]
    kinds = employer_kind()
    emp = c[c["property"] == "P108"].assign(kind=lambda x: x["value"].map(kinds))
    emp.loc[emp["valueLabel"].str.contains(IO_PATTERN, regex=True, na=False), "kind"] = "IO"
    emp["career"] = emp["kind"].map(EMP_TO_CAREER)
    pos = c[c["property"] == "P39"].copy()
    pos["career"] = None
    for label, pattern in reversed(POSITION_RULES):
        pos.loc[pos["valueLabel"].astype(str).str.contains(pattern, regex=True), "career"] = label
    spells = pd.concat([emp, pos]).dropna(subset=["career"])

    years = {}
    for (qid, career), g in spells.groupby(["item", "career"]):
        dated, undated = set(), 0
        for st, en in zip(g["start"], g["end"]):
            y = _years(st, en)
            if y is None:
                undated += 1
            else:
                dated |= y
        years[(qid, career)] = len(dated) + UNDATED_YEARS * undated

    # Spouses and children of U.S. presidents and vice presidents.
    principals = set(c.loc[(c["property"] == "P39") & c["valueLabel"].astype(str).str.contains(
        r"^(?:Vice )?President of the United States$", regex=True), "item"])
    us_family = (set(c.loc[c["property"].isin(["P22", "P25", "P26"]) & c["value"].isin(principals), "item"])
                 | set(c.loc[c["property"].isin(["P26", "P40"]) & c["item"].isin(principals), "value"]))
    rows = []
    for qid, g in c.groupby("item"):
        lab = lambda p: g.loc[g["property"] == p, "valueLabel"].astype(str)
        occ, edu, p39 = lab("P106"), lab("P69"), lab("P39")
        tech = max(_score(occ, TECH_JOB), _score(edu, TECH_EDU), _score(p39, TECH_POS))
        business = bool(occ.str.contains(BUSINESS_JOB, case=False, regex=True).any())
        political = bool(occ.str.contains(r"politician|statesperson|monarch|head of (?:state|government)",
                                          regex=True).any() or (g["property"] == "P102").any())
        military = bool((g["property"] == "P410").any() or occ.str.contains(
            r"military|soldier|army officer|naval officer|air force officer|general\b|admiral", case=False,
            regex=True).any())
        yrs = {k: years.get((qid, k), 0) for k in CAREERS}
        ranks = lab("P410")
        if len(ranks):
            floor = MILITARY_FLOOR if ranks.str.contains(SENIOR_RANK, case=False, regex=True).any() else UNDATED_YEARS
            yrs["Military"] = max(yrs["Military"], floor)
        if business:
            yrs["Business"] = max(yrs["Business"], BUSINESS_FLOOR)
        if max(yrs.values()) > 0:
            primary = max(CAREERS, key=lambda k: yrs[k])               # ties go to the earlier career type
        else:   # occupation fallback
            primary = ("Business" if business else "Technical" if tech >= 0.5 else "Military" if military
                       else "Political" if political else "Unknown")
        own_career = yrs["Political"] + yrs["Technical"] + yrs["Military"]
        if p39.str.contains(SPOUSE_POS, regex=True).any() or (qid in us_family and own_career == 0):
            primary = "Spouse/family"
        rows.append({"qid": qid, "tech_score": tech, "technical": tech >= 0.5, "business": business,
                     "political": political, "military": military, "background": primary,
                     **{f"yrs_{k.lower()}": v for k, v in yrs.items()}})
    return pd.DataFrame(rows).set_index("qid")


def office_types(df):
    """Office held at the time of the gift, for recipient and giver."""
    recip = np.select([df.branch.isin(["White House", "Legislative"]),
                       df.branch.eq("Diplomatic"),
                       df.branch.isin(["Defense", "Intelligence"])
                       | df.agency_std.fillna("").str.contains(SECURITY_AGENCIES, regex=True),
                       df.branch.isin(["Other executive", "Judicial"])],
                      ["Political", "Diplomatic", "Security", "Technical"], "Unknown")
    title = df.giver_title.fillna("") + " " + df.giver_org.fillna("")
    giver = pd.Series("Unknown", index=df.index)
    for label, pattern in reversed(GIVER_OFFICE_RULES):
        giver[title.str.contains(pattern, regex=True)] = label
    by_role = df.giver_role.map(ROLE_OFFICE)
    # Role keywords decide unless the title is specifically technical or business.
    giver = giver.where(giver != "Unknown", by_role.fillna("Unknown"))
    giver = giver.where(~(by_role.isin(["Political", "Security", "Diplomatic"]) & (giver == "Unknown")), by_role)
    giver[df.giver_role.eq("International org.")] = "Technical"
    return pd.Series(recip, index=df.index), giver


def item_kind(df):
    text = df["item"].fillna("").astype(str)
    kind = pd.Series("Other", index=df.index)
    for label, pattern in reversed(ITEM_RULES):
        kind[text.str.contains(pattern, case=False, regex=True)] = label
    kind[df.travel == 1] = "Travel/lodging"
    return kind


def ols_cluster(y, X, groups):
    """OLS with standard errors clustered on ``groups``."""
    X = np.asarray(X, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    bread = np.linalg.pinv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for idx in pd.Series(range(len(y))).groupby(np.asarray(groups)).indices.values():
        s = X[idx].T @ resid[idx]
        meat += np.outer(s, s)
    G, n, k = len(set(groups)), len(y), X.shape[1]
    V = bread @ meat @ bread * G / (G - 1) * (n - 1) / (n - k)
    return beta, np.sqrt(np.diag(V))


def background_analysis(df, claims):
    """Tables comparing technical, business, and political backgrounds and offices."""
    b = backgrounds(claims)
    b.loc[b.index.isin(spouse_by_title(df)), "background"] = "Spouse/family"
    df = df.copy()
    for side in ("recip", "giver"):
        has = df[f"{side}_has_qid"] == 1
        df[f"{side}_bg"] = np.where(has, df[f"{side}_wiki"].map(b["background"]).fillna("Unknown"), "Not linked")
    df["recip_office"], df["giver_office"] = office_types(df)
    df["kind"] = item_kind(df)
    out = {}

    # (1) Who has which background: people, by side.
    rows = []
    for side, label in [("recip", "Recipients"), ("giver", "Givers")]:
        ids = sorted(set(df.loc[df[f"{side}_has_qid"] == 1, f"{side}_wiki"]))
        bb = b.reindex(ids)
        bb["background"] = bb["background"].fillna("Unknown")
        row = {"": label, "People": len(ids),
               "Any technical": pct(bb.technical.fillna(False).mean()),
               "Any business": pct(bb.business.fillna(False).mean()),
               "Any political": pct(bb.political.fillna(False).mean())}
        for k in BACKGROUND_ORDER:
            row[k] = pct((bb.background == k).mean())
        rows.append(row)
    prof = pd.DataFrame(rows).set_index("").T.reset_index().rename(columns={"index": "Share of people"})
    prof.insert(0, "Group", ["", "Indicators (overlap)", "", ""] + ["Primary background"] + [""] * (len(BACKGROUND_ORDER) - 1))
    prof = prof.iloc[1:]  # People count goes in the header
    prof.columns = ["", "", f"Recipients (N={rows[0]['People']:,})", f"Givers (N={rows[1]['People']:,})"]
    write_table(prof, "tab_bg_profile", align="llrr")
    out["profile"] = rows

    # (2) Who gives to whom: background x background and office x office (row %, ratio to independence).
    def crosstab(r, c, order, name):
        m = pd.crosstab(df[r], df[c]).reindex(index=order, columns=order).fillna(0)
        m = m.loc[(m.sum(axis=1) > 0), (m.sum(axis=0) > 0)]
        m = m.drop(index="Unknown", columns="Unknown", errors="ignore")
        rowpct = m.div(m.sum(axis=1), axis=0)
        ratio = m / (np.outer(m.sum(axis=1), m.sum(axis=0)) / m.values.sum())
        tab = pd.DataFrame({"Giver $\\downarrow$ / Recipient $\\rightarrow$": m.index})
        for col in m.columns:
            tab[col] = [Raw(f"{100 * p:.0f} ({q:.1f})") for p, q in zip(rowpct[col], ratio[col])]
        tab["Gifts"] = m.sum(axis=1).astype(int).values
        write_table(tab, name, align="l" + "r" * (tab.shape[1] - 1))
        return m, rowpct, ratio
    out["bg_matrix"] = crosstab("giver_bg", "recip_bg", BACKGROUND_ORDER, "tab_bg_matrix")
    out["office_matrix"] = crosstab("giver_office", "recip_office", OFFICE_ORDER, "tab_office_matrix")

    # (3) Nature and value of gifts by giver and recipient background.
    kinds = ["Jewelry", "Watch", "Art/decorative", "Clothing/textile", "Weapon/ceremonial", "Book/media",
             "Food/drink", "Travel/lodging"]
    SHORT_KIND = {"Art/decorative": "Art, decor", "Clothing/textile": "Textile", "Weapon/ceremonial": "Weapon",
                  "Book/media": "Book", "Food/drink": "Food", "Travel/lodging": "Travel"}
    rows = []
    for side, label in [("giver", "Giver"), ("recip", "Recipient")]:
        for k in BACKGROUND_ORDER[:-1]:
            g = df[df[f"{side}_bg"] == k]
            if len(g) < 30:
                continue
            nt = g[g.travel == 0]
            row = {"Background": Raw(rf"{label}: {k}"), "Gifts": len(g),
                   "Median (\\$)": nt.estval_num.median(),
                   "$>$\\$5k": pct((nt.estval_num > 5000).mean())}
            for kk in kinds:
                row[SHORT_KIND.get(kk, kk)] = pct((g.kind == kk).mean())
            rows.append(row)
    nature = pd.DataFrame(rows)
    write_table(nature, "tab_bg_gifts", align="l" + "r" * (nature.shape[1] - 1))
    out["nature"] = nature

    # (4) Log value on backgrounds and offices, with branch and year fixed effects.
    d = df[(df.travel == 0) & (df.estval_num > 0) & (df.recip_has_qid == 1) & (df.giver_has_qid == 1)].copy()
    d = d[~d.giver_bg.eq("Unknown") & ~d.recip_bg.eq("Unknown")]
    y = np.log(d.estval_num.to_numpy())
    terms = []
    X = [np.ones(len(d))]
    for side, base in [("giver_bg", "Political"), ("recip_bg", "Political"), ("giver_office", "Political")]:
        for lev in [l for l in (BACKGROUND_ORDER if side.endswith("bg") else OFFICE_ORDER)
                    if l != base and (d[side] == l).sum() >= 30]:
            X.append((d[side] == lev).to_numpy(float))
            terms.append((side, lev))
    fe = pd.get_dummies(d.branch.astype(str), drop_first=True).astype(float).to_numpy()
    fy = pd.get_dummies(d.year.astype(str), drop_first=True).astype(float).to_numpy()
    X = np.column_stack(X + [fe, fy])
    beta, se = ols_cluster(y, X, d.giver_wiki.to_numpy())
    labels = {"giver_bg": "Giver background", "recip_bg": "Recipient background", "giver_office": "Giver office"}
    reg = pd.DataFrame([{"Term": Raw(f"{labels[s]}: {lev}"), "Coefficient": Raw(f"{beta[i + 1]:.2f}"),
                         "Std.\\ error": Raw(f"({se[i + 1]:.2f})"),
                         "Value ratio": Raw(f"{np.exp(beta[i + 1]):.2f}")}
                        for i, (s, lev) in enumerate(terms)])
    write_table(reg, "tab_bg_value", align="lrrr")
    out["reg"] = {"n": int(len(d)), "givers": int(d.giver_wiki.nunique()),
                  "terms": {f"{s}:{lev}": [float(beta[i + 1]), float(se[i + 1])] for i, (s, lev) in enumerate(terms)}}
    out["df"] = df
    return out


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_shared(results):
    """Observed similarity as a ratio to each random-pairing baseline, by panel."""
    ORANGE = "#eb6834"
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6), sharey=True)
    labels = [label.replace("$\\pm$", "±") for label, _ in MATCHES]
    y = np.arange(len(labels))[::-1]
    for ax, (title, res) in zip(axes, results.items()):
        ax.hlines(y, res["null_lo"], res["null_hi"], color=GRID, lw=7, zorder=1,
                  label="95% range of random pairings")
        ax.axvline(1, color=AXIS, lw=1, zorder=1)
        ax.scatter(res["ratio"], y, s=60, marker="o", color=BLUE, edgecolor="white",
                   linewidth=1.5, zorder=3, label="vs. random within branch-year")
        ax.scatter(res["ratio_year"], y, s=32, marker="D", color=ORANGE, edgecolor="white",
                   linewidth=1.2, zorder=4, label="vs. random within year")
        ax.set_xscale("log")
        ticks = [0.5, 0.75, 1, 1.5, 2, 3]
        ax.set_xticks(ticks, [f"{t:g}" for t in ticks])
        ax.minorticks_off()
        ax.set_xlim(0.4, 4)
        ax.grid(axis="y", visible=False)
        ax.set_title(title.split(" ", 1)[1], loc="left")
        ax.tick_params(axis="y", length=0)
    fig.supxlabel("Observed ÷ random-pairing rate (log scale)", fontsize=9, color=INK2, y=0.02)
    axes[0].set_yticks(y, labels)
    axes[0].tick_params(axis="y", labelcolor=INK2)
    h, l = axes[0].get_legend_handles_labels()
    order = [1, 2, 0]
    fig.legend([h[i] for i in order], [l[i] for i in order], loc="upper center", ncol=3,
               frameon=False, bbox_to_anchor=(0.55, 1.04), fontsize=8, labelcolor=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save(fig, "fig_shared")


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
    att = person_attributes(claims)
    profile = table_recip_profile(df, att)
    shared, school_pairs = table_shared(df, att)

    fig_by_year(df)
    fig_branch_multiples(df)
    fig_country_heatmap(df)
    role_branch = fig_role_branch(df)
    fig_shared(shared)
    bg = background_analysis(df, claims)
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
    numbers.update(giver_us_education(df, att))
    numbers["recip_profile"] = {r["Branch"]: {k: str(v) for k, v in r.items() if k != "Branch"}
                                for r in profile.to_dict("records")}
    numbers["shared"] = {panel: res.round(4).set_index("label").to_dict("index")
                         for panel, res in shared.items()}
    m, rowpct, ratio = bg["bg_matrix"]
    om, orow, oratio = bg["office_matrix"]
    bdf = bg["df"]
    numbers["backgrounds"] = {
        "profile": [{k: str(v) for k, v in r.items()} for r in bg["profile"]],
        "bg_rowpct": rowpct.round(3).to_dict("index"), "bg_ratio": ratio.round(2).to_dict("index"),
        "bg_gifts": m.sum(axis=1).astype(int).to_dict(),
        "office_rowpct": orow.round(3).to_dict("index"), "office_ratio": oratio.round(2).to_dict("index"),
        "office_gifts": om.sum(axis=1).astype(int).to_dict(),
        "nature": bg["nature"].astype(str).to_dict("records"),
        "value_reg": bg["reg"],
        "item_kinds": bdf["kind"].value_counts().to_dict(),
        "giver_office_counts": bdf["giver_office"].value_counts().to_dict(),
        "recip_office_counts": bdf["recip_office"].value_counts().to_dict(),
    }
    numbers["shared_school_pairs"] = [list(k) + [int(v)] for k, v in school_pairs.head(15).items()]
    (OUT_DIR / "paper_numbers.json").write_text(json.dumps(numbers, indent=2))
    print(json.dumps(numbers, indent=2))


if __name__ == "__main__":
    main()
