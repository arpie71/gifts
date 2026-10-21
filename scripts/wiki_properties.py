import time
import requests
import pandas as pd

API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "Raymond Hicks research script (arpie71@gmail.com)"}  # use real contact info

PROPS = ["P39","P102","P108","P69","P106","P21","P569","P570","P27",
         "P410","P40","P22","P25","P26","P3373","P101", "P31","P452","P571","P17","P749","P355","P159"]
PROPSET = set(PROPS)

session = requests.Session()
session.headers.update(HEADERS)


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def api_get(params, tries=6):
    params = {**params, "format": "json"}          # no maxlag for read requests
    last = None
    for attempt in range(tries):
        try:
            r = session.get(API, params=params, timeout=60)
            if r.status_code in (429, 502, 503, 504):
                wait = int(r.headers.get("Retry-After", 5 * 2 ** attempt))
                last = f"HTTP {r.status_code}"
                print(f"  {last}; waiting {wait}s")
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")  # 403 etc. fail fast
            data = r.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except (requests.RequestException, ValueError) as e:
            last = f"{type(e).__name__}: {e}"
            wait = 5 * 2 ** attempt
            print(f"  {last}; waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"giving up on {params.get('ids', '')[:40]}... last error: {last}")

def snak_value(snak):
    """Return (value, precision) from a snak. Value is a QID, ISO date, string, etc."""
    st = snak.get("snaktype")
    if st == "somevalue":
        return "unknown", None
    if st == "novalue":
        return "none", None
    dv = snak.get("datavalue")
    if not dv:
        return "", None
    v, t = dv["value"], dv["type"]
    if t == "wikibase-entityid":
        return v["id"], None
    if t == "time":
        return v["time"].lstrip("+"), v.get("precision")   # precision: 9=year, 10=month, 11=day
    if t == "string":
        return v, None
    if t == "quantity":
        return v["amount"], None
    if t == "monolingualtext":
        return v["text"], None
    return str(v), None


def qual_time(qualifiers, pid):
    """First value of a qualifier (e.g., P580 start, P582 end), or ''."""
    for snak in qualifiers.get(pid, [])[:1]:
        return snak_value(snak)[0]
    return ""


def fetch_claims(ids):
    """Pass 1: claims + item labels for all IDs, 50 per request."""
    rows, item_labels, missing = [], {}, []
    for batch in chunks(ids, 50):
        data = api_get({
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "claims|labels",
            "languages": "en",
        })
        for qid, ent in data.get("entities", {}).items():
            if "missing" in ent:
                missing.append(qid)
                continue
            item_labels[qid] = ent.get("labels", {}).get("en", {}).get("value", "")
            for pid in PROPSET & set(ent.get("claims", {})):
                for st in ent["claims"][pid]:
                    if st.get("rank") == "deprecated":
                        continue
                    val, prec = snak_value(st["mainsnak"])
                    q = st.get("qualifiers", {})
                    rows.append({
                        "item": qid,
                        "property": pid,
                        "value": val,
                        "value_precision": prec,
                        "start": qual_time(q, "P580"),
                        "end": qual_time(q, "P582"),
                        "rank": st.get("rank"),
                    })
        time.sleep(1)
    return rows, item_labels, missing


def fetch_labels(idlist):
    """Pass 2: English labels for any mix of Q and P IDs, 50 per request."""
    labels = {}
    for batch in chunks(sorted(set(idlist)), 50):
        data = api_get({
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "en",
        })
        for eid, ent in data.get("entities", {}).items():
            labels[eid] = ent.get("labels", {}).get("en", {}).get("value", "")
        time.sleep(1)
    return labels


# ---- run ----
import glob
import pandas as pd


df = pd.read_csv('files/masterwiki_new.csv')

ids = (df['wiki'].dropna().astype(str).str.strip().unique().tolist())
ids = [i for i in ids if i.startswith("Q")]
print(len(ids), "unique IDs")

rows, item_labels, missing = fetch_claims(ids)          # ids = your unique QID list
out = pd.DataFrame(rows)

# only entity-valued rows (Q-ids) need label lookup; dates and strings pass through
is_q = out["value"].astype(str).str.match(r"^Q\d+$")
lab = fetch_labels(out.loc[is_q, "value"].tolist() + PROPS)

out["itemLabel"] = out["item"].map(item_labels)
out["propertyLabel"] = out["property"].map(lab)
out["valueLabel"] = out["value"].map(lab).fillna("")
out.loc[~is_q, "valueLabel"] = out.loc[~is_q, "value"]  # dates/strings labeled as themselves

out = out[["item","itemLabel","property","propertyLabel","value","valueLabel",
           "value_precision","start","end","rank"]].drop_duplicates()
out.to_csv("cleaned/wikidata_claims.csv", index=False)
print(len(out), "rows;", len(missing), "missing/deleted IDs:", missing[:10])