"""Build the revised-analysis datasets.

Inputs (all read only):
  analysis/output/gifts_analysis.csv      original analysis file (one row per reported gift)
  files/wikidata_claims.csv               Wikidata statements for linked people
  files/employer_types.csv                P31 types of employers (cached by descriptives.py)
  files/masterwiki_new.csv                name -> QID lookup (for the linkage audit)
  analysis_revised/cache/position_meta.csv  organization / country / type of positions and employers

Outputs (analysis_revised/data/):
  interactions.csv          one row per gift record, with identities and flags used below
  spells.csv                one row per career spell (P39 position or P108 employer) with sector,
                            organization, country, and dates
  person_year_recip.csv     U.S. recipient x year panel (linked recipients), all lagged measures
  person_year_giver.csv     foreign giver x year panel (linked givers), gift and career measures
  person_recip.csv          one row per linked recipient (career at entry, totals)
  org_year.csv              reporting agency x year panel (turnover, continuity)
  tie_year.csv              agency x country x year ties with carrier departure status
  movers.csv                recipients observed under two reporting agencies (follow-the-person test)
  network_person_year.csv   network position of recipients by year and window
  network_giver_period.csv  brokerage of foreign givers between U.S. agencies, by period
  network_period.csv        whole-network summaries by year and by administration
  audit_*.csv               identifier-linkage audit

Run from the repo root:
  /home/arpie/envs/revised/bin/python analysis_revised/02_build_data.py
"""

import ast
import json
import re
import sys
from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import (BASE, DATA, GIFTS, CLAIMS, CLAIMS_SUPP, EMP_TYPES, POS_META, MASTERWIKI, SEED, FIRST_YEAR,
                    LAST_YEAR, OPEN_END, QID, PERIODS, period_of, classify_sector, year_of, GENERIC,
                    DOMAIN, US_ELITE_RX, US_ELITE_TITLE_RX, IO_RX)

# Employer-type rules from the original analysis, so both analyses type employers the same way.
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
EMP_SECTOR = {"IO": "Intl organization", "Academic": "Academic/research", "Business": "Private"}
US_PUBLIC = {"Legislature", "National executive", "Diplomatic", "Military", "Judiciary", "Monarchy/ceremonial"}
NON_PERSON_NAME = r"(?i)employee|agency|staff|delegation|unknown|personnel|members of|^$|officials|team|crew"
TRANS_DEFS = {"sector": "sector", "strict": "sector", "domain": "domain", "org": "org_id"}
WINDOWS = {"c1": (0, 0), "l3": (3, 1), "l5": (5, 1), "cum": (None, 1)}   # (back, lag): years t-back..t-lag


def norm_name(s):
    if not isinstance(s, str):
        return None
    s = re.sub(r"(?i)\b(the honorable|honorable|hon\.|mr\.|mrs\.|ms\.|dr\.|his|her|excellency|majesty|"
               r"royal highness|highness|general|admiral|ambassador|senator|sheikh|sheikha|h\.e\.|h\.r\.h\.)\b", " ", s)
    s = re.sub(r"[^a-z ]", " ", s.lower())
    return " ".join(s.split()) or None


# ---------------------------------------------------------------------------
# 1. Interactions
# ---------------------------------------------------------------------------
def load_interactions():
    g = pd.read_csv(GIFTS, low_memory=False)
    g["t"] = g["recd_year"].astype(int)
    g["in_panel_years"] = g["t"].between(FIRST_YEAR, LAST_YEAR)
    for side, name_col in [("recip", "recip_name"), ("giver", "giver_name")]:
        w = g[f"{side}_wiki"].astype(str).str.strip()
        g[f"{side}_link"] = np.select(
            [w.str.match(QID), w.str.upper().eq("NIL"), w.str.upper().eq("FAMILY"), w.str.upper().eq("GROUP"),
             w.str.upper().eq("UNCLEAR"), g[f"{side}_wiki"].isna()],
            ["QID", "NIL (searched, none)", "FAMILY", "GROUP", "UNCLEAR", "missing"], "other")
        g[f"{side}_qid"] = w.where(g[f"{side}_link"].eq("QID"))
        nm = g[name_col].where(g[name_col].notna(), g[side]).map(norm_name)
        nm = nm.where(~nm.fillna("").str.contains(NON_PERSON_NAME, regex=True))
        # Identity used for org-level robustness: QID if linked, else normalized name.
        g[f"{side}_id"] = g[f"{side}_qid"].where(g[f"{side}_qid"].notna(), "name:" + nm.fillna("")).where(
            g[f"{side}_qid"].notna() | nm.notna())
    g["period"] = g["t"].map(period_of)
    g["country"] = g["giver_country"]
    g["agency"] = g["agency_std"].fillna(g["agency"])
    # Prominence flags (record level).
    g["giver_elite"] = g["giver_role"].isin(["Head of state/govt", "Royalty"])
    g["recip_title_elite"] = (g["recip_title"].fillna("") + " | " + g["recip"].fillna("")).str.contains(
        US_ELITE_TITLE_RX, regex=True)
    return g


def mark_entity_types(g, claims):
    """Separate people from organizations, states, and Wikidata pages that are link errors.

    A linked QID is a person if its P31 includes human (Q5). Linked organizations
    (ministries, IOs, states) stay identifiable as partners ("org:" ids) but are
    removed from the person-level panels. Wikimedia categories and similar pages
    are flagged as suspect links.
    """
    p31 = claims[claims["property"] == "P31"].groupby("item")["valueLabel"].apply(lambda s: " | ".join(s.astype(str)))
    human = set(claims.loc[(claims["property"] == "P31") & (claims["value"] == "Q5"), "item"])
    for side in ("recip", "giver"):
        q = g[f"{side}_qid"]
        lab = q.map(p31).fillna("")
        typ = np.select([q.isna(), q.isin(human),
                         lab.str.contains(r"Wikimedia|flag design|family name|given name|disambiguation", regex=True),
                         lab.str.contains(r"sovereign state|country|state\b", regex=True)],
                        ["unlinked", "person", "suspect link", "state"], "organization")
        g[f"{side}_entity"] = typ
        g.loc[q.notna() & (typ != "person"), f"{side}_link"] = "QID (" + pd.Series(typ, index=g.index) + ")"
        g[f"{side}_org_qid"] = q.where(typ != "person")
        g[f"{side}_id"] = g[f"{side}_id"].where(typ == "person", ("org:" + q).where(q.notna(), g[f"{side}_id"]))
        g.loc[typ != "person", f"{side}_qid"] = np.nan
    return g


