"""Parse and clean the raw Federal Register gift records.

Reads every CSV in ``raw/``, splits the free-text ``item`` and ``recip``/``giver``
fields into structured columns, attaches Wikidata identifiers from the lookup
files in ``files/``, and writes the result to ``cleaned/`` under the same name.

Run from anywhere: ``python parseandclean_new.py``
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
CLEANED_DIR = BASE_DIR / "cleaned"
FILES_DIR = BASE_DIR / "files"

WIKI_CSV = FILES_DIR / "masterwiki_new.csv"
GROUPS_CSV = FILES_DIR / "groups.csv"
NOWIKI_TXT = FILES_DIR / "nowiki2.txt"

# Columns carried over from the masterwiki lookup on every merge.
WIKI_COLS = ["wiki", "wikiname", "descr"]


# ---------------------------------------------------------------------------
# Office holders — recipients recorded only as "President" etc. are resolved
# to a person via the gift year.
# ---------------------------------------------------------------------------
ROLES = {
    "President": {
        "Clinton": {"startyear": 1993, "endyear": 2000, "WikidataID": "Q1124"},
        "Bush":    {"startyear": 2001, "endyear": 2008, "WikidataID": "Q207"},
        "Obama":   {"startyear": 2009, "endyear": 2016, "WikidataID": "Q76"},
        "Trump1":  {"startyear": 2017, "endyear": 2020, "WikidataID": "Q22686"},
        "Biden":   {"startyear": 2021, "endyear": 2024, "WikidataID": "Q6279"},
        "Trump2":  {"startyear": 2025, "endyear": 2028, "WikidataID": "Q22686"},
    },
    "Vice President": {
        "Gore":    {"startyear": 1993, "endyear": 2000, "WikidataID": "Q19673"},
        "Cheney":  {"startyear": 2001, "endyear": 2008, "WikidataID": "Q48259"},
        "Biden":   {"startyear": 2009, "endyear": 2016, "WikidataID": "Q6279"},
        "Pence":   {"startyear": 2017, "endyear": 2020, "WikidataID": "Q24313"},
        "Harris":  {"startyear": 2021, "endyear": 2024, "WikidataID": "Q10853588"},
        "Vance":   {"startyear": 2025, "endyear": 2028, "WikidataID": "Q28935729"},
    },
    "First Lady": {
        "Clinton": {"startyear": 1993, "endyear": 2000, "WikidataID": "Q6294"},
        "Bush":    {"startyear": 2001, "endyear": 2008, "WikidataID": "Q152019"},   # Laura Bush
        "Obama":   {"startyear": 2009, "endyear": 2016, "WikidataID": "Q13133"},    # Michelle Obama
        "Trump1":  {"startyear": 2017, "endyear": 2020, "WikidataID": "Q432473"},   # Melania Trump
        "Biden":   {"startyear": 2021, "endyear": 2024, "WikidataID": "Q235349"},   # Jill Biden
        "Trump2":  {"startyear": 2025, "endyear": 2028, "WikidataID": "Q432473"},   # Melania Trump
    },
}


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
def _trailing_term_pattern(terms):
    """Build a pattern matching everything up to and including any of `terms`.

    Group 1 is the whole match, which is what the callers keep.
    """
    return r"((.+)?\s*(" + "|".join(terms) + "))"


RECIP_RANKS = [
    "General", "Admiral", "Captain", "Ambassador", "Colonel",
    "Commander", "Major", "Sergeant", "Special Agent",
]
RECIP_POSITIONS = [
    "Vice President", "White House Staff Member", "Senator",
    "Former President", "President",
]
GIVER_RANKS = [
    "General", "Admiral", "Captain", "Ambassador", "Colonel",
    "Commander", "Major", "Sergeant", r"Marshal(l | )",
]
GIVER_HONORIFICS = [
    "His Excellency", "Her Excellency", "His Majesty", "Her Majesty",
    "The Right Honorable", "The Most Honorable", "His Majesty",
    "His Royal Highness", "His Highness", "President", "Her Highness",
    "Her Royal Highness", "His Holiness", "Senator", "Madame",
    r"H\.M\.", r"H\. E\.", r"T\.H\.", "First Lady", "Chief of General Staff",
]

RECIP_RANK_PATTERN = _trailing_term_pattern(RECIP_RANKS)
RECIP_POSITION_PATTERN = _trailing_term_pattern(RECIP_POSITIONS)
GIVER_RANK_PATTERN = _trailing_term_pattern(GIVER_RANKS)
GIVER_HONORIFIC_PATTERN = _trailing_term_pattern(GIVER_HONORIFICS)

# Courtesy titles dropped from the parsed name (they carry no information).
RECIP_TITLE_PATTERN = r"(T\.H\.|The Honorable|Mr\.|Ms\.|Dr\.|Mrs\.|First Daughter|First Lady) "
GIVER_TITLE_PATTERN = r"(The Honorable|Mr\.|Ms\.|Mrs\.|Dr\.|H\.E\.|H\.R\.H\.|His Excellence|His Excellency) "

# Stray punctuation after an honorific breaks the comma split below, so it is
# normalised away before the name is parsed.
GIVER_PREFIX_FIXES = {
    r"^His Excellency[,.]": "His Excellency",
    r"^His Majesty,": "His Majesty",
    r"^Chief of General Staff,": "Chief of General Staff",
    r"^Lieutenant General Staff,": "Lieutenant General Staff",
    r"^The Honorable,": "The Honorable",
    r"^His Royal Highness[,.]": "His Royal Highness",
    r"^His Highness,": "His Highness",
    r"^His Holiness,": "His Holiness",
}

# Trailing fields packed into the `item` blob, peeled off in this order:
# (new column, pattern capturing (remainder, field), label to strip).
#
# The label strip is case-insensitive and accepts any of the separators the
# source uses (em dash, colon, hyphen), because all three appear -- "Location—",
# "Location:", "Est. value—", "Estimated Value:".
ITEM_FIELDS = [
    ("disposition", r"(.+)(Disposition.+$)", r"(?i)Disposition\s*[—:-—]\s*"),
    ("location",    r"(.+)(Location.+$)",    r"(?i)Location\s*[—:-]\s*"),
    ("estval",      r"(.+)((?:Est|[Aa]ppraised).+$)",   r"(?i)(?:Est(?:imated)?|Appraised)\.?\s*Value\s*[—:-]*\s*"),
    ("recd",        r"(.+)((Rec'?d|Rec'd|Received).+$)",       r"(?i)(Rec'?d|Rec'd|Received)\s*[—:-]*\s*"),
]


DATE_FORMATS = ['%B %d, %Y', '%m/%d/%Y', '%m/%d/%y']


# One token of an estimated-value expression, used to find where the value ends
# and free text begins (see split_value_expression).
#
# Connector words only count when a number follows, so a disposition opening
# with one of them -- "To be retained for official display" -- is not mistaken
# for a continuation of the value.
MONEY = r"\$?\s?\d[\d,]*(?:\.\d+)?"
VALUE_TOKEN = re.compile(
    rf"""
      \s+
    | {MONEY}
    | \$
    | not\s+submitted
    | awaiting\s+appraisal
    | more\s+than\s+minimal\s+value
    | minimal\s+value
    | (?:unknown|undetermined|unspecified|n/a|none)\b
    | (?:each|ea\.?|apiece|respectively|aggregately|aggragately|combined
        |total\s+value|total)\b
    | (?:over|above|about|approximately|approx\.?|exceeds|more\s+than
        |less\s+than|up\s+to|to|and|&|or|plus)
        \s*(?=\$|\d)
    | [-–—,.;:()\[\]/+*=]
    """,
    re.I | re.X,
)

# Punctuation left dangling at the head of the recovered text once the value
# has been taken off the front.
LEADING_SEPARATOR = re.compile(r"^[-–—,.;:/)\s]+")


# Absolute dollar cutoffs, NOT per-file quantiles -- the pipeline runs one file
# per year, so quantiles would mean something different in every file and the
# tiers would not be comparable across time. These are round numbers near the
# pooled quartiles (median $605, p75 $1,400, p90 $3,146); they are not
# inflation-adjusted.
VALUE_TIERS = [(500, "Minimal"), (1500, "Moderate"), (5000, "High")]
VALUE_TIER_TOP = "Exceptional"

# First money amount in an estval string, for the numeric column and the tiers.
AMOUNT = re.compile(r"\$?\s?(\d[\d,]*(?:\.\d+)?)")

# Names that stand in for "no identifiable person"; these get a NIL Wikidata ID
# rather than being left blank, so they are not re-searched later.
EXCLUDED_ENTITIES = [
    "5 U.S.C. 7342(f)(4)", "Foreign Government Official", "Unknown",
    "An Agency Employee", "Unknown", "5 U.S.C. 7342 (f)(4)",
    # Written as escapes because the source data uses a section sign followed
    # by a THIN SPACE, which is indistinguishable from a normal space on screen.
    "5 U.S.C. \u00a7\u20097342(f)(4)", "5USC 7342 (f)(4)", "5 U.S.C.  7342(f)(4)",
    "50 U.S.C. 403-(1)(i)", "Government Official", "U.S. Air Force Employee",
    "Employee of the Department of State", "Department of State employee",
    "USAID Employee", "Unknown Foreign Government Official Donor",
    "Unknown Qatar Government Official", "5 U.S.C. 7342(F)(4)",
    "5 U.S.C. 7342(f)4)", "5USC 7342 (f)(4).", "5USC 7342(f)(4)",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fix_mojibake(s):
    """Undo cp1252-read-as-utf8 damage, leaving anything else untouched."""
    if pd.isna(s):
        return s
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def strip_strings(x):
    return x.strip() if isinstance(x, str) else x


def split_pattern(series, pattern):
    """Split `pattern` off `series`.

    Returns ``(matched_text, remainder)`` — the matched text for a new column
    and the series with the match removed and re-stripped.
    """
    matched = series.str.extract(pattern, expand=False)[0]
    remainder = series.str.replace(pattern, "", regex=True).str.strip()
    return matched, remainder


def split_item_field(df, column_name, regex_pattern, label_pattern):
    """Peel one trailing field (e.g. "Disposition—...") off `item` in place.

    Rows where the pattern does not match keep their original `item`.
    """
    original = df["item"]
    extracted = df["item"].str.extract(regex_pattern, flags=re.M)
    df["item"] = extracted[0].fillna(original)
    df[column_name] = (
        extracted[1]
        .str.replace(label_pattern, "", regex=True)
        .str.strip()
        .str.replace(r"[.;,]$", "", regex=True)
    )


def split_value_expression(text):
    """Split an estval string into ``(value_expression, trailing_text)``.

    Many records carry no "Disposition—" label, so the disposition is left
    glued to the end of the value: ``"$280. Government Property"``. Rather than
    listing the disposition phrases -- an open set, 260+ variants and counting
    -- this walks the *value* off the front. The value vocabulary is closed
    (money, a few quantity words, punctuation), so whatever the walk stops on
    is where the value ends and the free text begins.

    Returns ``(None, None)`` for missing input, and leaves the text untouched
    in the value slot if no value could be read at all.
    """
    if not isinstance(text, str):
        return None, None
    pos = 0
    while pos < len(text):
        match = VALUE_TOKEN.match(text, pos)
        if not match or match.end() == pos:
            break
        pos = match.end()
    value, tail = text[:pos].strip(), LEADING_SEPARATOR.sub("", text[pos:]).strip()
    if not value:
        return text.strip(), None
    return value, (tail or None)


def split_estval(df):
    """Move any disposition text trailing the estimated value into `disposition`.

    Only fills `disposition` where the labelled extraction found nothing, so a
    real "Disposition—..." always wins over text recovered from the value.
    """
    split = df["estval"].map(split_value_expression)
    df["estval"] = [value for value, _ in split]
    recovered = pd.Series([tail for _, tail in split], index=df.index)
    df["disposition"] = df["disposition"].fillna(recovered)
    return df



def estval_amount(estval):
    """First dollar figure in an estval string, as a float."""
    if not isinstance(estval, str):
        return np.nan
    match = AMOUNT.search(estval)
    return float(match.group(1).replace(",", "")) if match else np.nan


def value_tier(amount):
    """Band a dollar amount into a comparable tier."""
    if pd.isna(amount):
        return None
    for cutoff, label in VALUE_TIERS:
        if amount <= cutoff:
            return label
    return VALUE_TIER_TOP



def officeholder(year, role):
    """Name of whoever held `role` in `year`, or None."""
    if pd.isna(year):
        return None
    for name, years in ROLES[role].items():
        if years["startyear"] <= int(year) <= years["endyear"]:
            return name
    return None


# ---------------------------------------------------------------------------
# Per-file pipeline
# ---------------------------------------------------------------------------
def normalise_source_columns(df):
    """Trim the three free-text source columns and forward-fill the blanks.

    A gift listing names the recipient and giver once and leaves the following
    rows blank, so the ffill re-attaches each item to its pair.
    """
    df["item"] = df.item.str.strip()
    df["item_orig"] = df["item"]

    df["recip"] = df.recip.str.strip()
    df["recip"] = df["recip"].replace("", np.nan)
    df["recip"] = df["recip"].ffill()

    df["giver"] = df.giver.str.strip()
    df["giver"] = df["giver"].replace("", np.nan)
    for pattern, replacement in GIVER_PREFIX_FIXES.items():
        df["giver"] = df["giver"].replace(pattern, replacement, regex=True)
    df["giver"] = df["giver"].ffill()
    return df


def split_item_fields(df):
    """Break the `item` blob into item / disposition / location / estval / recd."""
    for column_name, regex_pattern, label_pattern in ITEM_FIELDS:
        split_item_field(df, column_name, regex_pattern, label_pattern)
    df["item"] = (
        df["item"]
        .fillna(df["item_orig"])
        .str.strip()
        .str.replace(r"[.;]$", "", regex=True)
    )
    return split_estval(df)


def parse_recipient(df):
    """Split `recip` into name / title / org, pulling out rank and position."""
    df[["recip_name", "recip_title", "recip_org"]] = df["recip"].str.split(",", n=2, expand=True)
    df["recip_name"] = df.recip_name.str.replace(RECIP_TITLE_PATTERN, "", regex=True)
    df["recip_rank"], df["recip_name"] = split_pattern(df["recip_name"], RECIP_RANK_PATTERN)
    position, df["recip_name"] = split_pattern(df["recip_name"], RECIP_POSITION_PATTERN)
    # A position found inside the name only fills in for a missing title.
    df["recip_title"] = df["recip_title"].fillna(position)
    return df


def parse_giver(df):
    """Split `giver` into name / title / org, pulling out rank and honorifics."""
    df[["giver_name", "giver_title", "giver_org"]] = df["giver"].str.split(", ", n=2, expand=True)
    df["giver_name"] = df.giver_name.str.replace(GIVER_TITLE_PATTERN, "", regex=True)
    df["giver_rank"], df["giver_name"] = split_pattern(df["giver_name"], GIVER_RANK_PATTERN)
    df["giver_title2"], df["giver_name"] = split_pattern(df["giver_name"], GIVER_HONORIFIC_PATTERN)
    return df


def merge_wikidata(df, wiki, name_col, full_col, prefix):
    """Attach Wikidata columns for one party (recipient or giver).

    Matches first on the parsed name, then on the full unparsed string; a match
    on the full string wins, since it is the more specific one.
    """
    df = df.merge(wiki, left_on=name_col, right_on="entity", how="left")
    df = df.drop(columns="entity")
    df = df.merge(wiki, left_on=full_col, right_on="entity", how="left", suffixes=("", "_upd"))
    df = df.drop(columns="entity")
    for col in WIKI_COLS:
        upd_col = f"{col}_upd"
        df[col] = df[upd_col].where(df[upd_col].notna(), df[col])
        df = df.drop(columns=upd_col)
    return df.rename(columns={
        "wiki": f"{prefix}_wiki",
        "wikiname": f"{prefix}_wikiname",
        "descr": f"{prefix}_descr",
    })


def apply_group_overrides(df, groups, match_col, target_col):
    """Override the Wikidata ID for givers/recipients listed in groups.csv.

    These are delegations, families and similar non-person entities that get a
    hand-assigned code (FAMILY, UNCLEAR, ...).
    """
    df = df.merge(groups, left_on=match_col, right_on="giver_orig", how="left")
    mask = df["WikidataID"].notna() & (df["WikidataID"] != "")
    df.loc[mask, target_col] = df["WikidataID"]
    return df.drop(columns=["giver_orig", "WikidataID"])


def fill_role_wikidata(df):
    """Resolve bare role recipients ("President", ...) to that year's holder."""
    df = df.copy()
    for role, holders in ROLES.items():
        holder = df["year"].apply(lambda y: officeholder(y, role))
        mask = (df["recip"] == role) & holder.notna()
        df.loc[mask, "recip_wiki"] = holder[mask].map(lambda name: holders[name]["WikidataID"])
    return df

