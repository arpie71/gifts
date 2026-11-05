"""Write analysis_revised/CODEBOOK.md: every column of every dataset, with definition and summary.

The script raises an error if a dataset has a column with no definition here, so the
codebook cannot silently fall behind the data.

Run from the repo root:
  /home/arpie/envs/revised/bin/python analysis_revised/05_codebook.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REV

PRIOR = "Computed from spells that started in year t-1 or earlier (lagged; never uses year t or later)."
HIST = "Computed from this person's gift records in years before t (strictly prior)."
NET = ("Network position in the bipartite graph of linked U.S. recipients x giving countries built from gift records in "
       "the window: c1 = year t only (contemporaneous, used as an outcome); l3 = t-3..t-1; l5 = t-5..t-1; "
       "cum = 1998..t-1 (lagged windows, used as predictors). 0 when the person has no ties in a lagged window.")

COMMON = {
    "qid": "Wikidata identifier of the person (human items only).",
    "t": "Receipt year (recd_year from the original analysis file: year of the receipt date, else the report year).",
    "agency": "Standardized reporting agency (agency_std from the original file; raw agency if no standard name).",
    "branch": "Branch of the reporting agency (original BRANCH_RULES).",
    "period": "Administration of the receipt year: Clinton 1998-2000, Bush I 2001-04, Bush II 2005-08, Obama I 2009-12, "
              "Obama II 2013-16, Trump 2017-20, Biden 2021-23.",
}

DEFS = {
    "interactions.csv": {
        "_about": "One row per reported gift (all 10,428 records of analysis/output/gifts_analysis.csv), with identities "
                  "used by the revised analysis.",
        "gift_id": "Gift identifier from the original file.", "year": "Report year.",
        "recip_qid": "Recipient QID if linked to a human Wikidata item; missing otherwise.",
        "recip_id": "Identity used in organization-level robustness: recip_qid; else 'org:'+QID for non-person items; "
                    "else 'name:'+normalized name (honorifics removed); missing for non-person names (e.g. 'An Agency Employee').",
        "recip_link": "Link status: QID; QID (organization/state/suspect link); NIL (searched, none found); FAMILY; GROUP; "
                      "UNCLEAR; missing.",
        "recip_entity": "person / organization / state / suspect link / unlinked, from the item's P31.",
        "recip_org_qid": "QID when the linked item is not a human (kept out of person panels).",
        "recip_wikiname": "Wikidata label of the linked item.",
        "giver_qid": "Giver QID if linked to a human item.", "giver_id": "As recip_id, for the giver.",
        "giver_link": "As recip_link, for the giver.", "giver_entity": "As recip_entity, for the giver.",
        "giver_org_qid": "QID of a non-person giver item (state, ministry, IO).", "giver_wikiname": "Wikidata label.",
        "giver_role": "Coarse giver type from the original file (ROLE_RULES).",
        "country": "Giving country (giver_country from the original file).", "giver_iso3": "ISO3 code of the giving country.",
        "estval_num": "Estimated value in nominal dollars (not used as an outcome).",
        "giver_elite": "Giver is a head of state/government or royalty (giver_role).",
        "recip_title_elite": "Recipient title in the record names a cabinet-level office or above (US_ELITE_TITLE_RX).",
        "in_panel_years": "Receipt year within 1998-2023 (47 earlier backlogged receipts are excluded from panels).",
    },
    "spells.csv": {
        "_about": "One row per career spell: a Wikidata position held (P39) or employer (P108) of a linked person.",
        "person": "Wikidata label of the person.", "source": "P39 (position held) or P108 (employer).",
        "item": "QID of the position or employer.", "label": "Its English label.",
        "org_id": "Organization of the spell: for P39, the position's P2389 (organization directed) else P361 (part of) "
                  "else the position item itself; for P108, the employer.",
        "org_label": "Label of org_id.", "country": "P17 of the position/employer, else P1001 when it is a country.",
        "sector": "Sector by ordered keyword rules (common.SECTOR_RULES) on the label, then the organization label, then "
                  "P31/P279 types; employers use their P31 type (EMP_RULES) when the name is not decisive. Generic labels "
                  "('member', 'chairperson', 'director') with no organization are Unclassified.",
        "domain": "Public / International / Academic / Private (revolving-door domain of the sector).",
        "generic_label": "Label too generic to classify without qualifiers the snapshot lacks.",
        "start_year": "Year of the P580 start qualifier (missing = undated spell).",
        "end_year": "Year of the P582 end qualifier as recorded.",
        "elite_office": "Position is cabinet-level or above in the U.S. (US_ELITE_RX).",
        "end_imputed": "Spell has a start but no recorded end.",
        "next_other_start": "Start of the person's next dated spell in a different organization.",
        "end_year_filled": "End year used in panels: recorded end; else next_other_start; else death year; else 2025.",
        "suspect_link": "Person flagged as an implausible link (see audit_implausible_links.csv); excluded from career measures.",
        "side": "recip or giver.",
    },
    "person_year_recip.csv": {
        "_about": "Linked U.S. recipient x year, 1998-2023, for every linked person (rows outside the risk set are kept and "
                  "flagged). Use risk_main == 1 for count models.",
        "first_year": "First receipt year observed.", "last_year": "Last receipt year observed.",
        "prior_gifts": "Gifts received before t. " + HIST, "prior_countries": "Distinct giving countries before t. " + HIST,
        "prior_partners": "Distinct giver identities before t. " + HIST,
        "prior_agencies": "Distinct reporting agencies before t. " + HIST,
        "prior_branches": "Distinct branches before t. " + HIST, "prior_active_years": "Years with a gift before t. " + HIST,
        "years_since_first": "t minus first_year (missing before the first gift).",
        "n_gifts": "Gifts received in t (outcome).", "n_partners": "Distinct giver identities in t (outcome).",
        "n_countries": "Distinct giving countries in t (outcome: diversity).",
        "n_new_countries": "Countries in t never seen by this person before (outcome: reach).",
        "n_repeat_partner_gifts": "Gifts in t from givers seen before (repeated interaction).",
        "n_agencies": "Distinct reporting agencies in t.", "value": "Total estimated value in t (not an outcome).",
        "career_start": "First start year among usable spells (dated and classified).",
        "career_len": "Total career length: t - career_start, floored at 0. Wikidata records senior posts better than early "
                      "jobs, so this understates careers of junior staff.",
        "career_before_record": "Gift observed before the first recorded Wikidata spell (career data incomplete).",
        "n_prior_spells": "Usable spells started by t-1. " + PRIOR,
        "n_prior_orgs": "Number of prior organizations. " + PRIOR,
        "n_prior_countries_pos": "Distinct countries of prior positions. " + PRIOR,
        "n_prior_sectors": "Distinct sectors of prior spells. " + PRIOR,
        "trans_sector": "Cross-sector transitions (main definition): changes in sector between consecutive prior spells. " + PRIOR,
        "trans_strict": "As trans_sector, counting only changes where the new spell starts after the previous one ended "
                        "(sequential moves; concurrent posts not counted). " + PRIOR,
        "trans_domain": "Revolving-door transitions: changes between Public, International, Academic, and Private domains. " + PRIOR,
        "trans_org": "Changes of organization between consecutive prior spells. " + PRIOR,
        "ever_private": "Any prior private-sector spell. " + PRIOR, "ever_academic": "Any prior academic/research spell. " + PRIOR,
        "ever_io": "Any prior international-organization spell. " + PRIOR, "ever_military": "Any prior military spell. " + PRIOR,
        "ever_legis": "Any prior legislative spell. " + PRIOR, "ever_diplo": "Any prior diplomatic spell. " + PRIOR,
        "cur_sector": "Sector of the current spell (most recent start among spells covering t; 'None' if none).",
        "cur_org": "Organization QID of the current spell.", "cur_org_label": "Its label.",
        "tenure_org": "Tenure in the current organization: t minus the start of the continuous run of spells in that "
                      "organization covering t (gaps of up to one year merged).",
        "tenure_position": "t minus the start of the current spell.",
        "in_us_public": "Holds a dated U.S. public position in t (legislature, national executive, diplomatic, military, "
                        "judiciary, or ceremonial spouse office; country U.S. or missing).",
        "elite_now": "Holds a cabinet-level or higher U.S. office in t.",
        "move_org": "Starts a spell in t in an organization not held in t-1, having had a prior spell (career transition).",
        "move_sector": "As move_org, into a sector not held in t-1.", "move_domain": "As move_org, into a new domain.",
        "move_into_elite": "The new spell in t is a cabinet-level office.",
        "exit_org": "A spell ends in t and the person holds no spell in that organization in t+1 (organizational exit).",
        "elite_person": "Ever held a cabinet-level office or above (Wikidata or gift title).",
        "top1pct": "Among the top 1% of recipients by total gifts (10 people).",
        "top25": "Among the 25 recipients with the most gifts.",
        "group": "Cabinet level and above (elite_person); Family of officials (spouse/child of a U.S. president or vice "
                 "president in Wikidata, or listed as family in at least half of own records); Legislators (ever a "
                 "legislative spell in Wikidata or a gift reported by Congress); else Agency, military, diplomatic staff.",
        "staff": "group is Agency, military, diplomatic staff.",
        "has_career_data": "Has at least one usable (dated, classified) spell and is not a suspect link.",
        "in_window": "first_year <= t <= last_year.",
        "risk_wd": "In the Wikidata risk set: in_us_public == 1.",
        "risk_main": "Main risk set: risk_wd == 1 or a gift in t. Zeros are meaningful only inside it.",
        "gift_outside_wd_tenure": "Gift in t although Wikidata shows no U.S. public spell in t (missing career data).",
        "branch_filled": "Branch in t, else most recent earlier branch.", "agency_filled": "Agency in t, else most recent earlier.",
    },
    "person_year_giver.csv": {
        "_about": "Linked foreign giver x year, 1998-2023; columns as in person_year_recip.csv (partners are U.S. recipients; "
                  "countries are the giver's own country). Descriptive use only.",
    },
    "person_recip.csv": {
        "_about": "One row per linked U.S. recipient: career at entry (first gift year) and totals.",
        "name": "Wikidata label.", "total_gifts": "Gifts 1998-2023.", "active_years": "Years with a gift.",
        "total_countries": "Distinct giving countries.", "total_agencies": "Distinct reporting agencies.",
        "entry_branch": "Branch in the first gift year.", "entry_gifts": "Gifts in the first year.",
        "entry_countries": "Countries in the first year.",
        "entry_career_len": "career_len in the first year.", "entry_prior_orgs": "n_prior_orgs in the first year.",
        "entry_trans_sector": "trans_sector in the first year.", "entry_trans_domain": "trans_domain in the first year.",
        "entry_ever_private": "ever_private in the first year.", "entry_ever_academic": "ever_academic in the first year.",
        "entry_ever_io": "ever_io in the first year.", "entry_ever_military": "ever_military in the first year.",
        "entry_ever_legis": "ever_legis in the first year.", "entry_elite_now": "elite_now in the first year.",
        "entry_c1_betweenness": "Betweenness in the first year's network.",
        "entry_c1_participation": "Participation coefficient in the first year's network.",
    },
    "org_year.csv": {
        "_about": "Reporting agency x year, from the agency's first to last year with gifts (gap years included as zeros).",
        "n_gifts": "Gifts reported.", "n_recip_linked": "Distinct linked recipients.",
        "n_recip_ident": "Distinct identifiable recipients (linked or by normalized name).",
        "n_countries": "Distinct giving countries.", "n_givers_linked": "Distinct linked foreign individuals.",
        "share_recip_linked": "Share of the agency's records with a linked recipient.",
        "exit_rate": "Personnel turnover: share of linked recipients at t-1 not observed at t (defined when both years have one).",
        "entry_rate": "Share of linked recipients at t not observed at t-1.",
        "exit_rate_ident": "exit_rate using all identifiable recipients.",
        "new_recips": "Linked recipients never before observed in the agency.",
        "top_recip": "Linked recipient with the most gifts at t.",
        "head_change": "top_recip differs from the previous year's (key-person change).",
        "country_retention": "Organizational network continuity: share of t-1 giving countries that give again at t.",
        "country_jaccard": "Jaccard similarity of giving-country sets at t-1 and t.",
        "giver_retention": "Share of t-1 linked foreign individuals who give again at t.",
        "log_gifts": "log(1 + n_gifts).",
    },
    "tie_year.csv": {
        "_about": "Agency x country tie observed at year t (=t0) through linked recipients (carriers).",
        "country": "Giving country.", "n_carriers": "Linked recipients who carried the tie at t0.",
        "all_departed": "All carriers never appear under the agency after t0.",
        "share_departed": "Share of carriers who never appear under the agency after t0.",
        "retained_any": "Country gives to the agency again in t0+1..t0+3.",
        "retained_by_others": "... through a recipient who was not a carrier at t0 (institutional memory).",
        "retained_by_carrier": "... through one of the t0 carriers.",
    },
    "movers.csv": {
        "_about": "Episodes in which a linked recipient is observed under agency A and later first appears under agency B.",
        "name": "Recipient.", "from_agency": "A.", "to_agency": "B.", "from_branch": "Branch of A.", "to_branch": "Branch of B.",
        "move_year": "First year under B.", "n_countries_A": "Countries that gave to the person at A before the move.",
        "gifts_B": "Gifts with a known country to the person at B.",
        "share_B_from_CA": "Share of the person's gifts at B from countries that gave to them at A.",
        "others_B_share_from_CA": "Same share among B's other recipients in the same years (baseline).",
        "share_B_from_GA": "Share of the person's gifts at B from foreign individuals who gave to them at A.",
        "others_B_share_from_GA": "Same share among B's other recipients.",
        "A_after_share_from_CA": "At A, share of other recipients' gifts in move_year..+2 from the mover's countries.",
        "A_before_others_share_from_CA": "At A, the same share in the 3 years before the move.",
        "cross_branch": "A and B are in different branches.",
    },
    "network_person_year.csv": {"_about": "Network position of linked recipients by year and window (merged into "
                                          "person_year_recip.csv). " + NET},
    "network_giver_period.csv": {
        "_about": "Foreign individuals in the bipartite graph of linked givers x U.S. reporting agencies, by administration "
                  "and for all years.",
        "degree": "Number of U.S. agencies reached.", "strength": "Gifts.", "betweenness": "Normalized betweenness.",
        "participation": "Participation coefficient across Louvain communities.", "n_communities": "Communities reached.",
        "bridging": "Reaches two or more communities.", "n_branches": "Distinct U.S. branches reached.",
    },
    "network_period.csv": {
        "_about": "Whole-network summaries by year (window = year; recipient-country graph) and by administration "
                  "(window = period).",
        "window": "year or period.", "years": "Years of the administration.", "gifts": "Gifts.",
        "nodes_left": "Linked recipients in the yearly graph.", "nodes_right": "Countries in the yearly graph.",
        "edges": "Recipient-country ties.", "modularity": "Louvain modularity of the yearly graph (seeded).",
        "n_communities": "Louvain communities.", "giant_share": "Share of nodes in the largest component.",
        "density": "Bipartite density.", "gifts_per_year": "Gifts per year in the administration.",
        "agencies": "Agencies.", "countries": "Countries.", "recipients_linked": "Linked recipients.",
        "agency_country_ties": "Distinct agency-country ties.",
        "ties_kept_from_prev": "Share of the previous period's (or year's) agency-country ties observed again.",
        "ties_new_share": "Share of this period's ties not seen in the previous period.",
        "recips_from_prev": "Share of linked recipients also seen in the previous period.",
        "agency_country_modularity": "Modularity of the agency-country graph.",
        "recip_country_modularity": "Modularity of the recipient-country graph.",
        "recip_country_giant_share": "Largest-component share, recipient-country graph.",
        "gini_country_gifts": "Gini of gifts across countries.", "gini_recip_gifts": "Gini of gifts across linked recipients.",
        "top10_recip_share": "Share of linked-recipient gifts going to the top 10 recipients.",
    },
}
NETCOLS = {f"net_{w}_{v}": f"{v} in window {w}. " + NET for w in ("c1", "l3", "l5", "cum")
           for v in ("degree", "betweenness", "participation", "n_communities", "bridging")}


def summarize(s):
    nn = s.notna().mean()
    if pd.api.types.is_bool_dtype(s) or (pd.api.types.is_numeric_dtype(s) and set(s.dropna().unique()) <= {0, 1}):
        return "binary", f"{100 * nn:.0f}%", f"mean {s.mean():.3f}" if s.notna().any() else ""
    if pd.api.types.is_numeric_dtype(s):
        return "numeric", f"{100 * nn:.0f}%", (f"mean {s.mean():.2f}; min {s.min():.4g}; max {s.max():.4g}"
                                               if s.notna().any() else "")
    return "text", f"{100 * nn:.0f}%", f"{s.nunique()} distinct"


def main():
    lines = ["# Codebook: revised analysis datasets", "",
             "Generated by `analysis_revised/05_codebook.py` from the files in `analysis_revised/data/`. "
             "Summary statistics are computed from the current build.", "",
             "Conventions: *prior* and *lagged* measures use only information dated before year t. Career information "
             "comes from Wikidata (snapshot `files/wikidata_claims.csv` plus `analysis_revised/cache/claims_supplement.csv`); "
             "it is missing for unlinked people and incomplete for junior staff, and missingness is not random "
             "(see `tab_audit_by_group`).", ""]
    missing = []
    for fname, defs in DEFS.items():
        df = pd.read_csv(DATA / fname, low_memory=False)
        lines += [f"## `{fname}`", "", defs.get("_about", ""), "", f"Rows: {len(df):,}. Columns: {df.shape[1]}.", "",
                  "| Variable | Type | Non-missing | Summary | Definition |", "|---|---|---|---|---|"]
        same_as = DEFS["person_year_recip.csv"] if fname in ("person_year_giver.csv", "person_recip.csv") else {}
        for c in df.columns:
            d = defs.get(c) or COMMON.get(c) or NETCOLS.get(c) or same_as.get(c)
            if d is None and fname.startswith("network_") and c in ("degree", "strength", "betweenness", "participation",
                                                                     "n_communities", "bridging"):
                d = DEFS["network_giver_period.csv"][c]
            if d is None:
                missing.append(f"{fname}:{c}")
                d = ""
            typ, nn, summ = summarize(df[c])
            lines.append(f"| `{c}` | {typ} | {nn} | {summ} | {d.replace('|', '/')} |")
        lines.append("")
    lines += ["## Audit files", "",
              "| File | Contents |", "|---|---|",
              "| `audit_link_status.csv` | Records by link status and side. |",
              "| `audit_link_by_group.csv` | Linkage rates by branch, administration, giver type. |",
              "| `audit_ambiguous_lookup.csv` | Name keys in masterwiki_new.csv mapped to more than one QID. |",
              "| `audit_name_variants.csv` | QIDs reached from more than one name form; `no_common_token` marks name changes or mislinks to review. |",
              "| `audit_same_name_diff_qid.csv` | One normalized name linked to different QIDs. |",
              "| `audit_duplicate_labels.csv` | Distinct QIDs with the same Wikidata label (possible duplicate identities). |",
              "| `audit_nonhuman_qids.csv` | Linked items that are not humans (states, ministries, IOs, Wikimedia categories). |",
              "| `audit_implausible_links.csv` | People whose Wikidata dates cannot match the gift record (died before, born before 1915, job before age 14). |",
              "| `audit_career_coverage.csv` | Share of linked people and records with usable career information. |", ""]
    (REV / "CODEBOOK.md").write_text("\n".join(lines))
    if missing:
        raise SystemExit(f"Undocumented columns: {missing}")
    print("wrote", REV / "CODEBOOK.md")


if __name__ == "__main__":
    main()