# ---------------------------------------------------------------------------
# 2. Linkage audit
# ---------------------------------------------------------------------------
def bare_offices():
    src = (BASE / "parseandclean_new.py").read_text()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", "") == "ROLES")
    return list(ast.literal_eval(node.value).keys())


def audit(g, claims, spells):
    out = {}
    rows = []
    for side in ("recip", "giver"):
        vc = g[f"{side}_link"].value_counts()
        for k, v in vc.items():
            rows.append({"side": side, "status": k, "records": v, "share": v / len(g)})
    pd.DataFrame(rows).to_csv(DATA / "audit_link_status.csv", index=False)

    # Linkage by branch, period, and giver role (is missingness random? no).
    by = []
    for col in ("branch", "period", "giver_role"):
        t = g.groupby(col).agg(records=("gift_id", "size"), recip_linked=("recip_link", lambda s: (s == "QID").mean()),
                               giver_linked=("giver_link", lambda s: (s == "QID").mean()))
        t = t.reset_index().rename(columns={col: "group"})
        t.insert(0, "dimension", col)
        by.append(t)
    pd.concat(by).to_csv(DATA / "audit_link_by_group.csv", index=False)

    # Ambiguous lookups: a name key mapped to more than one QID in the lookup table.
    mw = pd.read_csv(MASTERWIKI, encoding="utf-8-sig")
    amb = mw.dropna(subset=["wiki"]).drop_duplicates(["entity", "wiki"])
    amb = amb[amb["entity"].duplicated(keep=False)].sort_values("entity")
    amb.to_csv(DATA / "audit_ambiguous_lookup.csv", index=False)
    out["lookup_keys"] = int(mw["entity"].nunique())
    out["lookup_keys_conflicting"] = int(amb["entity"].nunique())
    out["lookup_exact_duplicate_rows"] = int(mw.duplicated(["entity", "wiki"]).sum())

    # Name variants per QID (name changes, transliterations) and possible mislinks.
    var = []
    for side, name_col in [("recip", "recip_name"), ("giver", "giver_name")]:
        d = g[g[f"{side}_qid"].notna()]
        for q, s in d.groupby(f"{side}_qid")[name_col]:
            names = sorted(set(s.dropna().map(norm_name).dropna()))
            if len(names) < 2:
                continue
            toks = [set(n.split()) for n in names]
            shared = set.intersection(*toks) if toks else set()
            var.append({"side": side, "qid": q, "wikiname": d.loc[d[f"{side}_qid"] == q, f"{side}_wikiname"].iloc[0],
                        "n_name_variants": len(names), "no_common_token": len(shared) == 0,
                        "variants": " ; ".join(names)[:400]})
    var = pd.DataFrame(var)
    var.to_csv(DATA / "audit_name_variants.csv", index=False)
    out["qids_with_name_variants"] = {s: int((var.side == s).sum()) for s in ("recip", "giver")}
    out["qids_variants_no_common_token"] = {s: int(((var.side == s) & var.no_common_token).sum())
                                            for s in ("recip", "giver")}

    # Same normalized name linked to different QIDs (homonyms or inconsistent links).
    hom = []
    for side, name_col in [("recip", "recip_name"), ("giver", "giver_name")]:
        d = g[g[f"{side}_qid"].notna()].assign(nm=lambda x: x[name_col].map(norm_name)).dropna(subset=["nm"])
        k = d.groupby("nm")[f"{side}_qid"].nunique()
        for nm in k[k > 1].index:
            q = d.loc[d.nm == nm, f"{side}_qid"].value_counts()
            hom.append({"side": side, "name": nm, "qids": " ; ".join(f"{a} ({b})" for a, b in q.items())})
    hom = pd.DataFrame(hom, columns=["side", "name", "qids"])
    hom.to_csv(DATA / "audit_same_name_diff_qid.csv", index=False)
    out["names_linked_to_multiple_qids"] = {s: int((hom.side == s).sum()) for s in ("recip", "giver")}

    # Possible duplicate identities: two QIDs with the same Wikidata label.
    dup = []
    for side in ("recip", "giver"):
        d = g[g[f"{side}_qid"].notna()].drop_duplicates(f"{side}_qid")
        lab = d[f"{side}_wikiname"].map(norm_name)
        k = d.groupby(lab)[f"{side}_qid"].nunique()
        for nm in k[k > 1].index:
            dup.append({"side": side, "label": nm, "qids": " ; ".join(d.loc[lab == nm, f"{side}_qid"])})
    dup = pd.DataFrame(dup, columns=["side", "label", "qids"])
    dup.to_csv(DATA / "audit_duplicate_labels.csv", index=False)
    out["qid_pairs_same_label"] = {s: int((dup.side == s).sum()) for s in ("recip", "giver")}

    # QIDs on both sides, QIDs that are not humans, QIDs without claims.
    rq, gq = set(g["recip_qid"].dropna()), set(g["giver_qid"].dropna())
    out["qids_on_both_sides"] = len(rq & gq)
    human = set(claims.loc[(claims["property"] == "P31") & (claims["value"] == "Q5"), "item"])
    has_claims = set(claims["item"])
    nonhuman = []
    for side in ("recip", "giver"):
        d = g[g[f"{side}_org_qid"].notna()]
        for (q, typ), n in d.groupby([f"{side}_org_qid", f"{side}_entity"]).size().items():
            p31 = claims.loc[(claims["item"] == q) & (claims["property"] == "P31"), "valueLabel"]
            nonhuman.append({"side": side, "qid": q, "label": d.loc[d[f"{side}_org_qid"] == q, f"{side}_wikiname"].iloc[0],
                             "entity_type": typ, "records": n, "p31": " ; ".join(p31.astype(str))})
    nh = pd.DataFrame(nonhuman, columns=["side", "qid", "label", "entity_type", "records", "p31"])
    nh.sort_values(["side", "records"], ascending=[True, False]).to_csv(DATA / "audit_nonhuman_qids.csv", index=False)
    out["nonhuman_qids"] = nh.groupby(["side", "entity_type"]).agg(qids=("qid", "size"), records=("records", "sum")) \
        .reset_index().to_dict("records")

    # Bare offices resolved to the holder by year (not a name match).
    offices = bare_offices()
    out["bare_office_records"] = int(g["recip"].isin(offices).sum())
    out["bare_offices"] = offices

    # Career information available.
    dated = spells[spells["start_year"].notna()]
    classified = dated[dated["sector"] != "Unclassified"]
    cov = []
    for side, qs in (("recip", rq), ("giver", gq)):
        recs = g[g[f"{side}_qid"].notna()]
        for lab, s in [("has any Wikidata claims", has_claims), ("has a P39 or P108 spell", set(spells["qid"])),
                       ("has a dated spell", set(dated["qid"])), ("has a dated, classified spell", set(classified["qid"]))]:
            cov.append({"side": side, "measure": lab, "people": len(qs & s), "people_share": len(qs & s) / len(qs),
                        "records_share_of_all": recs[f"{side}_qid"].isin(s).sum() / len(g),
                        "records_share_of_linked": recs[f"{side}_qid"].isin(s).mean()})
    pd.DataFrame(cov).to_csv(DATA / "audit_career_coverage.csv", index=False)
    out["career_coverage"] = cov
    return out


