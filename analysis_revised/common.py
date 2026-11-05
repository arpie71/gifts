"""Shared paths, classification rules, and estimators for the revised analysis.

Nothing here reads or writes files on import.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
REV = BASE / "analysis_revised"
DATA = REV / "data"
CACHE = REV / "cache"
TAB = REV / "output" / "tables"
FIG = REV / "output" / "figures"
OUTJ = REV / "output" / "numbers.json"

GIFTS = BASE / "analysis" / "output" / "gifts_analysis.csv"      # original analysis file (read only)
CLAIMS = BASE / "files" / "wikidata_claims.csv"
CLAIMS_SUPP = CACHE / "claims_supplement.csv"   # linked QIDs absent from the snapshot (01b script)
EMP_TYPES = BASE / "files" / "employer_types.csv"
POS_META = CACHE / "position_meta.csv"
MASTERWIKI = BASE / "files" / "masterwiki_new.csv"

SEED = 20261105
FIRST_YEAR, LAST_YEAR = 1998, 2023     # receipt years used in panels
OPEN_END = 2025                        # open spells run to the claims snapshot year
QID = re.compile(r"^Q\d+$")

# ---------------------------------------------------------------------------
# Periods and events (for temporal analysis). Years are receipt years.
# ---------------------------------------------------------------------------
PERIODS = [("Clinton", 1998, 2000), ("Bush I", 2001, 2004), ("Bush II", 2005, 2008),
           ("Obama I", 2009, 2012), ("Obama II", 2013, 2016), ("Trump", 2017, 2020),
           ("Biden", 2021, 2023)]
EVENTS = {2001: "9/11", 2003: "Iraq war; DHS", 2005: "ODNI created", 2008: "Financial crisis",
          2011: "Arab Spring", 2014: "Crimea", 2020: "COVID-19", 2022: "Ukraine invasion"}


def period_of(year):
    for name, a, b in PERIODS:
        if a <= year <= b:
            return name
    return None


# ---------------------------------------------------------------------------
# Career-spell classification
# ---------------------------------------------------------------------------
# Sector of a position held (P39) or employer (P108). Rules are checked in
# order against "position label | organization label | P31/P279 labels";
# the first match wins. Sectors are generic so the same rules serve U.S.
# recipients and foreign givers; the country of the spell is kept separately.
IO_RX = (r"United Nations|\bUN\b|UNESCO|UNICEF|UNHCR|World Bank|International Monetary Fund|\bIMF\b|OECD|"
         r"World Health Organization|World Trade Organization|International Atomic Energy|European Commission|"
         r"European Union|Council of Europe|Secretary General of NATO|NATO Secretary|African Union|"
         r"Arab League|League of Arab States|Gulf Cooperation Council|ASEAN|Organization of American States|"
         r"African Development Bank|Asian Development Bank|Inter-American Development Bank|"
         r"International Labour|Food and Agriculture Organization|intergovernmental organization|"
         r"international organization|specialized agency|international financial institution|"
         r"Interpol|International Committee of the Red Cross|International Criminal Court|"
         r"European Parliament|Commonwealth Secretar|ECOWAS|Organi[sz]ation of African Unity|"
         r"Economic Community of|Organisation of Islamic|Organization of Islamic")
US_STATES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|"
             "Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|"
             "Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|"
             "New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
             "South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|"
             "Wisconsin|Wyoming|Puerto Rico|Guam|District of Columbia")
SECTOR_RULES = [
    ("Monarchy/ceremonial", r"\bKing of|\bQueen of|\bEmir of|Sultan of|Crown Prince|monarch|First Lady|Second Lady|"
                            r"First Gentleman|[Ss]pouse of|consort|Prince of|Grand Duke|Princess|Governor-General"),
    ("Diplomatic",          r"[Aa]mbassador|Permanent Representative|[Ee]nvoy|[Cc]onsul\b|Consul General|"
                            r"Chief of Protocol|diplomat|chargé d'affaires|High Commissioner to"),
    ("Intl organization",   IO_RX),
    # Civilian service secretaries and public corporations/laboratories before the keyword rules.
    ("National executive",  r"(?:Secretary|Under Secretary|Assistant Secretary) of the (?:Army|Navy|Air Force)|"
                            r"Overseas Private Investment Corporation|Millennium Challenge Corporation|"
                            r"Export-Import Bank|National Institute of Standards|National Institutes of Health|"
                            r"National Aeronautics|President-elect|United States Attorney|"
                            r"Corporation for Public Broadcasting|Tennessee Valley Authority"),
    ("Monarchy/ceremonial", r"Privy Council"),
    ("Military",            r"Chief of Staff of the (?:United States )?(?:Army|Air Force)|Joint Chiefs|Chief of Naval|"
                            r"Commandant|[Cc]ommander|Chief of (?:the )?(?:General|Defence|Defense|Army|Air|Naval) Staff|"
                            r"Supreme Allied|Chief of Space Operations|Chief of the National Guard|"
                            r"armed forces|military|[Aa]rmy\b|[Nn]avy\b|[Aa]ir [Ff]orce|Marine Corps|Coast Guard"),
    ("Judiciary",           r"[Jj]udge|Justice of|[Cc]ourt\b|[Jj]urist"),
    ("Subnational",         r"(?:" + US_STATES + r").*(?:[Ss]enat|[Hh]ouse|[Aa]ssembly|[Ll]egislat|[Gg]overnor|"
                            r"[Dd]elegate|[Cc]ouncil|[Aa]ttorney [Gg]eneral|[Tt]reasurer|[Ss]ecretary of [Ss]tate)|"
                            r"(?:[Ss]enat|[Hh]ouse|[Aa]ssembly|[Ll]egislat|[Gg]overnor|[Aa]ttorney [Gg]eneral).*(?:"
                            + US_STATES + r")|[Ll]ieutenant [Gg]overnor|[Mm]ayor|council member|city council|"
                            r"[Cc]ounty|municipal|[Aa]lderman|Governor of (?!the )|provincial|[Pp]refect|district attorney|board of education"),
    ("Legislature",         r"United States representative|United States senator|^senator$|"
                            r"Knesset|Leader of the Opposition|Federation Council|Assembly of the Republic|"
                            r"(?i:member of) (?:the )?(?:[A-Z][^ ]* )*(?:Parliament|House|Congress|Knesset|Bundestag|"
                            r"Duma|National Assembly|Senate|Chamber|Majlis|Diet|Lok Sabha|Rajya Sabha|Shura|Cortes|"
                            r"Riksdag|Storting|Sejm|Folketing|Bundesrat|Dáil|Seanad|Verkhovna Rada|Legislative)|"
                            r"Speaker|President pro tempore|Majority Leader|Minority Leader|[Ww]hip\b|"
                            r"parliamentarian|legislator|Member of Parliament|Teachta|U\.S\. House|"
                            r"United States House|Congressional"),
    ("Party",               r"[Pp]arty\b|National Committee"),
    ("Academic/research",   r"[Pp]rofessor|[Dd]ean\b|[Pp]rovost|[Uu]niversit|College|[Ii]nstitute|[Rr]esearch|"
                            r"[Ff]ellow\b|[Ll]ecturer|think tank|[Aa]cademy of [Ss]ciences|[Ll]aborator|[Ss]chool|"
                            r"JILA|Council on Foreign Relations|Brookings|RAND Corporation|[Ff]oundation|academic"),
    ("Private",             r"chief executive|\bCEO\b|chairman of the board|managing director|chief operating|"
                            r"chief financial|business|company|corporation|enterprise|\bbank\b|law firm|firm\b|"
                            r"conglomerate|investment|holding|manufacturer|consult|airline|newspaper|television|"
                            r"media|broadcast|Goldman Sachs|WestExec|Inc\.|LLC|\bpartner\b|publisher"),
    ("National executive",  r"President of|Vice President|[Pp]rime [Mm]inister|[Mm]inister|Secretary|"
                            r"Chief of Staff|National Security Advis|[Cc]hancellor|head of (?:state|government)|"
                            r"Premier|Attorney General|[Aa]dvis[eo]r|Press Secretary|Counselor|[Dd]irector|"
                            r"Administrator|Commissioner|Inspector General|Comptroller|Surgeon General|"
                            r"Coordinator|Policy Planning|[Dd]eputy|civil servant|government agency|[Mm]inistry|"
                            r"executive department|federal agency|central bank|independent agency|"
                            r"intelligence agency|regulatory|public body|Department of|Agency|Bureau|"
                            r"Office of|Federal Reserve|[Gg]overnor of the .*[Bb]ank|Librarian|Archivist|"
                            r"Treasurer|Solicitor General|^[Pp]resident$|^[Ss]ecretary$|government|"
                            r"Executive Office"),
]
SECTORS = list(dict.fromkeys([s for s, _ in SECTOR_RULES])) + ["Unclassified"]
# Domains for the revolving-door definition (public / international / academic / private).
DOMAIN = {"Monarchy/ceremonial": "Public", "Diplomatic": "Public", "Military": "Public", "Judiciary": "Public",
          "Subnational": "Public", "Legislature": "Public", "Party": "Public", "National executive": "Public",
          "Intl organization": "International", "Academic/research": "Academic", "Private": "Private",
          "Unclassified": None}
# Labels too generic to classify without the qualifier (P642 'of') that the claims snapshot lacks.
GENERIC = r"^(?:board member|member|delegate|chairperson|chair|director|president|member of the board|vice-chairperson|" \
          r"vice president|chief executive officer|secretary|deputy|trustee|executive director|" \
          r"general secretary|leader|spokesperson|commissioner)$"

# Senior U.S. offices (cabinet level and above, plus their spouses). Used for the
# 'exclude prominent officials' sensitivity analyses.
US_ELITE_RX = (r"^President of the United States$|^Vice President of the United States$|"
               r"First Lady of the United States|Second Lady|First Gentleman|"
               r"^United States Secretary of|^United States Attorney General$|^White House Chief of Staff$|"
               r"^United States National Security Advisor$|^Director of the Central Intelligence Agency$|"
               r"^Director of National Intelligence$|^Chairman of the Joint Chiefs of Staff$|"
               r"^United States Ambassador to the United Nations$|^Speaker of the United States House|"
               r"^Director of the Office of Management and Budget$|^United States Trade Representative$|"
               r"^Administrator of the Environmental Protection Agency$|^President-elect of the United States$")
# Titles in the gift record that mark the same tier when Wikidata is silent.
US_ELITE_TITLE_RX = (r"^President$|President of the United States|^Vice President|First Lady|Second Lady|"
                     r"^Secretary of (?:State|Defense|the Treasury|Homeland|Commerce|Energy|Agriculture|"
                     r"Labor|Education|Transportation|Veterans|Health|the Interior|Housing)|Attorney General|"
                     r"White House Chief of Staff|National Security Advis[eo]r|Director of Central Intelligence|"
                     r"Director,? Central Intelligence Agency|Director of National Intelligence|"
                     r"Chairman,? (?:of the )?Joint Chiefs")


def classify_sector(text):
    if not isinstance(text, str) or not text:
        return "Unclassified"
    for sector, rx in SECTOR_RULES:
        if re.search(rx, text):
            return sector
    return "Unclassified"


def year_of(s):
    """Year of a Wikidata time string ('2009-01-20T00:00:00Z'); NaN when missing."""
    if not isinstance(s, str) or not s[:4].lstrip("+-").isdigit():
        return np.nan
    return float(s[:4])


# ---------------------------------------------------------------------------
# Estimators with high-dimensional fixed effects
# ---------------------------------------------------------------------------
def _demean(M, fes, w=None, tol=1e-10, maxit=500):
    """Weighted within-transformation for several fixed effects (alternating projections)."""
    M = np.array(M, float, copy=True)
    if not fes:
        return M
    if M.ndim == 1:
        M = M[:, None]
    w = np.ones(len(M)) if w is None else w
    codes = [pd.factorize(f)[0] for f in fes]
    wsums = [np.bincount(c, weights=w) for c in codes]
    for _ in range(maxit):
        old = M.copy()
        for c, ws in zip(codes, wsums):
            for j in range(M.shape[1]):
                means = np.bincount(c, weights=w * M[:, j]) / np.where(ws > 0, ws, 1)
                M[:, j] -= means[c]
        if np.max(np.abs(M - old)) < tol:
            break
    return M


def _cluster_vcov(Xd, u, cl, bread):
    G = pd.factorize(cl)[0]
    S = np.zeros((G.max() + 1, Xd.shape[1]))
    np.add.at(S, G, Xd * u[:, None])
    meat = S.T @ S
    ng, n, k = G.max() + 1, len(u), Xd.shape[1]
    return bread @ meat @ bread * ng / (ng - 1) * (n - 1) / max(n - k, 1)


def drop_singletons(df, fe_cols):
    """Drop observations that are alone in any fixed-effect group (iteratively)."""
    df = df.copy()
    while True:
        keep = np.ones(len(df), bool)
        for f in fe_cols:
            keep &= df.groupby(f)[f].transform("size").to_numpy() > 1
        if keep.all():
            return df
        df = df[keep]


def ols_fe(df, y, xs, fe=(), cluster=None):
    """OLS with absorbed fixed effects and cluster-robust SEs."""
    d = df.dropna(subset=[y, *xs, *fe] + ([cluster] if cluster else [])).copy()
    if fe:
        d = drop_singletons(d, list(fe))
    fes = [d[f].to_numpy() for f in fe]
    Y = _demean(d[y].to_numpy(float), fes)[:, 0]
    X = _demean(d[xs].to_numpy(float), fes)
    if not fe:
        X = np.column_stack([np.ones(len(d)), X])
    keep = np.abs(X).sum(0) > 1e-8
    Xk = X[:, keep]
    bread = np.linalg.pinv(Xk.T @ Xk)
    b = bread @ Xk.T @ Y
    u = Y - Xk @ b
    V = _cluster_vcov(Xk, u, d[cluster].to_numpy() if cluster else np.arange(len(d)), bread)
    names = ([] if fe else ["const"]) + list(xs)
    names = [n for n, k in zip(names, keep) if k]
    res = pd.DataFrame({"coef": b, "se": np.sqrt(np.diag(V))}, index=names)
    res.attrs.update(n=len(d), clusters=d[cluster].nunique() if cluster else len(d),
                     ymean=float(d[y].mean()), model="OLS", fe=list(fe))
    return res


def ppml_fe(df, y, xs, fe=(), cluster=None, tol=1e-8, maxit=100):
    """Poisson pseudo-maximum likelihood with absorbed fixed effects (IRLS + demeaning).

    Groups in which the outcome is always zero are dropped first, since they carry
    no information about the slopes (as in ppmlhdfe).
    """
    d = df.dropna(subset=[y, *xs, *fe] + ([cluster] if cluster else [])).copy()
    for f in fe:
        d = d[d.groupby(f)[y].transform("sum") > 0]
    if fe:
        d = drop_singletons(d, list(fe))
    yv = d[y].to_numpy(float)
    X = d[xs].to_numpy(float)
    if not fe:
        X = np.column_stack([np.ones(len(d)), X])
    fes = [d[f].to_numpy() for f in fe]
    mu = (yv + yv.mean()) / 2
    eta = np.log(mu)
    b = np.zeros(X.shape[1])
    for it in range(maxit):
        z = eta + (yv - mu) / mu
        w = mu
        Zd = _demean(z, fes, w)[:, 0]
        Xd = _demean(X, fes, w)
        sw = np.sqrt(w)
        keep = np.abs(Xd).sum(0) > 1e-8
        bk, *_ = np.linalg.lstsq(Xd[:, keep] * sw[:, None], Zd * sw, rcond=None)
        b_new = np.zeros(X.shape[1]); b_new[keep] = bk
        resid = Zd - Xd @ b_new
        eta_new = z - resid                      # fitted linear index incl. FE
        eta_new = np.clip(eta_new, -30, 30)
        mu = np.exp(eta_new)
        if np.max(np.abs(b_new - b)) < tol and it > 2:
            b = b_new
            eta = eta_new
            break
        b, eta = b_new, eta_new
    Xd = _demean(X, fes, mu)
    keep = np.abs(Xd).sum(0) > 1e-8
    Xk = Xd[:, keep]
    bread = np.linalg.pinv(Xk.T @ (Xk * mu[:, None]))
    u = yv - mu
    V = _cluster_vcov(Xk, u, d[cluster].to_numpy() if cluster else np.arange(len(d)), bread)
    names = ([] if fe else ["const"]) + list(xs)
    names = [n for n, k in zip(names, keep) if k]
    res = pd.DataFrame({"coef": b[keep], "se": np.sqrt(np.diag(V))}, index=names)
    res.attrs.update(n=len(d), clusters=d[cluster].nunique() if cluster else len(d),
                     ymean=float(yv.mean()), model="Poisson PML", fe=list(fe), iterations=it + 1)
    return res


# ---------------------------------------------------------------------------
# LaTeX tables
# ---------------------------------------------------------------------------
def fix_mojibake(s):
    """Repair UTF-8 text that was decoded as cp1252/latin-1 upstream (e.g. 'IsÄƒrescu')."""
    if not isinstance(s, str) or not any(ch in s for ch in "ÃÄÅâ"):
        return s
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s


def tex_escape(x):
    s = fix_mojibake(str(x))
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\^{}")]:
        s = s.replace(a, b)
    return s


def write_tex(df, name, caption=None, note=None, index=False, align=None):
    """Write a booktabs tabular (and a CSV twin) to output/tables/."""
    TAB.mkdir(parents=True, exist_ok=True)
    d = df.reset_index() if index else df
    align = align or "l" + "r" * (d.shape[1] - 1)
    lines = []
    if caption:
        lines.append(f"% {caption}")
    lines += [rf"\begin{{tabular}}{{{align}}}", r"\toprule",
              " & ".join(tex_escape(c) for c in d.columns) + r" \\", r"\midrule"]
    for _, row in d.iterrows():
        cells = []
        for v in row:
            if isinstance(v, str) and v.startswith("$") and v.endswith("$"):
                cells.append(v)            # pre-formatted math (e.g. stars)
            else:
                cells.append(tex_escape(v))
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    if note:
        lines.append(r"\par\smallskip{\footnotesize " + tex_escape(note) + "}")
    (TAB / f"{name}.tex").write_text("\n".join(lines) + "\n")
    d.to_csv(TAB / f"{name}.csv", index=False)


def stars(coef, se):
    if not np.isfinite(se) or se == 0:
        return f"{coef:.3f}"
    z = abs(coef / se)
    s = "***" if z > 3.291 else "**" if z > 2.576 else "*" if z > 1.96 else ""
    return f"{coef:.3f}{s}"


def regtable(models, labels, rows, name, caption, note=None, extra=None):
    """Side-by-side coefficient table from a list of result frames."""
    out = []
    for var, lab in rows:
        c = [lab] + [stars(m.loc[var, "coef"], m.loc[var, "se"]) if var in m.index else "" for m in models]
        s = [""] + [f"({m.loc[var, 'se']:.3f})" if var in m.index else "" for m in models]
        out += [c, s]
    for key, lab in [("n", "Observations"), ("clusters", "Clusters"), ("ymean", "Mean of outcome")]:
        out.append([lab] + [f"{m.attrs[key]:,.0f}" if key != "ymean" else f"{m.attrs[key]:.2f}" for m in models])
    out.append(["Estimator"] + [m.attrs["model"] for m in models])
    out.append(["Fixed effects"] + [", ".join(m.attrs["fe"]) or "none" for m in models])
    for lab, vals in (extra or []):
        out.append([lab] + vals)
    df = pd.DataFrame(out, columns=[""] + labels)
    write_tex(df, name, caption=caption, note=note)
    return df