def standardize_date(s):
    """
    Parse a date string into an ISO date (YYYY-MM-DD).
    Returns pd.NaT if missing, unparseable, or if it looks like a range
    (e.g. 'November 7-9, 2005', 'October 22 to 24, 2005').
    """
    if pd.isna(s):
        return pd.NaT
    s = str(s).strip()
    if not s:
        return pd.NaT
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return pd.NaT  # unrecognized format - worth reviewing manually



def clean(df, wiki, groups, excluded):
    """Run one year's raw records through the whole pipeline."""
    df = normalise_source_columns(df)
    df = split_item_fields(df)
    #df = classify_items(df)
    df = parse_recipient(df)
    df = parse_giver(df)
    df = df.map(strip_strings)

    df = merge_wikidata(df, wiki, "recip_name", "recip", "recip")
    df.loc[df["recip_name"].isin(excluded), "recip_wiki"] = "NIL"

    df = merge_wikidata(df, wiki, "giver_name", "giver", "giver")
    df.loc[df["giver_name"].isin(excluded), "giver_wiki"] = "NIL"

    df = apply_group_overrides(df, groups, "giver", "giver_wiki")
    df.loc[df.giver_name.str.contains(r"^Unknown\b", na=False), "giver_wiki"] = "NIL"

    df = apply_group_overrides(df, groups, "recip", "recip_wiki")
    df = fill_role_wikidata(df)
    return df.map(strip_strings)


