"""Fetch Wikidata claims for linked people missing from files/wikidata_claims.csv.

scripts/wiki_properties.py enriches the QIDs listed in files/masterwiki_new.csv.
QIDs assigned by the bare-office rule in parseandclean_new.py (ROLES: "President"
-> that year's holder, etc.) are not in that list, so some heavily observed people
(George W. Bush, Laura Bush) have no claims. This script fetches the same
properties, in the same schema, for every linked QID absent from the snapshot and
writes analysis_revised/cache/claims_supplement.csv. The original snapshot is not
modified; the revised analysis reads both files.

Run from the repo root:
  /home/arpie/envs/revised/bin/python analysis_revised/01b_fetch_missing_claims.py
"""

import re
import time
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent.parent
CLAIMS = BASE / "files" / "wikidata_claims.csv"
GIFTS = BASE / "analysis" / "output" / "gifts_analysis.csv"
OUT = BASE / "analysis_revised" / "cache" / "claims_supplement.csv"
API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "gifts-revised-analysis/1.0 (academic research script; python-requests)"}
# Same property list as scripts/wiki_properties.py.
PROPS = ["P39", "P102", "P108", "P69", "P106", "P21", "P569", "P570", "P27", "P410", "P40", "P22", "P25",
         "P26", "P3373", "P101", "P31", "P452", "P571", "P17", "P749", "P355", "P159"]


def api_get(params, tries=8):
    for attempt in range(tries):
        r = requests.get(API, headers=HEADERS, timeout=60, params={**params, "format": "json"})
        if r.status_code in (429, 502, 503, 504):
            time.sleep(int(r.headers.get("Retry-After", 5 * 2 ** attempt)))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("giving up")


def snak_value(snak):
    if snak.get("snaktype") == "somevalue":
        return "unknown", None
    if snak.get("snaktype") == "novalue":
        return "none", None
    dv = snak.get("datavalue")
    if not dv:
        return "", None
    v, t = dv["value"], dv["type"]
    if t == "wikibase-entityid":
        return v["id"], None
    if t == "time":
        return v["time"].lstrip("+"), v.get("precision")
    if t == "quantity":
        return v["amount"], None
    if t == "monolingualtext":
        return v["text"], None
    return str(v), None


def qual_time(q, pid):
    for snak in q.get(pid, [])[:1]:
        return snak_value(snak)[0]
    return ""


def main():
    claims = pd.read_csv(CLAIMS, low_memory=False, usecols=["item"])
    g = pd.read_csv(GIFTS, low_memory=False, usecols=["recip_wiki", "giver_wiki"])
    linked = set()
    for col in ("recip_wiki", "giver_wiki"):
        linked |= {q for q in g[col].dropna().astype(str).str.strip() if re.match(r"^Q\d+$", q)}
    ids = sorted(linked - set(claims["item"]))
    print(f"{len(ids)} linked QIDs missing from the claims snapshot: {ids}")
    rows, labels = [], {}
    for i in range(0, len(ids), 50):
        data = api_get({"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]),
                        "props": "claims|labels", "languages": "en"})
        for qid, ent in data.get("entities", {}).items():
            labels[qid] = ent.get("labels", {}).get("en", {}).get("value", "")
            for pid in set(PROPS) & set(ent.get("claims", {})):
                for st in ent["claims"][pid]:
                    if st.get("rank") == "deprecated":
                        continue
                    val, prec = snak_value(st["mainsnak"])
                    q = st.get("qualifiers", {})
                    rows.append({"item": qid, "property": pid, "value": val, "value_precision": prec,
                                 "start": qual_time(q, "P580"), "end": qual_time(q, "P582"),
                                 "rank": st.get("rank")})
        time.sleep(1)
    out = pd.DataFrame(rows)
    is_q = out["value"].astype(str).str.match(r"^Q\d+$")
    refs = sorted(set(out.loc[is_q, "value"]) | set(PROPS))
    lab = {}
    for i in range(0, len(refs), 50):
        data = api_get({"action": "wbgetentities", "ids": "|".join(refs[i:i + 50]), "props": "labels",
                        "languages": "en"})
        lab.update({k: e.get("labels", {}).get("en", {}).get("value", "") for k, e in data["entities"].items()})
        time.sleep(1)
    out["itemLabel"] = out["item"].map(labels)
    out["propertyLabel"] = out["property"].map(lab)
    out["valueLabel"] = out["value"].map(lab).fillna("")
    out.loc[~is_q, "valueLabel"] = out.loc[~is_q, "value"]
    out = out[["item", "itemLabel", "property", "propertyLabel", "value", "valueLabel", "value_precision",
               "start", "end", "rank"]].drop_duplicates()
    out["retrieved"] = time.strftime("%Y-%m-%d")
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} statements for {out['item'].nunique()} people")


if __name__ == "__main__":
    main()