def implausible_links(g, claims, spells):
    """People whose Wikidata dates cannot belong to the person in the gift record.

    Flags: died before a gift they received or gave; born before 1915 and observed
    after 2000; or a first dated spell starting before age 14. These are likely
    links to a namesake. Their career measures are set to missing (the gift records
    are kept, since the reporting agency and country do not depend on the link).
    """
    # Only year-or-finer dates (precision >= 9); century placeholders read as "1901".
    prec = pd.to_numeric(claims["value_precision"], errors="coerce")
    exact = claims[prec >= 9]
    birth = exact[exact["property"] == "P569"].assign(y=lambda x: x["value"].map(year_of)).groupby("item")["y"].min()
    death = exact[exact["property"] == "P570"].assign(y=lambda x: x["value"].map(year_of)).groupby("item")["y"].min()
    # Royal titles held from birth are not an error.
    royals = set(spells.loc[spells["sector"] == "Monarchy/ceremonial", "qid"]) | set(
        g.loc[g["giver_role"].eq("Royalty"), "giver_qid"].dropna())
    first_spell = spells[~spells["qid"].isin(royals)].groupby("qid")["start_year"].min()
    rows = []
    for side in ("recip", "giver"):
        d = g[g[f"{side}_qid"].notna()].groupby(f"{side}_qid").agg(
            first=("t", "min"), last=("t", "max"), records=("t", "size"), name=(f"{side}_name", "first"),
            wikiname=(f"{side}_wikiname", "first"))
        for q, r in d.iterrows():
            b, dth, fs = birth.get(q, np.nan), death.get(q, np.nan), first_spell.get(q, np.nan)
            why = []
            if dth == dth and dth < r["first"] - 1:
                why.append(f"died {dth:.0f}, first gift {r['first']}")
            if b == b and b < 1915 and r["last"] >= 2000:
                why.append(f"born {b:.0f}, gift in {r['last']}")
            if b == b and fs == fs and fs < b + 14:
                why.append(f"first spell {fs:.0f} at age {fs - b:.0f}")
            if why:
                rows.append({"side": side, "qid": q, "gift_name": r["name"], "wikidata_label": r["wikiname"],
                             "records": r["records"], "first_gift": r["first"], "reason": "; ".join(why)})
    out = pd.DataFrame(rows, columns=["side", "qid", "gift_name", "wikidata_label", "records", "first_gift", "reason"])
    out.to_csv(DATA / "audit_implausible_links.csv", index=False)
    return out


# ---------------------------------------------------------------------------
# 3. Career spells
# ---------------------------------------------------------------------------
def build_spells(claims, people):
    c = claims[(claims["rank"] != "deprecated") & claims["property"].isin(["P39", "P108"])
               & claims["item"].isin(people)].copy()
    meta = pd.read_csv(POS_META)
    first = lambda p: meta[meta["property"] == p].drop_duplicates("qid").set_index("qid")
    org2389, org361, cty, jur = first("P2389"), first("P361"), first("P17"), first("P1001")
    types = (meta[meta["property"].isin(["P31", "P279"])].groupby("qid")["value_label"]
             .apply(lambda s: " | ".join(s.dropna().astype(str))))
    emp = pd.read_csv(EMP_TYPES).fillna("")
    emp_kind = {}
    for q, gq in emp.groupby("qid"):
        labs = " | ".join(gq["p31_label"])
        emp_kind[q] = next((k for k, pat in EMP_RULES if re.search(pat, labs, re.I)), "Other")
    countries = set(pd.read_csv(BASE / "files" / "country_iso3.csv")["qid"])

    rows = []
    for r in c.itertuples(index=False):
        q, lab = r.value, str(r.valueLabel) if isinstance(r.valueLabel, str) else ""
        if r.property == "P39":
            if q in org2389.index:
                org_id, org_label = q_lab(org2389, q)
            elif q in org361.index:
                org_id, org_label = q_lab(org361, q)
            else:
                org_id, org_label = q, lab
        else:
            org_id, org_label = q, lab
        country = cty.loc[q, "value_label"] if q in cty.index else (
            jur.loc[q, "value_label"] if q in jur.index and jur.loc[q, "value"] in countries else None)
        typ = types.get(q, "")
        generic = bool(re.match(GENERIC, lab, re.I))
        sector = "Unclassified"
        if r.property == "P108":
            k = emp_kind.get(q)
            sector = classify_sector(lab)            # the employer's own name decides first
            if sector in ("Unclassified", "National executive") and k in EMP_SECTOR:
                sector = EMP_SECTOR[k]               # then its Wikidata type (P31)
            if sector == "Unclassified" and k == "Government":
                sector = "National executive"
            if sector == "Unclassified":
                sector = classify_sector(typ)
        else:
            if not generic:
                sector = classify_sector(lab)
            if sector == "Unclassified" and org_id != q:
                sector = classify_sector(org_label)
            if sector == "Unclassified" and not generic:
                sector = classify_sector(typ)
        rows.append({"qid": r.item, "person": r.itemLabel, "source": r.property, "item": q, "label": lab,
                     "org_id": org_id, "org_label": org_label, "country": country, "sector": sector,
                     "domain": DOMAIN.get(sector), "generic_label": generic,
                     "start_year": year_of(r.start), "end_year": year_of(r.end),
                     "elite_office": bool(re.search(US_ELITE_RX, lab))})
    s = pd.DataFrame(rows)
    death = (claims[claims["property"] == "P570"].assign(y=lambda x: x["value"].map(year_of))
             .groupby("item")["y"].min())
    s["end_imputed"] = s["start_year"].notna() & s["end_year"].isna()
    # An open-ended spell (no P582) is closed at the start of the person's next dated spell in
    # a different organization, else at death, else it runs to the snapshot year. Wikidata
    # often omits end dates of earlier jobs; without this rule a 1979 law-firm partnership
    # would count as the 'current organization' decades later.
    s = s.sort_values(["qid", "start_year"]).reset_index(drop=True)
    nxt = []
    for q, h in s.groupby("qid", sort=False):
        st, org = h["start_year"].to_numpy(), h["org_id"].to_numpy()
        for i in range(len(h)):
            later = [st[j] for j in range(len(h)) if st[j] > st[i] and org[j] != org[i]] if not np.isnan(st[i]) else []
            nxt.append(min(later) if later else np.nan)
    s["next_other_start"] = nxt
    s["end_year_filled"] = s["end_year"].fillna(s["next_other_start"]).fillna(s["qid"].map(death)).fillna(OPEN_END)
    s.loc[s["start_year"].isna(), "end_year_filled"] = np.nan
    s["end_year_filled"] = np.maximum(s["end_year_filled"], s["start_year"])
    s = s.sort_values(["qid", "start_year", "end_year_filled"]).reset_index(drop=True)
    s.to_csv(DATA / "spells.csv", index=False)
    return s


