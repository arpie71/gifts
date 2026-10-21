"""Probe: assign an item type to each gift description.

Strategy mirrors the estval splitter -- match on the most reliable signal
first. For an item description that is the *head noun* (the text before the
first comma), because the source writes "Goum silk rug, modern, ivory
ground..." -- everything after the first comma is material and colour, which
is exactly what pulls a keyword match in the wrong direction.

So: try the head phrase first, fall back to the whole description, and give up
rather than guess.
"""

import collections
import glob
import re

import pandas as pd

# Ordered: first match wins. Order matters because descriptions name materials
# ("gold", "silver") that would otherwise drag everything into jewellery.
CATEGORIES = [
    ("Travel & Hospitality", r"""
        travels?|lodging|airfares?|air\s*fare|hotels?|accommodations?|meals?|
        banquets?|transportations?|transport|flights?|airlines?|helicopters?|
        expenses?|itinerar\w*|excursions?|tours?|\d+\s*nights?|overnight|
        dinners?|luncheons?|receptions?|conference\s+registration|
        expended\s+for|round-?trip
    """),
    ("Books & Media", r"""
        books?|hardcovers?|paperbacks?|volumes?|atlas|almanac|catalog(?:ue)?s?|
        magazines?|journals?|manuscripts?|monographs?|encyclopedias?|
        dictionar\w+|dvds?|compact\s+discs?|recordings?|photo\s*albums?|
        memoirs?|biograph\w+|scrolls?|maps?
    """),
    ("Jewellery & Watches", r"""
        watch(?:es)?|wristwatch(?:es)?|necklaces?|bracelets?|earrings?|
        (?<!ear)rings?(?!\s+(?:handle|stand|around|binder))|brooch(?:es)?|
        pendants?|cufflinks?|cuff\s+links?|jewell?ery|tiaras?|anklets?|
        lockets?|rosar\w+|lapel\s+pins?|tie\s*(?:pins?|clips?|tacks?)|
        chronographs?|strands?\s+of\s+pearls
    """),
    ("Textiles & Rugs", r"""
        rugs?|carpets?|tapestr\w+|kilims?|quilts?|blankets?|throws?|
        cushions?|pillows?|linens?|embroider\w+|weaving|textiles?|
        tablecloths?|wall\s+hangings?
    """),
    ("Art & Decorative", r"""
        paintings?|sculptures?|statues?|statuettes?|figurines?|artworks?|
        prints?|lithographs?|etchings?|drawings?|portraits?|watercolou?rs?|
        mosaics?|icons?|vases?|urns?|busts?|carvings?|ornaments?|decorative|
        calligraph\w+|sketch(?:es)?|frames?|framed|shadow\s+box(?:es)?|
        figures?|engravings?|ceramics?|porcelain|crystal|bonsai
    """),
    ("Household & Tableware", r"""
        bowls?|plates?|platters?|trays?|tea\s+sets?|coffee\s+sets?|cups?|
        saucers?|teapots?|pitchers?|decanters?|goblets?|glassware|tableware|
        cutlery|candlesticks?|candelabras?|serving|dish(?:es)?|mugs?|
        flatware|silverware|lamps?|clocks?|mirrors?|furniture|chairs?|
        samovars?|compotes?|chess\s+sets?|boxe?s?
    """),
    ("Desk, Office & Commemorative", r"""
        pens?|ballpoints?|fountain\s+pens?|desk\s+sets?|plaques?|medallions?|
        medals?|coins?|troph(?:y|ies)|awards?|paperweights?|letter\s+openers?|
        briefcases?|portfolios?|folders?|certificates?|key\s+to\s+the\s+city|
        commemorative|shields?|crests?|flags?
    """),
    ("Apparel & Accessories", r"""
        scarf|scarves|shawls?|neckties?|robes?|coats?|jackets?|dress(?:es)?|
        garments?|clothing|hats?|caps?|shoes?|boots?|handbags?|purses?|
        wallets?|belts?|gloves?|kimonos?|abayas?|thobes?|saris?|vests?|
        shirts?|capes?
    """),
    ("Food, Drink & Consumables", r"""
        whiske?y|whisky|wines?|champagne|vodka|cognac|liquor|spirits|sake|
        bottles?\s+of|chocolates?|candy|sweets|caviar|honey|olive\s+oil|
        cigars?|perfumes?|colognes?|fragrances?|soaps?|cosmetics|
        baskets?\s+of|fruit|nuts
    """),
    ("Electronics & Equipment", r"""
        ipad|iphone|tablets?|laptops?|computers?|cameras?|phones?|headphones|
        speakers?|radios?|televisions?|electronics?|drones?|binoculars|
        telescopes?|knives|knife|daggers?|swords?|firearms?|rifles?|pistols?|
        saddles?|bicycles?
    """),
]

COMPILED = [(name, re.compile(rf"\b(?:{pat})\b", re.I | re.X)) for name, pat in CATEGORIES]


def categorize(description):
    """Return (category, matched_on) for one item description."""
    if not isinstance(description, str) or not description.strip():
        return "Unclassified", "empty"
    head = description.split(",")[0]
    for name, pattern in COMPILED:
        if pattern.search(head):
            return name, "head"
    for name, pattern in COMPILED:
        if pattern.search(description):
            return name, "full"
    return "Unclassified", "none"


d = pd.concat(
    [pd.read_csv(f) for f in sorted(glob.glob("cleaned/*.csv"))], ignore_index=True
)
items = d["item"].fillna("").astype(str)
result = [categorize(t) for t in items]
d["category"] = [c for c, _ in result]
d["matched_on"] = [m for _, m in result]

total = len(d)
counts = collections.Counter(d["category"])
print(f"items: {total}\n")
print("=== category distribution ===")
for name, _ in CATEGORIES + [("Unclassified", None)]:
    n = counts.get(name, 0)
    print(f"  {n:6d}  {100*n/total:5.1f}%  {name}")
print()
print("=== matched on ===")
for k, n in collections.Counter(d["matched_on"]).most_common():
    print(f"  {n:6d}  {k}")
print()
print("=== 6 samples per category ===")
for name, _ in CATEGORIES:
    sub = d[d["category"] == name]["item"].drop_duplicates().head(6)
    print(f"\n-- {name} ({counts.get(name,0)})")
    for s in sub:
        print(f"     {s[:95]}")
print("\n-- Unclassified samples")
for s in d[d["category"] == "Unclassified"]["item"].drop_duplicates().head(25):
    print(f"     {s[:95]}")
