"""Cache Wikidata metadata for every position (P39) and employer (P108) item.

The claims snapshot (files/wikidata_claims.csv) gives the position or employer
QID and the spell dates, but not the organization a position belongs to or its
country. This script fetches, for each such QID:

  P31  instance of          -> used to type employers and positions
  P279 subclass of          -> generic positions ("ambassador", "senator")
  P17  country              -> country of the position / organization
  P1001 applies to jurisdiction
  P2389 organization directed by the office or position
  P361 part of

and the English labels of all referenced items. Output:
  analysis_revised/cache/position_meta.csv   (one row per qid x property x value)

The script is read-only against Wikidata. It only requests QIDs that are not
already in the cache, so reruns are offline once the cache is complete.

Run from the repo root:
  /home/arpie/envs/revised/bin/python analysis_revised/01_fetch_position_metadata.py
"""

import time
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent.parent
CLAIMS = BASE / "files" / "wikidata_claims.csv"
CACHE = BASE / "analysis_revised" / "cache" / "position_meta.csv"
API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "gifts-revised-analysis/1.0 (academic research script; python-requests)"}
PROPS = ["P31", "P279", "P17", "P1001", "P2389", "P361"]


def get_entities(qids, props):
    out = {}
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        for attempt in range(8):
            try:
                r = requests.get(API, headers=HEADERS, timeout=60, params={
                    "action": "wbgetentities", "ids": "|".join(batch), "props": props,
                    "languages": "en|mul", "format": "json"})
                r.raise_for_status()
                out.update(r.json().get("entities", {}))
                break
            except Exception as e:  # rate limit or network hiccup: back off and retry
                wait = 10 * (attempt + 1)
                if getattr(e, "response", None) is not None and e.response.headers.get("Retry-After"):
                    wait = max(wait, int(e.response.headers["Retry-After"]))
                print("retry", attempt, type(e).__name__, f"batch {i // 50}", f"wait {wait}s")
                time.sleep(wait)
        else:
            print(f"batch {i // 50} failed; its QIDs stay uncached and are retried on the next run")
        time.sleep(1.0)
    return out


def label_of(ent):
    labs = ent.get("labels", {})
    # Items with no English label keep their QID as the label (so they read back as cached).
    return (labs.get("en") or labs.get("mul") or {}).get("value", ent.get("id", ""))


def main():
    claims = pd.read_csv(CLAIMS, low_memory=False)
    supp = BASE / "analysis_revised" / "cache" / "claims_supplement.csv"
    if supp.exists():   # written by 01b_fetch_missing_claims.py
        claims = pd.concat([claims, pd.read_csv(supp)], ignore_index=True)
    qids = sorted(set(claims.loc[claims["property"].isin(["P39", "P108"]), "value"].dropna()))
    qids = [q for q in qids if str(q).startswith("Q")]
    cache = pd.read_csv(CACHE) if CACHE.exists() else pd.DataFrame(
        columns=["qid", "qid_label", "property", "value", "value_label"])
    # Rows from an earlier failed request (no label and no statements) are not a real
    # cache entry, so those QIDs are fetched again.
    failed = cache.groupby("qid").apply(
        lambda g: g["qid_label"].isna().all() and g["property"].isna().all(), include_groups=False)
    cache = cache[~cache["qid"].isin(failed[failed].index)]
    todo = [q for q in qids if q not in set(cache["qid"])]
    print(f"{len(qids)} position/employer items; {len(todo)} not cached")
    missing_labels = cache["value"].notna() & cache["value_label"].isna()
    if missing_labels.any():   # repair labels of referenced items from a failed label request
        ents = get_entities(sorted(set(cache.loc[missing_labels, "value"])), "labels")
        cache.loc[missing_labels, "value_label"] = cache.loc[missing_labels, "value"].map(
            lambda q: label_of(ents[q]) if q in ents else None)
        print(f"repaired {cache.loc[missing_labels, 'value_label'].notna().sum()} labels")
    if not todo:
        cache.to_csv(CACHE, index=False)
        return

    ents = get_entities(todo, "labels|claims")
    rows = []
    for qid in todo:
        if qid not in ents:      # request failed: leave uncached
            continue
        ent = ents[qid]
        lab = label_of(ent)
        got = False
        for p in PROPS:
            for st in ent.get("claims", {}).get(p, []):
                dv = st.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(dv, dict) and "id" in dv:
                    rows.append({"qid": qid, "qid_label": lab, "property": p, "value": dv["id"]})
                    got = True
        if not got:   # keep a row so the QID counts as cached
            rows.append({"qid": qid, "qid_label": lab, "property": "", "value": ""})
    new = pd.DataFrame(rows)

    # Labels of the referenced items.
    refs = sorted(set(new["value"].dropna()) - {""})
    lab_ents = get_entities(refs, "labels")
    new["value_label"] = new["value"].map(lambda q: label_of(lab_ents[q]) if q in lab_ents else None)
    pd.concat([cache, new], ignore_index=True).to_csv(CACHE, index=False)
    print(f"wrote {CACHE} ({len(new)} new rows)")


if __name__ == "__main__":
    main()