def q_lab(frame, q):
    return frame.loc[q, "value"], frame.loc[q, "value_label"]


def count_transitions(seq, key, strict=False):
    """Number of changes in `key` between consecutive dated spells (Unclassified skipped)."""
    seq = [x for x in seq if x["sector"] != "Unclassified" and x[key] is not None and not
           (isinstance(x[key], float) and np.isnan(x[key]))]
    n, prev = 0, None
    for x in seq:
        if prev is not None and x[key] != prev[key]:
            if not strict or x["start_year"] >= prev["end_year_filled"]:
                n += 1
        prev = x
    return n


def run_start(spans, t):
    """Start of the continuous run of spells (gaps of at most one year merged) that covers t."""
    runs = []
    for a, b in spans:
        if runs and a <= runs[-1][1] + 1:
            runs[-1][1] = max(runs[-1][1], b)
        else:
            runs.append([a, b])
    return next(a for a, b in runs if a <= t <= b)


def career_panel(spells, people, years):
    """Career measures for each person and year, using only spells that began before the year."""
    out = []
    # Dated, classified spells only: a generic label with no organization ("partner", "member")
    # cannot define an organization, a tenure, or a sector change.
    usable = spells[spells["start_year"].notna() & (spells["sector"] != "Unclassified")]
    by = {q: g.to_dict("records") for q, g in usable.groupby("qid")}
    for q in people:
        sp = by.get(q, [])
        cstart = min((x["start_year"] for x in sp), default=np.nan)
        for t in years:
            prior = [x for x in sp if x["start_year"] <= t - 1]
            current = [x for x in sp if x["start_year"] <= t <= x["end_year_filled"]]
            started = [x for x in sp if x["start_year"] == t]
            cur_prev = [x for x in sp if x["start_year"] <= t - 1 <= x["end_year_filled"]]
            prev_orgs = {x["org_id"] for x in cur_prev}
            row = {"qid": q, "t": t, "career_start": cstart,
                   "career_len": max(t - cstart, 0) if not np.isnan(cstart) else np.nan,
                   "career_before_record": bool(not np.isnan(cstart) and cstart > t),
                   "n_prior_spells": len(prior),
                   "n_prior_orgs": len({x["org_id"] for x in prior}),
                   "n_prior_countries_pos": len({x["country"] for x in prior if isinstance(x["country"], str)}),
                   "n_prior_sectors": len({x["sector"] for x in prior if x["sector"] != "Unclassified"})}
            for name, key in TRANS_DEFS.items():
                row[f"trans_{name}"] = count_transitions(prior, key, strict=(name == "strict"))
            for sec, tag in [("Private", "private"), ("Academic/research", "academic"),
                             ("Intl organization", "io"), ("Military", "military"),
                             ("Legislature", "legis"), ("Diplomatic", "diplo")]:
                row[f"ever_{tag}"] = int(any(x["sector"] == sec for x in prior))
            if current:
                # Most recent appointment; ties go to the spell that runs longer.
                cur = max(current, key=lambda x: (x["start_year"], x["end_year_filled"]))
                org = cur["org_id"]
                start = run_start(sorted((x["start_year"], x["end_year_filled"]) for x in sp
                                         if x["org_id"] == org), t)
                row.update(cur_sector=cur["sector"], cur_org=org, cur_org_label=cur["org_label"],
                           tenure_org=t - start,
                           tenure_position=t - cur["start_year"],
                           in_us_public=int(any(x["sector"] in US_PUBLIC and (
                               not isinstance(x["country"], str) or x["country"] == "United States")
                               for x in current)),
                           elite_now=int(any(x["elite_office"] for x in current)))
            else:
                row.update(cur_sector=None, cur_org=None, cur_org_label=None, tenure_org=np.nan,
                           tenure_position=np.nan, in_us_public=0, elite_now=0)
            new_org = [x for x in started if x["org_id"] not in prev_orgs]
            prev_sectors = {x["sector"] for x in cur_prev} or ({prior[-1]["sector"]} if prior else set())
            prev_domains = {DOMAIN.get(s) for s in prev_sectors}
            row["move_org"] = int(bool(new_org) and bool(prior))
            row["move_sector"] = int(any(x["sector"] not in prev_sectors and x["sector"] != "Unclassified"
                                         for x in new_org) and bool(prior))
            row["move_domain"] = int(any(x["domain"] not in prev_domains and x["domain"] is not None
                                         for x in new_org) and bool(prior))
            row["move_into_elite"] = int(any(x["elite_office"] for x in new_org))
            ending = [x for x in sp if x["end_year"] == t and x["org_id"] not in
                      {y["org_id"] for y in sp if y["start_year"] <= t + 1 <= y["end_year_filled"]}]
            row["exit_org"] = int(bool(ending))
            out.append(row)
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# 4. Gift-derived person-year measures
# ---------------------------------------------------------------------------
def gift_panel(g, side, years):
    """Counts at t and cumulative history strictly before t, for linked people on one side."""
    other = "giver" if side == "recip" else "recip"
    d = g[g[f"{side}_qid"].notna() & g["in_panel_years"]].copy()
    d["partner"] = d[f"{other}_id"]
    rows = []
    for q, h in d.groupby(f"{side}_qid"):
        h = h.sort_values("t")
        seen_c, seen_p, seen_a, seen_b = set(), set(), set(), set()
        prior_gifts, active_years = 0, 0
        first, last = h["t"].min(), h["t"].max()
        byt = dict(list(h.groupby("t")))
        for t in years:
            cur = byt.get(t)
            r = {"qid": q, "t": t, "first_year": first, "last_year": last,
                 "prior_gifts": prior_gifts, "prior_countries": len(seen_c), "prior_partners": len(seen_p),
                 "prior_agencies": len(seen_a), "prior_branches": len(seen_b), "prior_active_years": active_years,
                 "years_since_first": t - first if t >= first else np.nan}
            if cur is None:
                r.update(n_gifts=0, n_partners=0, n_countries=0, n_new_countries=0, n_repeat_partner_gifts=0,
                         n_agencies=0, value=0.0, agency=None, branch=None)
            else:
                cs = set(cur["country"].dropna())
                ps = set(cur["partner"].dropna())
                r.update(n_gifts=len(cur), n_partners=len(ps), n_countries=len(cs),
                         n_new_countries=len(cs - seen_c),
                         n_repeat_partner_gifts=int(cur["partner"].isin(seen_p).sum()),
                         n_agencies=cur["agency"].nunique(), value=float(cur["estval_num"].fillna(0).sum()),
                         agency=cur["agency"].mode().iloc[0] if cur["agency"].notna().any() else None,
                         branch=cur["branch"].mode().iloc[0] if cur["branch"].notna().any() else None)
                seen_c |= cs; seen_p |= ps
                seen_a |= set(cur["agency"].dropna()); seen_b |= set(cur["branch"].dropna())
                prior_gifts += len(cur); active_years += 1
            rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Network measures
