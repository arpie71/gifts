"""Build the analysis file for the foreign gifts data.

Combines the yearly files in ``cleaned/`` and adds the variables the paper and
the Streamlit app need but the parser does not produce:

* ``agency`` / ``branch``  -- the reporting agency, recovered from the section
  headings of the Federal Register XML, and a coarse branch grouping.
* ``giver_country`` / ``giver_country_qid`` / ``giver_iso3`` -- the giving
  government, from the text of the giver field, falling back on the giver's
  Wikidata country of citizenship (P27).
* ``giver_role`` -- a coarse type for the giver (royalty, head of state, ...).
* ``estval_num`` / ``travel`` -- numeric value and a travel-gift flag.

Writes ``analysis/output/gifts_analysis.csv`` plus edge and panel files.

Run from the repo root: ``python analysis/build_analysis_data.py``
"""

import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
XML_DIR = BASE_DIR / "xml"
CLEANED_DIR = BASE_DIR / "cleaned"
FILES_DIR = BASE_DIR / "files"
OUT_DIR = BASE_DIR / "analysis" / "output"

CLAIMS_CSV = FILES_DIR / "wikidata_claims.csv"
ISO_CACHE = FILES_DIR / "country_iso3.csv"
LABEL_CACHE = FILES_DIR / "qid_labels.csv"

HEADERS = {"User-Agent": "Raymond Hicks research script (arpie71@gmail.com)"}


# ---------------------------------------------------------------------------
# Agency, from the XML section headings
# ---------------------------------------------------------------------------
# From 2001 on each agency's table carries a <TTITLE>; in 1999-2000 the agency
# is a one-cell row inside a single long table. download_data.py keeps rows
# with 2-4 cells, so walking the same rows in document order lines each kept
# row up with its index in raw/ and cleaned/.
TITLE_SKIP = re.compile(r"^\[|^Report of|^Amended Report", re.I)
TITLE_PREFIX = re.compile(r"^\s*(AGENCY|ENTITY)\s*[:—–-]?\s*", re.I)


def clean_title(text):
    text = " ".join(text.split())
    if TITLE_SKIP.search(text):
        return None
    text = TITLE_PREFIX.sub("", text)
    text = re.split(r"—Report of", text)[0]
    return re.sub(r"^The\s+", "", text).strip() or None