# ---------------------------------------------------------------------------
# Lookups and entry point
# ---------------------------------------------------------------------------
def load_lookups():
    wiki = pd.read_csv(WIKI_CSV, encoding="utf-8-sig")
    wiki["entity"] = wiki["entity"].apply(fix_mojibake)
    # A repeated key fans out the left merge and duplicates gift rows, so keep
    # one row per entity. Keys mapped to two different IDs need a manual look.
    conflicts = wiki.drop_duplicates(["entity", "wiki"])
    conflicts = conflicts.loc[conflicts["entity"].duplicated(keep=False), "entity"].unique()
    if len(conflicts):
        print(f"masterwiki: entities with conflicting IDs (kept first): {list(conflicts)}")
    wiki = wiki.drop_duplicates("entity", keep="first")

    groups = pd.read_csv(GROUPS_CSV).drop_duplicates("giver_orig", keep="first")

    with open(NOWIKI_TXT, "r") as f:
        nowikilist = f.read().splitlines()
    excluded = EXCLUDED_ENTITIES + nowikilist

    return wiki, groups, excluded


def main():
    wiki, groups, excluded = load_lookups()
    CLEANED_DIR.mkdir(exist_ok=True)

    for path in sorted(RAW_DIR.glob("*.csv")):
        df = pd.read_csv(path, encoding="utf-8-sig")
        df = clean(df, wiki, groups, excluded)
        df["estval"] = df["estval"].str.strip().str.replace(r"[;.]$", "", regex=True)
        df['recd_std'] = df['recd'].apply(standardize_date)
        df.to_csv(CLEANED_DIR / path.name, index=False)
        print(f"{path.name}: {len(df)} rows")


if __name__ == "__main__":
    main()