# ---------------------------------------------------------------------------
def louvain(G, seed):
    if G.number_of_edges() == 0:
        return {}
    comms = nx.community.louvain_communities(G, weight="weight", seed=seed)
    return {n: i for i, c in enumerate(comms) for n in c}


def bipartite_measures(edges, left, right, seed):
    """Degree, betweenness, participation coefficient and community span for `left` nodes."""
    G = nx.Graph()
    for (a, b), w in edges.items():
        G.add_edge(("L", a), ("R", b), weight=w)
    if G.number_of_nodes() == 0:
        return pd.DataFrame(), {}
    btw = nx.betweenness_centrality(G, normalized=True)
    comm = louvain(G, seed)
    mod = nx.community.modularity(G, [set(n for n in comm if comm[n] == i) for i in set(comm.values())],
                                  weight="weight") if comm else np.nan
    rows = []
    for n in G.nodes:
        if n[0] != "L":
            continue
        nb = list(G.neighbors(n))
        k = sum(G[n][m]["weight"] for m in nb)
        cs = defaultdict(float)
        for m in nb:
            cs[comm.get(m)] += G[n][m]["weight"]
        pc = 1 - sum((v / k) ** 2 for v in cs.values()) if k else 0.0
        rows.append({left: n[1], "degree": len(nb), "strength": k, "betweenness": btw[n],
                     "participation": pc, "n_communities": len(cs), "bridging": int(len(cs) >= 2)})
    comp = max(nx.connected_components(G), key=len)
    summary = {"nodes_left": sum(1 for n in G if n[0] == "L"), "nodes_right": sum(1 for n in G if n[0] == "R"),
               "edges": G.number_of_edges(), "modularity": mod, "n_communities": len(set(comm.values())),
               "giant_share": len(comp) / G.number_of_nodes(),
               "density": nx.bipartite.density(G, [n for n in G if n[0] == "L"])}
    return pd.DataFrame(rows), summary


def edge_counts(d, a, b):
    d = d.dropna(subset=[a, b])
    return d.groupby([a, b]).size().to_dict()


def gini(x):
    x = np.sort(np.asarray(x, float))
    if len(x) == 0 or x.sum() == 0:
        return np.nan
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum()))