def agencies_for_year(path):
    """Agency for each kept row of one year's XML, in raw-file order."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"),
                         features="html.parser")
    agency, out = None, []
    for tag in soup.find_all(["ttitle", "row"]):
        if tag.name == "ttitle":
            agency = clean_title(tag.text) or agency
            continue
        cells = tag.find_all("ent")
        if len(cells) in (2, 3, 4):
            out.append(agency)
        elif len(cells) == 1 and cells[0].text.strip() not in ("", "None"):
            agency = clean_title(cells[0].text) or agency
    return out


# Order matters: the first matching rule wins.
BRANCH_RULES = [
    ("Legislative",  r"Senate|House of Representatives|General Accounting|Government Accountability|Library of Congress|Congress"),
    ("Judicial",     r"Courts|Supreme Court|Judicia"),
    ("White House",  r"White House|Executive Office of the President|Vice President|National Security Council|President of the U|Trade Representative|Science and Technology Policy"),
    ("Intelligence", r"Intelligence|National Security Agency"),
    ("Defense",      r"Defense|Army|Navy|Air Force|Marine|Central Command|Joint Chiefs|Coast Guard"),
    ("Diplomatic",   r"\bState\b|International Development|Peace Corps|Development Finance"),
]


# Spelling variants of the same agency -> one name (first match wins). The raw
# label stays in `agency`; this is for grouping, e.g. agency nodes in the dashboard.
AGENCY_STD = [
    (r"Vice President", "Office of the Vice President"),
    (r"Science and Technology Policy", "Office of Science and Technology Policy"),
    (r"Trade Representative", "Office of the U.S. Trade Representative"),
    (r"National Drug Control", "Office of National Drug Control Policy"),
    (r"White House|Executive Office of the President|President of the U|National Security Council",
     "White House / Executive Office of the President"),
    (r"Department of State|^State$", "Department of State"),
    (r"International Development$|Agency (for|of|For) International Development", "USAID"),
    (r"Development Finance", "U.S. International Development Finance Corporation"),
    (r"Central Intelligence", "Central Intelligence Agency"),
    (r"Director of National Intelligence", "Office of the Director of National Intelligence"),
    (r"Defense Intelligence", "Defense Intelligence Agency"),
    (r"^FBI$", "Federal Bureau of Investigation"),
    (r"Marine Corps", "U.S. Marine Corps"),
    (r"Navy|Naval Operations", "Department of the Navy"),
    (r"Air Force", "Department of the Air Force"),
    (r"Army", "Department of the Army"),
    (r"Central Command", "U.S. Central Command"),
    (r"European Command", "U.S. European Command"),
    (r"Defense Logistics", "Defense Logistics Agency"),
    (r"Defense", "Department of Defense"),
    (r"Senate", "U.S. Senate"),
    (r"House of Representatives|Standards of Official Conduct", "U.S. House of Representatives"),
    (r"Accounting Office|Accountability Office", "Government Accountability Office"),
    (r"Court", "Administrative Office of the U.S. Courts"),
    (r"Treasury", "Department of the Treasury"),
    (r"Commerce", "Department of Commerce"),
    (r"Justice", "Department of Justice"),
    (r"Homeland Security", "Department of Homeland Security"),
    (r"Transportation Systems|Department of Transportation", "Department of Transportation"),
    (r"Agriculture", "Department of Agriculture"),
    (r"Education", "Department of Education"),
    (r"Health and Human Services", "Department of Health and Human Services"),
    (r"Veterans", "Department of Veterans Affairs"),
    (r"Environmental Protection", "Environmental Protection Agency"),
    (r"NASA|Aeronautics", "NASA"),
    (r"Federal Reserve", "Federal Reserve Board"),
    (r"District of Columbia|^Office of the Mayor$", "Government of the District of Columbia"),
]


def standard_agency(agency):
    if not isinstance(agency, str):
        return None
    for pattern, name in AGENCY_STD:
        if re.search(pattern, agency, re.I):
            return name
    return re.sub(r"[.\s\d]+$", "", agency)


def branch_of(agency):
    if not isinstance(agency, str):
        return "Unknown"
    for branch, pattern in BRANCH_RULES:
        if re.search(pattern, agency, re.I):
            return branch
    return "Other executive"


# ---------------------------------------------------------------------------
# Giver country
# ---------------------------------------------------------------------------
# States that no longer exist; a P27 to one of these is dropped when the
# person also holds a current citizenship.
HISTORICAL = {
    "Soviet Union", "Russian Empire", "Yugoslavia", "Socialist Federal Republic of Yugoslavia",
    "Czechoslovakia", "East Germany", "West Germany", "Ottoman Empire", "Mandatory Palestine",
    "British Raj", "Kingdom of Iraq", "Kingdom of Egypt", "Kingdom of Italy",
    "Federal Republic of Yugoslavia", "Serbia and Montenegro", "Empire of Japan",
    "Weimar Republic", "Nazi Germany", "Republic of China (1912–1949)", "Kingdom of Afghanistan",
    "Ukrainian Soviet Socialist Republic", "Russian Soviet Federative Socialist Republic",
    "Kingdom of Libya", "Dominion of India", "Dominion of Pakistan", "French Algeria",
    "Emirate of Transjordan", "Kingdom of Hejaz", "Sultanate of Egypt",
}

# Spellings in the gift records -> the Wikidata label of the country.
ALIASES = {
    "Republic of Korea": "South Korea", "Korea": "South Korea", "Korean": "South Korea",
    "Democratic People's Republic of Korea": "North Korea", "Great Britain": "United Kingdom",
    "England": "United Kingdom", "British": "United Kingdom", "Scotland": "United Kingdom",
    "U.A.E": "United Arab Emirates", "UAE": "United Arab Emirates", "Emirati": "United Arab Emirates",
    "Abu Dhabi": "United Arab Emirates", "Dubai": "United Arab Emirates",
    "China": "People's Republic of China", "Chinese": "People's Republic of China",
    "Russian Federation": "Russia", "Russian": "Russia", "Moscow": "Russia",
    "Taiwan": "Republic of China", "Holy See": "Vatican City", "Vatican": "Vatican City", "Burma": "Myanmar",
    "Ivory Coast": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Türkiye": "Turkey", "Turkish": "Turkey", "Palestinian": "Palestine",
    "State of Palestine": "Palestine", "Czech": "Czech Republic", "Czechia": "Czech Republic",
    "Netherlands": "Kingdom of the Netherlands", "Dutch": "Kingdom of the Netherlands",
    "Denmark": "Kingdom of Denmark", "Danish": "Kingdom of Denmark",
    "Saudi": "Saudi Arabia", "Iraqi": "Iraq", "Israeli": "Israel", "Japanese": "Japan",
    "Afghan": "Afghanistan", "Kuwaiti": "Kuwait", "Qatari": "Qatar", "Jordanian": "Jordan",
    "Hashemite Kingdom": "Jordan", "Egyptian": "Egypt", "Indian": "India", "Pakistani": "Pakistan",
    "French": "France", "German": "Germany", "Italian": "Italy", "Mexican": "Mexico",
    "Canadian": "Canada", "Australian": "Australia", "Moroccan": "Morocco", "Bahraini": "Bahrain",
    "Omani": "Oman", "Polish": "Poland", "Ukrainian": "Ukraine", "Brazilian": "Brazil",
    "Colombian": "Colombia", "Vietnamese": "Vietnam", "Viet Nam": "Vietnam", "Thai": "Thailand",
    "Philippine": "Philippines", "Indonesian": "Indonesia", "Malaysian": "Malaysia",
    "Spanish": "Spain", "Norwegian": "Norway", "Swedish": "Sweden", "Greek": "Greece",
    "Lebanese": "Lebanon", "Yemeni": "Yemen", "Libyan": "Libya", "Tunisian": "Tunisia",
    "Algerian": "Algeria", "Kenyan": "Kenya", "Nigerian": "Nigeria", "Ethiopian": "Ethiopia",
    "Singaporean": "Singapore", "Kazakh": "Kazakhstan", "Azerbaijani": "Azerbaijan",
    "Taipei": "Republic of China",
}

# Givers are foreign by construction, so the US is never the giving government.
NOT_GIVER = {"United States", "United States of America"}

# Regime-specific and constitutional items folded into the continuing state,
# so a country keeps one ID (and an ISO code) across the whole panel.
CANONICAL = {
    "Islamic Republic of Afghanistan": ("Afghanistan", "Q889"),
    "Islamic State of Afghanistan": ("Afghanistan", "Q889"),
    "Transitional Islamic State of Afghanistan": ("Afghanistan", "Q889"),
    "Republic of Afghanistan": ("Afghanistan", "Q889"),
    "Democratic Republic of Afghanistan": ("Afghanistan", "Q889"),
    "Great Socialist People's Libyan Arab Jamahiriya": ("Libya", "Q1016"),
    "Libyan Arab Republic": ("Libya", "Q1016"),
    "Republic of Egypt": ("Egypt", "Q79"),
    "Kingdom of Denmark": ("Denmark", "Q35"),
    "Kingdom of the Netherlands": ("Netherlands", "Q29999"),  # ISO code sits on the kingdom
    "Palestine": ("State of Palestine", "Q219060"),
    "Occupied Palestinian territory": ("State of Palestine", "Q219060"),
    "Republic of China": ("Taiwan", "Q865"),
    "People's Republic of China": ("China", "Q148"),
}


def load_claims():
    claims = pd.read_csv(CLAIMS_CSV, low_memory=False)
    claims = claims[claims["rank"] != "deprecated"]
    return claims


def country_lookup(claims):
    """Country label -> QID, from every P27 value in the claims file."""
    p27 = claims[claims["property"] == "P27"]
    labels = p27[["value", "valueLabel"]].drop_duplicates()
    labels = labels[~labels["valueLabel"].isin(HISTORICAL | NOT_GIVER)]
    return dict(zip(labels["valueLabel"], labels["value"]))


def p27_country(claims, label_to_qid):
    """Person QID -> single current country QID, where one can be chosen."""
    p27 = claims[claims["property"] == "P27"]
    current = p27[p27["valueLabel"].isin(label_to_qid)]
    picked = current.groupby("item")["value"].agg(lambda s: s.iloc[0] if s.nunique() == 1 else None)
    return picked.dropna().to_dict()


def text_matcher(label_to_qid):
    names = {name: name for name in label_to_qid}
    names.update({alias: target for alias, target in ALIASES.items() if target in label_to_qid})
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b")

    def match(text):
        if not isinstance(text, str):
            return None
        # "Democratic People's Republic of Korea" must not fall through to "Korea".
        hit = pattern.search(text)
        return names[hit.group(1)] if hit else None
    return match


def fetch_iso3(qids):
    """ISO 3166-1 alpha-3 (P298) for country QIDs, cached in files/."""
    cache = pd.read_csv(ISO_CACHE) if ISO_CACHE.exists() else pd.DataFrame(columns=["qid", "iso3"])
    cache = cache[cache["iso3"].fillna("") != ""]
    todo = sorted(set(qids) - set(cache["qid"]))
    rows = []
    for i in range(0, len(todo), 50):
        r = requests.get("https://www.wikidata.org/w/api.php", headers=HEADERS, timeout=60, params={
            "action": "wbgetentities", "ids": "|".join(todo[i:i + 50]),
            "props": "claims", "format": "json"})
        for qid, ent in r.json().get("entities", {}).items():
            iso = ""
            for st in ent.get("claims", {}).get("P298", []):
                if st.get("rank") != "deprecated" and st["mainsnak"].get("datavalue"):
                    iso = st["mainsnak"]["datavalue"]["value"]
                    break
            rows.append({"qid": qid, "iso3": iso})
        time.sleep(1)
    if rows:
        cache = pd.concat([cache, pd.DataFrame(rows)]).drop_duplicates("qid")
        cache.to_csv(ISO_CACHE, index=False)
    return dict(zip(cache["qid"], cache["iso3"].fillna("")))


def fill_labels(df, claims):
    """Fill blank Wikidata names (e.g. role-resolved Presidents) from claims or the API."""
    labels = claims.dropna(subset=["itemLabel"]).drop_duplicates("item").set_index("item")["itemLabel"].to_dict()
    if LABEL_CACHE.exists():
        labels.update(pd.read_csv(LABEL_CACHE).set_index("qid")["label"].to_dict())
    need = set()
    for side in ("recip", "giver"):
        blank = is_qid(df[f"{side}_wiki"]) & df[f"{side}_wikiname"].isna()
        need |= set(df.loc[blank, f"{side}_wiki"]) - set(labels)
    rows = []
    for batch in [sorted(need)[i:i + 50] for i in range(0, len(need), 50)]:
        r = requests.get("https://www.wikidata.org/w/api.php", headers=HEADERS, timeout=60, params={
            "action": "wbgetentities", "ids": "|".join(batch), "props": "labels",
            "languages": "en|mul", "format": "json"})
        for qid, ent in r.json().get("entities", {}).items():
            # Wikidata keeps many personal names only in the "mul" (all-language) slot.
            names = ent.get("labels", {})
            label = names.get("en", names.get("mul", {})).get("value")
            if label:
                rows.append({"qid": qid, "label": label})
        time.sleep(1)
    if rows:
        new = pd.DataFrame(rows)
        if LABEL_CACHE.exists():
            new = pd.concat([pd.read_csv(LABEL_CACHE), new]).drop_duplicates("qid")
        new.to_csv(LABEL_CACHE, index=False)
        labels.update(dict(zip(new["qid"], new["label"])))
    for side in ("recip", "giver"):
        df[f"{side}_wikiname"] = df[f"{side}_wikiname"].fillna(df[f"{side}_wiki"].map(labels))
    return df


# ---------------------------------------------------------------------------
# Giver role and gift attributes
# ---------------------------------------------------------------------------
# 5 U.S.C. 7342 counts international organizations as foreign governments; they
# get their own role and no country.
INTL_ORG = re.compile(
    r"World Health Organization|Pan American Health|United Nations|\bUNESCO\b|\bUNICEF\b|\bNATO\b|"
    r"North Atlantic Treaty|European Union|European Commission|European Parliament|"
    r"International Monetary Fund|World Bank|African Union|Organization of American States|"
    r"Caribbean Environment Programme|International Atomic Energy|World Trade Organization|"
    r"Inter-American Development Bank|Asian Development Bank|Gulf Cooperation Council|Arab League|"
    r"League of Arab States|International Committee of the Red Cross|\bOECD\b|Commonwealth Secretariat")

ROLE_RULES = [
    ("Royalty",              r"\b(King|Queen|Emir|Amir|Sultan|Prince|Princess|Majesty|Highness|Sheikh|Shaikh)\b"),
    ("Minister",             r"\b(Deputy|Vice) (Prime Minister|President)\b|\bMinister\b|Foreign Secretary"),
    ("Head of state/govt",   r"\b(President|Prime Minister|Chancellor|Premier|Governor[- ]General|Head of State)\b"),
    ("Legislator",           r"\b(Parliament|Speaker|Senator|M\.P\.|Assembly|Duma|Knesset|Congress|Legislat)"),
    ("Diplomat",             r"\b(Ambassador|Embassy|Charg[eé]|Consul)"),
    ("Intelligence/security", r"Intelligence|Security Service|Mukhabarat|\bPolice\b|Directorate"),
    ("Military",             r"\b(General|Admiral|Chief of|Commander|Colonel|Brigadier|Marshal|Army|Navy|Air Force|Armed Forces|Military|Defen[cs]e Force)"),
]

TRAVEL = re.compile(
    r"^(Travel|Gift of Travel|Transport?at?ion|Lodging and meals|Ground transportation|Air travel|"
    r"Food, lodging|Round trip|Bus transportation|Air transportation|lodging|hotel|meals|accomm?odation|"
    r"expended for|airfare|\d+ nights?|helicopter|in-kind lodging)", re.I)

AMOUNT = re.compile(r"\$?\s?(\d[\d,]*(?:\.\d+)?)")


def giver_role(text):
    if not isinstance(text, str):
        return "Other/unknown"
    if INTL_ORG.search(text):
        return "International org."
    for role, pattern in ROLE_RULES:
        if re.search(pattern, text):
            return role
    return "Other/unknown"


def amount(text):
    if not isinstance(text, str):
        return np.nan
    m = AMOUNT.search(text)
    return float(m.group(1).replace(",", "")) if m else np.nan


def is_qid(series):
    return series.fillna("").str.match(r"^Q\d+$")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def load_gifts():
    frames = []
    for path in sorted(CLEANED_DIR.glob("gifts*.csv")):
        df = pd.read_csv(path, low_memory=False)
        agencies = agencies_for_year(XML_DIR / f"{path.stem}.xml")
        if len(agencies) != len(df):
            raise ValueError(f"{path.name}: {len(df)} rows but {len(agencies)} XML rows")
        df["agency"] = [agencies[i] for i in df["Unnamed: 0"]]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True).rename(columns={"Unnamed: 0": "row"})
    df.insert(0, "gift_id", df["year"].astype(str) + "-" + df["row"].astype(str).str.zfill(4))
    return df


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_gifts()
    df["branch"] = df["agency"].map(branch_of)
    df["agency_std"] = df["agency"].map(standard_agency)

    claims = load_claims()
    df = fill_labels(df, claims)
    label_to_qid = country_lookup(claims)
    qid_to_label = {q: l for l, q in label_to_qid.items()}
    from_text = df["giver"].map(text_matcher(label_to_qid))
    from_p27 = df["giver_wiki"].map(p27_country(claims, label_to_qid)).map(qid_to_label)
    intl = df["giver"].fillna("").str.contains(INTL_ORG)
    from_text, from_p27 = from_text.mask(intl), from_p27.mask(intl)
    df["giver_country"] = from_text.fillna(from_p27)
    canon = df["giver_country"].map(CANONICAL)
    df["giver_country_qid"] = df["giver_country"].map(label_to_qid)
    has_canon = canon.notna()
    df.loc[has_canon, "giver_country"] = canon[has_canon].str[0]
    df.loc[has_canon, "giver_country_qid"] = canon[has_canon].str[1]
    df["giver_country_source"] = np.select(
        [from_text.notna(), from_p27.notna()], ["text", "wikidata_p27"], default="")
    iso = fetch_iso3(df["giver_country_qid"].dropna().unique())
    df["giver_iso3"] = df["giver_country_qid"].map(iso)

    both = from_text.notna() & from_p27.notna()
    canon_label = lambda s: s.map(lambda x: CANONICAL.get(x, (x,))[0])
    agree = (canon_label(from_text[both]) == canon_label(from_p27[both])).mean()

    df["giver_role"] = df["giver"].map(giver_role)
    df["estval_num"] = df["estval"].map(amount)
    # The report year is when the gift was filed; backlogged filings (e.g. the 2015
    # Senate report) list gifts received years earlier, so keep the receipt year too.
    recd_year = pd.to_datetime(df["recd_std"], errors="coerce").dt.year
    recd_year = recd_year.fillna(pd.to_numeric(df["recd"].str.extract(r"((?:19|20)\d\d)")[0], errors="coerce"))
    df["recd_year"] = recd_year.where(recd_year.between(1990, df["year"].max() + 1)).fillna(df["year"]).astype(int)
    df["recd_year_source"] = np.where(recd_year.between(1990, df["year"].max() + 1), "receipt date", "report year")
    df["travel"] = df["item_orig"].fillna("").str.match(TRAVEL).astype(int)
    df["recip_has_qid"] = is_qid(df["recip_wiki"]).astype(int)
    df["giver_has_qid"] = is_qid(df["giver_wiki"]).astype(int)

    df.to_csv(OUT_DIR / "gifts_analysis.csv", index=False)

    # Edge list for the network view: one row per giver-recipient pair.
    pairs = df[is_qid(df["giver_wiki"]) & is_qid(df["recip_wiki"])]
    edges = (pairs.groupby(["giver_wiki", "recip_wiki"])
             .agg(giver=("giver_wikiname", "first"), recip=("recip_wikiname", "first"),
                  giver_country=("giver_country", "first"), recip_branch=("branch", "first"),
                  n_gifts=("gift_id", "size"), total_value=("estval_num", "sum"),
                  first_year=("year", "min"), last_year=("year", "max"))
             .reset_index())
    edges.to_csv(OUT_DIR / "edges_person.csv", index=False)

    # Balanced country-year panel for the map and for merges with country data.
    countries = df.dropna(subset=["giver_country"])
    panel = (countries.groupby(["giver_country", "giver_iso3", "year"])
             .agg(n_gifts=("gift_id", "size"), total_value=("estval_num", "sum"),
                  n_recipients=("recip_wiki", "nunique"))
             .reset_index())
    full = pd.MultiIndex.from_product(
        [panel[["giver_country", "giver_iso3"]].drop_duplicates().itertuples(index=False, name=None),
         sorted(df["year"].unique())], names=["country", "year"]).to_frame(index=False)
    full[["giver_country", "giver_iso3"]] = pd.DataFrame(full.pop("country").tolist(), index=full.index)
    panel = full.merge(panel, on=["giver_country", "giver_iso3", "year"], how="left")
    panel[["n_gifts", "total_value", "n_recipients"]] = panel[["n_gifts", "total_value", "n_recipients"]].fillna(0)
    panel["any_gift"] = (panel["n_gifts"] > 0).astype(int)
    panel.to_csv(OUT_DIR / "country_year_panel.csv", index=False)

    summary = {
        "n_gifts": int(len(df)),
        "years": [int(df["year"].min()), int(df["year"].max())],
        "n_agencies": int(df["agency"].nunique()),
        "agency_missing": int(df["agency"].isna().sum()),
        "n_agencies_std": int(df["agency_std"].nunique()),
        "recip_qid_share": float(df["recip_has_qid"].mean()),
        "giver_qid_share": float(df["giver_has_qid"].mean()),
        "recip_unique_qids": int(df.loc[df["recip_has_qid"] == 1, "recip_wiki"].nunique()),
        "giver_unique_qids": int(df.loc[df["giver_has_qid"] == 1, "giver_wiki"].nunique()),
        "giver_country_share": float(df["giver_country"].notna().mean()),
        "giver_country_by_source": df["giver_country_source"].value_counts().to_dict(),
        "text_p27_agreement": float(agree),
        "n_countries": int(df["giver_country"].nunique()),
        "intl_org_gifts": int(intl.sum()),
        "estval_share": float(df["estval_num"].notna().mean()),
        "travel_share": float(df["travel"].mean()),
        "recd_year_from_date_share": float((df["recd_year_source"] == "receipt date").mean()),
        "recd_lag_gt1_share": float(((df["year"] - df["recd_year"]) > 1).mean()),
        "n_edges": int(len(edges)),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
