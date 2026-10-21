"""Probe: how well does a *supervised* text classifier do, versus the regex?

Key observation: 17% of records carry a category the State Department itself
wrote into the description -- "Artwork: ...", "Household item: ...",
"Consumables: ...". That is free training data and free ground truth, so the
choice between regex and a learned model can be measured rather than argued.

Multinomial Naive Bayes on word uni+bigrams, 5-fold cross-validation, written
out by hand so the probe needs no scikit-learn. NB is the weakest reasonable
learned model, so treat its score as a floor, not a ceiling.
"""

import collections
import glob
import math
import re

import numpy as np
import pandas as pd

TRUTH = {
    "TRAVEL": "Travel & Hospitality", "GIFT OF TRAVEL": "Travel & Hospitality",
    "Travel": "Travel & Hospitality",
    "Artwork": "Art & Decorative", "Vase": "Art & Decorative",
    "Painting": "Art & Decorative", "Photograph": "Art & Decorative",
    "Household item": "Household & Tableware", "Household Item": "Household & Tableware",
    "Household": "Household & Tableware", "Household accessory": "Household & Tableware",
    "Bowl": "Household & Tableware",
    "Hardcover book": "Books & Media", "Book": "Books & Media",
    "Hardback book": "Books & Media", "Paperback book": "Books & Media",
    "Jewelry": "Jewellery & Watches", "Watch": "Jewellery & Watches",
    "Necklace": "Jewellery & Watches",
    "Clothing": "Apparel & Accessories", "Accessory": "Apparel & Accessories",
    "Rug": "Textiles & Rugs", "Fabric": "Textiles & Rugs",
    "Table linens": "Textiles & Rugs",
    "Desk accessory": "Desk, Office & Commemorative",
    "Desk Accessory": "Desk, Office & Commemorative",
    "Consumables": "Food, Drink & Consumables", "Consumable": "Food, Drink & Consumables",
    "Flowers": "Food, Drink & Consumables",
    "Weapon": "Electronics & Equipment", "Sword": "Electronics & Equipment",
}

# Dimensions, colours and dates dominate these strings and carry no category
# signal, so they are collapsed to placeholders rather than learned as features.
NOISE = [
    (re.compile(r"\d+(?:\.\d+)?\s*(?:″|\"|'|′|inch(?:es)?|cm|ft|feet)"), " DIM "),
    (re.compile(r"\$\s?[\d,]+(?:\.\d+)?"), " MONEY "),
    (re.compile(r"\b(?:january|february|march|april|may|june|july|august|september"
                r"|october|november|december)\b", re.I), " MONTH "),
    (re.compile(r"\b\d+\b"), " NUM "),
]


def featurize(text):
    """Tokens for one description: uni+bigrams of the de-noised head region."""
    t = text.lower()
    for pattern, repl in NOISE:
        t = pattern.sub(repl, t)
    words = re.findall(r"[a-z]{3,}", t)[:25]  # head-weighted: first 25 words
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def train(docs, labels, alpha=0.2):
    classes = sorted(set(labels))
    vocab = {w: i for i, w in enumerate(
        {w for d in docs for w in d})}
    counts = np.full((len(classes), len(vocab)), alpha)
    prior = np.zeros(len(classes))
    cidx = {c: i for i, c in enumerate(classes)}
    for d, y in zip(docs, labels):
        i = cidx[y]
        prior[i] += 1
        for w in d:
            counts[i, vocab[w]] += 1
    logprob = np.log(counts) - np.log(counts.sum(axis=1, keepdims=True))
    return classes, vocab, logprob, np.log(prior / prior.sum())


def predict(model, doc):
    classes, vocab, logprob, logprior = model
    score = logprior.copy()
    for w in doc:
        j = vocab.get(w)
        if j is not None:
            score += logprob[:, j]
    return classes[int(np.argmax(score))]


d = pd.concat([pd.read_csv(f) for f in sorted(glob.glob("cleaned/*.csv"))],
              ignore_index=True)
items = d["item"].fillna("").astype(str)
d["pre"] = items.str.extract(r"^([A-Z][A-Za-z /&\'-]{2,28}):\s")[0]
d["truth"] = d["pre"].map(TRUTH)

labelled = d[d["truth"].notna()].copy()
# Strip the prefix -- otherwise the model just reads the answer off the front.
labelled["stripped"] = labelled["item"].astype(str).str.replace(
    r"^[A-Z][A-Za-z /&\'-]{2,28}:\s*", "", regex=True)

docs = [featurize(t) for t in labelled["stripped"]]
truth = list(labelled["truth"])
regex_pred = list(labelled["item_type"])

rng = np.random.default_rng(7)
order = rng.permutation(len(docs))
folds = np.array_split(order, 5)

nb_correct = regex_correct = total = 0
nb_nt = rx_nt = total_nt = 0
confusion = collections.Counter()
for k in range(5):
    test = folds[k]
    trainidx = np.concatenate([folds[j] for j in range(5) if j != k])
    model = train([docs[i] for i in trainidx], [truth[i] for i in trainidx])
    for i in test:
        p = predict(model, docs[i])
        nb_correct += p == truth[i]
        regex_correct += regex_pred[i] == truth[i]
        total += 1
        if truth[i] != "Travel & Hospitality":
            nb_nt += p == truth[i]
            rx_nt += regex_pred[i] == truth[i]
            total_nt += 1
            if p != truth[i]:
                confusion[(truth[i], p)] += 1

print(f"labelled rows available: {len(docs)}\n")
print("                       all rows      objects only (no Travel)")
print(f"  regex rules          {100*regex_correct/total:5.1f}%"
      f"            {100*rx_nt/total_nt:5.1f}%")
print(f"  Naive Bayes (5-fold) {100*nb_correct/total:5.1f}%"
      f"            {100*nb_nt/total_nt:5.1f}%")
print(f"\n  n = {total} / {total_nt}")
print("\n=== NB's remaining object confusions (truth -> predicted) ===")
for (t, p), n in confusion.most_common(10):
    print(f"  {n:4d}  {t}  ->  {p}")