def network_measures(g):
    d = g[g["in_panel_years"]]
    lr = d[d["recip_qid"].notna()]
    rows, summ = [], []
    for t in range(FIRST_YEAR, LAST_YEAR + 1):
        for wname, (back, lag) in WINDOWS.items():
            lo = FIRST_YEAR if back is None else t - back
            hi = t - lag
            if hi < lo or hi < FIRST_YEAR:
                continue
            w = lr[lr["t"].between(lo, hi)]
            m, s = bipartite_measures(edge_counts(w, "recip_qid", "country"), "qid", "country", SEED)
            if len(m):
                m["t"], m["window"] = t, wname
                rows.append(m)
            if wname == "c1":
                s.update(t=t, window="year")
                summ.append(s)
    net = pd.concat(rows, ignore_index=True)
    wide = net.pivot_table(index=["qid", "t"], columns="window",
                           values=["degree", "betweenness", "participation", "n_communities", "bridging"])
    wide.columns = [f"net_{w}_{v}" for v, w in wide.columns]
    wide = wide.reset_index()
    wide.to_csv(DATA / "network_person_year.csv", index=False)

    # Whole-network summaries: by year (above) and by administration, all records and linked only.
    prev = None
    for name, a, b in PERIODS:
        w = d[d["t"].between(a, b)]
        ac = edge_counts(w, "agency", "country")
        _, s_all = bipartite_measures(ac, "agency", "country", SEED)
        _, s_rc = bipartite_measures(edge_counts(w[w.recip_qid.notna()], "recip_qid", "country"), "qid", "country", SEED)
        ties = set(ac)
        recips = set(w["recip_qid"].dropna())
        row = {"t": a, "window": "period", "period": name, "years": f"{a}-{b}", "gifts": len(w),
               "gifts_per_year": len(w) / (b - a + 1), "agencies": w["agency"].nunique(),
               "countries": w["country"].nunique(), "recipients_linked": len(recips),
               "agency_country_ties": len(ties),
               "ties_kept_from_prev": len(ties & prev["ties"]) / len(prev["ties"]) if prev else np.nan,
               "ties_new_share": len(ties - prev["ties"]) / len(ties) if prev else np.nan,
               "recips_from_prev": len(recips & prev["recips"]) / len(recips) if prev and recips else np.nan,
               "agency_country_modularity": s_all.get("modularity"),
               "recip_country_modularity": s_rc.get("modularity"),
               "recip_country_giant_share": s_rc.get("giant_share"),
               "gini_country_gifts": gini(w["country"].value_counts()),
               "gini_recip_gifts": gini(w["recip_qid"].value_counts()),
               "top10_recip_share": w["recip_qid"].value_counts().head(10).sum() / max(w["recip_qid"].notna().sum(), 1)}
        prev = {"ties": ties, "recips": recips}
        summ.append(row)
    net_sum = pd.DataFrame(summ)
    # Year-level continuity of agency-country ties (t-1 -> t).
    yr = d.groupby("t")
    ties_by_year = {t: set(edge_counts(x, "agency", "country")) for t, x in yr}
    for i, r in net_sum.iterrows():
        if r["window"] == "year" and r["t"] - 1 in ties_by_year and r["t"] in ties_by_year:
            p, c = ties_by_year[r["t"] - 1], ties_by_year[r["t"]]
            net_sum.loc[i, "ties_kept_from_prev"] = len(p & c) / len(p) if p else np.nan
            net_sum.loc[i, "gifts"] = len(d[d.t == r["t"]])
    net_sum.to_csv(DATA / "network_period.csv", index=False)

    # Foreign givers as brokers between U.S. agencies (giver x agency graph, by period).
    lg = d[d["giver_qid"].notna()]
    gr = []
    for name, a, b in PERIODS + [("All years", FIRST_YEAR, LAST_YEAR)]:
        w = lg[lg["t"].between(a, b)]
        m, _ = bipartite_measures(edge_counts(w, "giver_qid", "agency"), "qid", "agency", SEED)
        if len(m):
            br = w.groupby("giver_qid")["branch"].nunique()
            m["n_branches"] = m["qid"].map(br)
            m["period"] = name
            gr.append(m)
    gr = pd.concat(gr, ignore_index=True)
    gr.to_csv(DATA / "network_giver_period.csv", index=False)
    return wide, net_sum, gr


# ---------------------------------------------------------------------------
# 6. Organization-year panel, tie-level data, movers
# ---------------------------------------------------------------------------
def org_year(g):
    d = g[g["in_panel_years"] & g["agency"].notna()]
    rows = []
    for a, h in d.groupby("agency"):
        byt = dict(list(h.groupby("t")))
        years = range(h["t"].min(), h["t"].max() + 1)
        seen_r, top_prev = set(), None
        for t in years:
            cur, prv = byt.get(t), byt.get(t - 1)
            R = set(cur["recip_qid"].dropna()) if cur is not None else set()
            Rp = set(prv["recip_qid"].dropna()) if prv is not None else set()
            RI = set(cur["recip_id"].dropna()) if cur is not None else set()
            RIp = set(prv["recip_id"].dropna()) if prv is not None else set()
            C = set(cur["country"].dropna()) if cur is not None else set()
            Cp = set(prv["country"].dropna()) if prv is not None else set()
            G_ = set(cur["giver_qid"].dropna()) if cur is not None else set()
            Gp = set(prv["giver_qid"].dropna()) if prv is not None else set()
            top = cur["recip_qid"].value_counts().idxmax() if cur is not None and cur["recip_qid"].notna().any() else None
            r = {"agency": a, "t": t, "branch": h["branch"].mode().iloc[0],
                 "n_gifts": 0 if cur is None else len(cur), "n_recip_linked": len(R), "n_recip_ident": len(RI),
                 "n_countries": len(C), "n_givers_linked": len(G_),
                 "share_recip_linked": np.nan if cur is None else cur["recip_qid"].notna().mean(),
                 "exit_rate": len(Rp - R) / len(Rp) if Rp and R else np.nan,
                 "entry_rate": len(R - Rp) / len(R) if R and Rp else np.nan,
                 "exit_rate_ident": len(RIp - RI) / len(RIp) if RIp and RI else np.nan,
                 "new_recips": len(R - seen_r),
                 "top_recip": top,
                 "head_change": (int(top != top_prev) if top is not None and top_prev is not None else np.nan),
                 "country_retention": len(C & Cp) / len(Cp) if Cp and C else np.nan,
                 "country_jaccard": len(C & Cp) / len(C | Cp) if Cp and C else np.nan,
                 "giver_retention": len(G_ & Gp) / len(Gp) if Gp and G_ else np.nan}
            seen_r |= R
            if top is not None:
                top_prev = top
            rows.append(r)
    o = pd.DataFrame(rows)
    o["log_gifts"] = np.log1p(o["n_gifts"])
    o.to_csv(DATA / "org_year.csv", index=False)
    return o


def tie_year(g):
    """Agency x country ties at t-1 and whether the U.S. people who carried them left the agency.

    'Departed' uses the whole record: a carrier has departed if they never again appear
    under that agency after t-1. The outcome of interest is whether *other* people in the
    agency keep the tie in t..t+2, so the carrier's own later gifts do not count.
    """
    d = g[g["in_panel_years"] & g["agency"].notna() & g["country"].notna() & g["recip_qid"].notna()]
    last_in_agency = d.groupby(["recip_qid", "agency"])["t"].max().to_dict()
    gifts_by = d.groupby(["agency", "country", "t"])["recip_qid"].apply(set).to_dict()
    agency_years = d.groupby("agency")["t"].agg(["min", "max"])
    rows = []
    for (a, c, t0), carriers in gifts_by.items():
        if t0 + 2 > agency_years.loc[a, "max"]:
            continue   # not enough later years to observe retention
        future = set().union(*(gifts_by.get((a, c, t), set()) for t in range(t0 + 1, t0 + 4)))
        departed = [last_in_agency[(q, a)] <= t0 for q in carriers]
        rows.append({"agency": a, "country": c, "t": t0, "n_carriers": len(carriers),
                     "all_departed": int(all(departed)), "share_departed": float(np.mean(departed)),
                     "retained_any": int(bool(future)), "retained_by_others": int(bool(future - carriers)),
                     "retained_by_carrier": int(bool(future & carriers))})
    tdf = pd.DataFrame(rows)
    tdf.to_csv(DATA / "tie_year.csv", index=False)
    return tdf


def movers(g):
    """People observed under agency A and later under agency B: do their foreign contacts follow them?"""
    d = g[g["in_panel_years"] & g["agency"].notna() & g["recip_qid"].notna()]
    rows = []
    for q, h in d.groupby("recip_qid"):
        span = h.groupby("agency")["t"].agg(["min", "max"]).sort_values("min")
        if len(span) < 2:
            continue
        for i in range(len(span) - 1):
            A, B = span.index[i], span.index[i + 1]
            if span.loc[B, "min"] <= span.loc[A, "min"]:
                continue
            s = span.loc[B, "min"]
            CA = set(h.loc[(h.agency == A) & (h.t < s), "country"].dropna())
            GA = set(h.loc[(h.agency == A) & (h.t < s), "giver_qid"].dropna())
            at_b = h[(h.agency == B) & (h.t >= s)]
            others_b = d[(d.agency == B) & (d.recip_qid != q) & d.t.isin(at_b.t.unique())]
            others_a = d[(d.agency == A) & (d.recip_qid != q) & d.t.between(s, s + 2)]
            pre_a_others = d[(d.agency == A) & (d.recip_qid != q) & d.t.between(s - 3, s - 1)]
            if not CA or at_b["country"].notna().sum() == 0:
                continue
            rows.append({"qid": q, "name": h["recip_wikiname"].iloc[0], "from_agency": A, "to_agency": B,
                         "from_branch": h.loc[h.agency == A, "branch"].iloc[0],
                         "to_branch": h.loc[h.agency == B, "branch"].iloc[0], "move_year": s,
                         "n_countries_A": len(CA), "gifts_B": int(at_b["country"].notna().sum()),
                         "share_B_from_CA": at_b["country"].isin(CA).mean(),
                         "others_B_share_from_CA": others_b["country"].isin(CA).mean() if len(others_b) else np.nan,
                         "share_B_from_GA": at_b["giver_qid"].isin(GA).mean() if GA else np.nan,
                         "others_B_share_from_GA": others_b["giver_qid"].isin(GA).mean() if GA and len(others_b) else np.nan,
                         "A_after_share_from_CA": others_a["country"].isin(CA).mean() if len(others_a) else np.nan,
                         "A_before_others_share_from_CA": pre_a_others["country"].isin(CA).mean() if len(pre_a_others) else np.nan,
                         "cross_branch": int(h.loc[h.agency == A, "branch"].iloc[0] != h.loc[h.agency == B, "branch"].iloc[0])})
    m = pd.DataFrame(rows)
    m.to_csv(DATA / "movers.csv", index=False)
    return m


# ---------------------------------------------------------------------------
def main():
    DATA.mkdir(parents=True, exist_ok=True)
    g = load_interactions()
    claims = pd.read_csv(CLAIMS, low_memory=False)
    if CLAIMS_SUPP.exists():
        claims = pd.concat([claims, pd.read_csv(CLAIMS_SUPP).drop(columns="retrieved")], ignore_index=True)
    claims = claims[claims["rank"] != "deprecated"]
    g = mark_entity_types(g, claims)
    rq = sorted(set(g["recip_qid"].dropna()))
    gq = sorted(set(g["giver_qid"].dropna()))
    spells = build_spells(claims, set(rq) | set(gq))
    spells["side"] = np.where(spells["qid"].isin(rq), "recip", "giver")
    bad = implausible_links(g, claims, spells)
    spells["suspect_link"] = spells["qid"].isin(set(bad["qid"]))
    spells.to_csv(DATA / "spells.csv", index=False)
    numbers = {"audit": audit(g, claims, spells)}
    numbers["audit"]["implausible_links"] = bad.groupby("side").agg(qids=("qid", "size"), records=("records", "sum")).to_dict("index")
    spells = spells[~spells["suspect_link"]]      # career measures only from plausible links

    years = list(range(FIRST_YEAR, LAST_YEAR + 1))
    print("career panels ...", flush=True)
    car_r = career_panel(spells, rq, years)
    car_g = career_panel(spells, gq, years)
    print("gift panels ...", flush=True)
    gp_r = gift_panel(g, "recip", years)
    gp_g = gift_panel(g, "giver", years)
    print("networks ...", flush=True)
    net, net_sum, giver_net = network_measures(g)

    # Person-level prominence flags (recipients).
    elite_wd = set(spells.loc[spells["elite_office"], "qid"])
    elite_title = set(g.loc[g["recip_title_elite"] & g["recip_qid"].notna(), "recip_qid"])
    totals = g[g.in_panel_years].groupby("recip_qid").size().sort_values(ascending=False)
    top1 = set(totals.head(max(1, int(round(len(totals) * 0.01)))).index)
    top25 = set(totals.head(25).index)
    dated_people = set(spells.loc[spells["start_year"].notna(), "qid"])

    py = gp_r.merge(car_r, on=["qid", "t"], how="left").merge(net, on=["qid", "t"], how="left")
    py["elite_person"] = py["qid"].isin(elite_wd | elite_title).astype(int)
    # Prominence group: cabinet level and above; legislators (ever a legislative spell or a gift
    # reported by Congress); everyone else = agency, military, and diplomatic staff.
    legis = set(spells.loc[spells["sector"] == "Legislature", "qid"]) | set(
        g.loc[g["branch"].eq("Legislative"), "recip_qid"].dropna())
    # Family of presidents and vice presidents (spouses, children) who hold no cabinet office themselves,
    # plus recipients listed as a spouse or family member in most of their own records.
    principals = set(claims.loc[(claims["property"] == "P39") & claims["valueLabel"].astype(str).str.match(
        r"^(?:Vice )?President of the United States$"), "item"])
    fam = (set(claims.loc[claims["property"].isin(["P22", "P25", "P26"]) & claims["value"].isin(principals), "item"])
           | set(claims.loc[claims["property"].isin(["P26", "P40"]) & claims["item"].isin(principals), "value"]))
    fam_title = (g["recip_title"].fillna("") + " " + g["recip"].fillna("")).str.contains(
        r"First Lady|Second Lady|[Ss]pouse|[Ww]ife of|[Dd]aughter|\b[Ss]on of|First Family", regex=True)
    share = fam_title.groupby(g["recip_qid"]).mean()
    fam_title_q = set(share[share >= 0.5].index)
    # Order: cabinet; family by Wikidata relation; legislators; family by title; staff.
    py["group"] = np.select([py["elite_person"] == 1, py["qid"].isin(fam), py["qid"].isin(legis),
                             py["qid"].isin(fam_title_q)],
                            ["Cabinet level and above", "Family of officials", "Legislators", "Family of officials"],
                            "Agency, military, diplomatic staff")
    py["staff"] = (py["group"] == "Agency, military, diplomatic staff").astype(int)
    py["top1pct"] = py["qid"].isin(top1).astype(int)
    py["top25"] = py["qid"].isin(top25).astype(int)
    py["has_career_data"] = py["qid"].isin(dated_people).astype(int)
    py["in_window"] = py["t"].between(py["first_year"], py["last_year"]).astype(int)
    py["risk_wd"] = py["in_us_public"].fillna(0).astype(int)
    py["risk_main"] = ((py["risk_wd"] == 1) | (py["n_gifts"] > 0)).astype(int)
    py["gift_outside_wd_tenure"] = ((py["n_gifts"] > 0) & (py["risk_wd"] == 0) & (py["has_career_data"] == 1)).astype(int)
    # Branch: of this year's gifts, else the most recent earlier gift year, else none.
    py = py.sort_values(["qid", "t"])
    py["branch_filled"] = py.groupby("qid")["branch"].ffill()
    py["agency_filled"] = py.groupby("qid")["agency"].ffill()
    py["period"] = py["t"].map(period_of)
    # Network measures absent for a window mean the person had no ties in it: 0, flagged.
    for c in [c for c in py.columns if c.startswith("net_") and not c.startswith("net_c1")]:
        py[c] = py[c].fillna(0)
    py.to_csv(DATA / "person_year_recip.csv", index=False)

    pyg = gp_g.merge(car_g, on=["qid", "t"], how="left")
    pyg.to_csv(DATA / "person_year_giver.csv", index=False)

    # One row per recipient: career at entry (selection) and totals.
    first = py[py["t"] == py["first_year"]].set_index("qid")
    person = pd.DataFrame({
        "first_year": first["first_year"], "last_year": first["last_year"],
        "total_gifts": py.groupby("qid")["n_gifts"].sum(),
        "active_years": py.groupby("qid")["n_gifts"].apply(lambda s: (s > 0).sum()),
        "total_countries": g[g.in_panel_years].groupby("recip_qid")["country"].nunique(),
        "total_agencies": g[g.in_panel_years].groupby("recip_qid")["agency"].nunique(),
        "entry_branch": first["branch"], "entry_gifts": first["n_gifts"], "entry_countries": first["n_countries"],
        "entry_career_len": first["career_len"], "entry_prior_orgs": first["n_prior_orgs"],
        "entry_trans_sector": first["trans_sector"], "entry_trans_domain": first["trans_domain"],
        "entry_ever_private": first["ever_private"], "entry_ever_academic": first["ever_academic"],
        "entry_ever_io": first["ever_io"], "entry_ever_military": first["ever_military"],
        "entry_ever_legis": first["ever_legis"], "entry_elite_now": first["elite_now"],
        "entry_c1_betweenness": first["net_c1_betweenness"], "entry_c1_participation": first["net_c1_participation"],
        "elite_person": first["elite_person"], "top25": first["top25"], "has_career_data": first["has_career_data"],
        "group": first["group"], "staff": first["staff"]})
    person.index.name = "qid"
    person["name"] = g.drop_duplicates("recip_qid").set_index("recip_qid")["recip_wikiname"]
    person.to_csv(DATA / "person_recip.csv")

    print("organization panels ...", flush=True)
    o = org_year(g)
    tdf = tie_year(g)
    mv = movers(g)
    keep = ["gift_id", "t", "year", "agency", "branch", "recip_qid", "recip_id", "recip_link", "recip_entity",
            "recip_org_qid", "recip_wikiname", "giver_qid", "giver_id", "giver_link", "giver_entity",
            "giver_org_qid", "giver_wikiname", "giver_role", "country", "giver_iso3",
            "estval_num", "period", "giver_elite", "recip_title_elite", "in_panel_years"]
    g[keep].to_csv(DATA / "interactions.csv", index=False)

    numbers["sizes"] = {"interactions": len(g), "interactions_in_panel_years": int(g.in_panel_years.sum()),
                        "spells": len(spells), "spells_dated": int(spells.start_year.notna().sum()),
                        "spells_unclassified": int((spells.sector == "Unclassified").sum()),
                        "person_year_recip_rows": len(py), "risk_main_rows": int(py.risk_main.sum()),
                        "risk_wd_rows": int(py.risk_wd.sum()), "recipients": len(rq), "givers": len(gq),
                        "org_year_rows": len(o), "tie_rows": len(tdf), "mover_episodes": len(mv),
                        "elite_recipients": len(elite_wd | elite_title), "top1pct_recipients": len(top1)}
    numbers["sector_counts"] = spells.groupby(["side", "sector"]).size().unstack(0).fillna(0).astype(int).to_dict()
    (DATA / "build_numbers.json").write_text(json.dumps(numbers, indent=2, default=str))
    print(json.dumps(numbers["sizes"], indent=2))


if __name__ == "__main__":
    main()
